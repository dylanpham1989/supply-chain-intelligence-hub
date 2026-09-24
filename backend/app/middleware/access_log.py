"""One log line per request.

Uvicorn's own access log is disabled in configure_logging, because it writes a
second line for the same request with none of the context that makes the first
one useful.
"""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import current_context
from app.core.logging import get_logger
from app.middleware.request_context import route_template

log = get_logger("app.access")

SERVER_ERROR = 500


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        # An exception that escapes never reaches http.response.start, so the
        # default has to be the status the server will end up sending.
        status = SERVER_ERROR

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # The tenant is only known once the token is decoded, which happens
            # deeper in the stack, so this is read after the response.
            log.info(
                "http.request",
                method=scope.get("method", ""),
                route=route_template(scope),
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                **current_context(),
            )
