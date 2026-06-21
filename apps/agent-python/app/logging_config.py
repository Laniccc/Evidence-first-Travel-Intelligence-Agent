import logging
import sys
from uuid import uuid4

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, log_level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper(), logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def bind_request_context(request_id: str | None = None, session_id: str | None = None) -> dict:
    rid = request_id or str(uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=rid, session_id=session_id or rid)
    return {"request_id": rid, "session_id": session_id or rid}


def get_logger(name: str):
    return structlog.get_logger(name)
