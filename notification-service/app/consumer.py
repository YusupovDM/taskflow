import json
import logging

from aio_pika import ExchangeType
from aio_pika.abc import AbstractRobustConnection

from app.database import SessionLocal
from app.messaging import EXCHANGE_NAME, connect_with_retry
from app.metrics import events_consumed_total
from app.services.events import handle_event

logger = logging.getLogger(__name__)

DLX_NAME = "taskflow.dlx"
DLQ_NAME = "taskflow.dead-letter"
QUEUE_NAME = "notification-service.events"
BINDINGS = ["#"]  # все события
PREFETCH_COUNT = 10


class EventConsumer:
    def __init__(self, url: str) -> None:
        self.url = url
        self._connection: AbstractRobustConnection | None = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def run(self) -> None:
        self._connection = await connect_with_retry(self.url)
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH_COUNT)

        exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
        dlx = await channel.declare_exchange(DLX_NAME, ExchangeType.FANOUT, durable=True)
        dlq = await channel.declare_queue(DLQ_NAME, durable=True)
        await dlq.bind(dlx)

        queue = await channel.declare_queue(
            QUEUE_NAME, durable=True, arguments={"x-dead-letter-exchange": DLX_NAME}
        )
        for routing_key in BINDINGS:
            await queue.bind(exchange, routing_key=routing_key)
        logger.info("Consuming %s (bindings: %s)", QUEUE_NAME, ", ".join(BINDINGS))

        async with queue.iterator() as messages:
            async for message in messages:
                event_type = message.routing_key or "unknown"
                try:
                    async with message.process(requeue=False):  # исключение → reject → DLQ
                        event = json.loads(message.body)
                        async with SessionLocal() as session:
                            await handle_event(session, event)
                except Exception:
                    logger.exception("Failed to handle event %s, sent to DLQ", event_type)
                    events_consumed_total.labels(event_type=event_type, result="error").inc()
                else:
                    events_consumed_total.labels(event_type=event_type, result="success").inc()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
