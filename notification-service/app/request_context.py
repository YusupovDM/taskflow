"""X-Request-ID: берём из запроса (его ставит Nginx), кладём в лог-контекст и в ответ."""

import logging
import time
from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("app.request")
QUIET_PATHS = {"/health", "/metrics"}  # healthcheck и Prometheus не засоряют лог

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    logging.basicConfig(level=level, handlers=[handler], force=True)


def add_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            if request.url.path not in QUIET_PATHS:
                logger.info(
                    "%s %s -> %s (%.1f ms)",
                    request.method,
                    request.url.path,
                    response.status_code,
                    (time.perf_counter() - started) * 1000,
                )
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
