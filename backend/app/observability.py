import logging
import sys
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

import structlog
from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-ID"
request_id_context: ContextVar[str] = ContextVar("request_id", default="unavailable")

CallNext = Callable[[Request], Awaitable[Response]]


def configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def request_context_middleware(
    request: Request,
    call_next: CallNext,
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
    token = request_id_context.set(request_id)
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    logger = structlog.get_logger()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    else:
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return response
    finally:
        structlog.contextvars.unbind_contextvars("request_id")
        request_id_context.reset(token)
