"""Request-scoped identifiers that every log line picks up.

ContextVar rather than thread local: the server is async, and one thread serves
many requests interleaved, so a thread local would attribute log lines to
whichever request happened to be running.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def set_request_id(value: str) -> None:
    request_id_var.set(value)


def set_actor(tenant_id: str, user_id: str) -> None:
    tenant_id_var.set(tenant_id)
    user_id_var.set(user_id)


def current_request_id() -> str:
    return request_id_var.get()


def current_context() -> dict[str, str]:
    return {
        key: value
        for key, value in (
            ("request_id", request_id_var.get()),
            ("tenant_id", tenant_id_var.get()),
            ("user_id", user_id_var.get()),
        )
        if value
    }


def bind_job_context(*, request_id: str, tenant_id: str) -> None:
    """A job continues the request that enqueued it.

    arq runs each job in its own task, so the values set here belong to that job
    and do not leak into the next one on the same worker.
    """
    request_id_var.set(request_id)
    tenant_id_var.set(tenant_id)
