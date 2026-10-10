import asyncio
import logging

import aio_pika
from aio_pika.abc import AbstractRobustConnection

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
