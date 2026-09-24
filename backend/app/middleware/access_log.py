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
CLIENT_ERROR = 400


class AccessLogMiddleware:
    """One line per request, minus the traffic nobody reads.

    Kubernetes probes every few seconds and Prometheus scrapes every fifteen. At
    a line each that is most of the log volume and none of its value, so those
    paths are logged only when they answer with an error.
    """

    def __init__(self, app: ASGIApp, *, quiet_paths: tuple[str, ...] = ()) -> None:
        self.app = app
        self.quiet_paths = quiet_paths

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
            if status >= CLIENT_ERROR or scope.get("path", "") not in self.quiet_paths:
                # The tenant is only known once the token is decoded, which
                # happens deeper in the stack, so this is read after the
                # response rather than before the call.
                log.info(
                    "http.request",
                    method=scope.get("method", ""),
                    route=route_template(scope),
                    status=status,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    **current_context(),
                )
