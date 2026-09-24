"""HTTP counters and latency histogram."""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import tenant_id_var
from app.core.metrics import record_http, tenant_label
from app.middleware.request_context import UNKNOWN_ROUTE, route_template

SERVER_ERROR = 500


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, *, skip_paths: tuple[str, ...] = ()) -> None:
        self.app = app
        self.skip_paths = skip_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "") in self.skip_paths:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = SERVER_ERROR

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            route = route_template(scope)
            # A request for a path no route matches is a scan or a typo. Counting
            # it under its own label would let anyone on the internet add series.
            tenant = tenant_id_var.get()
            record_http(
                route=route,
                method=str(scope.get("method", "")),
                status=status,
                tenant=tenant_label(tenant) if tenant and route != UNKNOWN_ROUTE else "anonymous",
                duration_s=time.perf_counter() - started,
            )
