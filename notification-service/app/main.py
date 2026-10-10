import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.consumer import EventConsumer
from app.database import engine
from app.exceptions import register_exception_handlers
from app.request_context import add_request_id_middleware, setup_logging
from app.routes import health, notifications

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


async def _run_consumer(consumer: EventConsumer) -> None:
    try:
        await consumer.run()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("RabbitMQ consumer stopped, notifications will not arrive", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = EventConsumer(settings.rabbitmq_url)
    app.state.consumer = consumer
    consumer_task: asyncio.Task | None = None
    if settings.rabbitmq_enabled:
        consumer_task = asyncio.create_task(_run_consumer(consumer))
    else:
        logger.warning("RABBITMQ_ENABLED=false: consumer is disabled")

    yield

    if consumer_task is not None:
        consumer_task.cancel()
        with suppress(asyncio.CancelledError):
            await consumer_task
    await consumer.close()
    await engine.dispose()


app = FastAPI(
    title="TaskFlow Notifications",
    docs_url="/docs/notifications",
    openapi_url="/docs/notifications/openapi.json",
    lifespan=lifespan,
)
register_exception_handlers(app)
add_request_id_middleware(app)

app.include_router(notifications.router, prefix="/api/v1")
app.include_router(health.router)

Instrumentator().instrument(app).expose(app, include_in_schema=False)
