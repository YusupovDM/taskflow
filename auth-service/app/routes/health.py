import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.dependencies import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness: процесс жив")
async def health():
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness: проверка зависимостей")
async def ready(session: SessionDep):
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}
