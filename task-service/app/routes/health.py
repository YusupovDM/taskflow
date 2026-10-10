import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.dependencies import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request, session: SessionDep):
    """БД обязательна (иначе 503); брокер показывается в теле, но статус не валит."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse({"status": "unavailable", "database": "error"}, status_code=503)
    state = request.app.state
    rabbitmq = "ok" if state.publisher.is_connected and state.consumer.is_connected else "degraded"
    return {"status": "ok", "database": "ok", "rabbitmq": rabbitmq}
