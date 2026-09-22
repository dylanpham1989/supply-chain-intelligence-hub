"""Structured logging.

Logs go to stdout as JSON in every environment except local development, where a
human-readable renderer is easier to scan. Keys that look like credentials are
replaced before the record is rendered.
"""

import logging
import re
import sys
from typing import Any

import structlog

SENSITIVE_KEY = re.compile(r"(api[_-]?key|authorization|password|passwd|token|secret)", re.I)
REDACTED = "***"


def redact_sensitive(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    for key in list(event_dict):
        if SENSITIVE_KEY.search(key):
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(*, env: str = "local", level: str = "INFO") -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        redact_sensitive,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if env == "local":
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    else:
        renderer = structlog.processors.JSONRenderer()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper(), force=True)

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # The access-log middleware added in phase 9 emits one line per request, so
    # uvicorn's own access log would duplicate it.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
