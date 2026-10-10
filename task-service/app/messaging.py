import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractExchange, AbstractRobustConnection

from app.metrics import events_published_total

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "taskflow.events"
CONNECT_ATTEMPTS = 10
CONNECT_DELAY_SECONDS = 3


async def connect_with_retry(url: str) -> AbstractRobustConnection:
    """connect_robust с ретраями: до CONNECT_ATTEMPTS попыток с паузой CONNECT_DELAY_SECONDS."""
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            return await aio_pika.connect_robust(url)
        except Exception as exc:
            logger.warning(
                "RabbitMQ connect attempt %s/%s failed: %s", attempt, CONNECT_ATTEMPTS, exc
            )
            if attempt == CONNECT_ATTEMPTS:
                raise
            await asyncio.sleep(CONNECT_DELAY_SECONDS)
    raise RuntimeError("unreachable")


class EventPublisher:
    def __init__(self, url: str, service_name: str) -> None:
        self.url = url
        self.service_name = service_name
        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None

    @property
    def is_connected(self) -> bool:
        return self._exchange is not None and not self._connection.is_closed

    async def connect(self) -> None:
        self._connection = await connect_with_retry(self.url)
        channel = await self._connection.channel()
        self._exchange = await channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )
        logger.info("Connected to RabbitMQ, exchange %s declared", EXCHANGE_NAME)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        envelope = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(UTC).isoformat(),
            "producer": self.service_name,
            "payload": payload,
        }
        if not self.is_connected:
            logger.warning("RabbitMQ is not connected, event %s dropped", event_type)
            events_published_total.labels(event_type=event_type, result="error").inc()
            return
        try:
            message = Message(
                json.dumps(envelope).encode(),
                content_type="application/json",
                delivery_mode=DeliveryMode.PERSISTENT,
                message_id=envelope["event_id"],
            )
            await self._exchange.publish(message, routing_key=event_type)
        except Exception:
            # запрос пользователя не должен падать из-за брокера
            logger.error("Failed to publish event %s", event_type, exc_info=True)
            events_published_total.labels(event_type=event_type, result="error").inc()
            return
        events_published_total.labels(event_type=event_type, result="success").inc()
        logger.info("Published event %s (%s)", event_type, envelope["event_id"])

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._exchange = None
