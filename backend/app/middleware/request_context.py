"""Give every request an id, and hand it back in the response.

Written as raw ASGI rather than BaseHTTPMiddleware: BaseHTTPMiddleware wraps
each request in an anyio task group and a memory stream to fake a response
object, which costs latency on every request and, because it runs the app in a
child task, loses contextvars set further down the stack. Everything here needs
both of those to work.
"""

import re
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import set_request_id

REQUEST_ID_HEADER = "x-request-id"

# A caller-supplied id ends up in log lines, so it is validated rather than
# trusted. A newline in it would let a caller forge log records.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

UNKNOWN_ROUTE = "unmatched"


def route_template(scope: Scope) -> str:
    """The path with its parameters put back as placeholders.

    `/api/v1/shipments/{shipment_id}`, never `/api/v1/shipments/3f2a-...`. As a
    metric label the raw path would mint one time series per shipment.

    It is rebuilt from the path and the matched parameters rather than read off
    `scope["route"].path`: FastAPI keeps included routers nested instead of
    flattening them, so the route object carries the path as its own router
    declared it, without the `/api/v1` prefix the request actually used.
    """
    if scope.get("route") is None:
        return UNKNOWN_ROUTE
    path = str(scope.get("path", ""))
    for name, value in (scope.get("path_params") or {}).items():
        path = path.replace(str(value), "{" + name + "}", 1)
    return path or UNKNOWN_ROUTE


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, REQUEST_ID_HEADER)
        request_id = incoming if SAFE_REQUEST_ID.match(incoming) else uuid4().hex
        set_request_id(request_id)
        scope["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_header)


def _header(scope: Scope, name: str) -> str:
    wanted = name.encode()
    for key, value in scope.get("headers", []):
        if bytes(key).lower() == wanted:
            return str(bytes(value).decode("latin-1"))
    return ""
