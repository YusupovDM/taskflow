import asyncio
import logging
import socket
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.consumer import EventConsumer
from app.database import engine
from app.exceptions import register_exception_handlers
from app.messaging import EventPublisher
from app.routes import health, projects, tasks

logging.basicConfig(
    level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

INSTANCE_ID = socket.gethostname()


async def _connect_publisher(publisher: EventPublisher) -> None:
    try:
        await publisher.connect()
    except Exception:
        logger.warning("RabbitMQ unavailable, events will not be published", exc_info=True)


async def _run_consumer(consumer: EventConsumer) -> None:
    try:
        await consumer.run()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("RabbitMQ consumer stopped, user replicas will not sync", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    publisher = EventPublisher(settings.rabbitmq_url, settings.service_name)
    consumer = EventConsumer(settings.rabbitmq_url)
    app.state.publisher = publisher
    app.state.consumer = consumer
    background: list[asyncio.Task] = []
    if settings.rabbitmq_enabled:
        # подключение в фоне: сервис стартует и без брокера (graceful degradation)
        background.append(asyncio.create_task(_connect_publisher(publisher)))
        background.append(asyncio.create_task(_run_consumer(consumer)))
    else:
        logger.warning("RABBITMQ_ENABLED=false: events are disabled")

    yield

    for task in background:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    await consumer.close()
    await publisher.close()
    await engine.dispose()


app = FastAPI(
    title="TaskFlow Tasks",
    docs_url="/docs/tasks",
    openapi_url="/docs/tasks/openapi.json",
    lifespan=lifespan,
)
register_exception_handlers(app)


@app.middleware("http")
async def add_instance_id(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Instance-ID"] = INSTANCE_ID
    return response


app.include_router(projects.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(health.router)

Instrumentator().instrument(app).expose(app, include_in_schema=False)
