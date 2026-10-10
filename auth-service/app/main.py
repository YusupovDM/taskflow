import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database import SessionLocal, engine
from app.exceptions import register_exception_handlers
from app.messaging import EventPublisher
from app.request_context import add_request_id_middleware, setup_logging
from app.routes import auth, health, users
from app.services.auth import ensure_admin

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    publisher = EventPublisher(settings.rabbitmq_url, settings.service_name)
    if settings.rabbitmq_enabled:
        await publisher.connect()
    app.state.publisher = publisher

    async with SessionLocal() as session:
        await ensure_admin(
            session,
            publisher,
            settings.admin_email,
            settings.admin_password,
            settings.admin_full_name,
        )

    yield

    await publisher.close()
    await engine.dispose()


app = FastAPI(
    title="TaskFlow Auth",
    docs_url="/docs/auth",
    openapi_url="/docs/auth/openapi.json",
    lifespan=lifespan,
)
register_exception_handlers(app)
add_request_id_middleware(app)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(health.router)

Instrumentator().instrument(app).expose(app, include_in_schema=False)
