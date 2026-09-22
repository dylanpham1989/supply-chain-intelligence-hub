from typing import Any


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    message = "Internal server error"

    def __init__(self, message: str | None = None, **extra: Any) -> None:
        self.message = message or self.message
        self.extra = extra
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    message = "Bad request"


class AuthError(AppError):
    status_code = 401
    code = "unauthenticated"
    # Deliberately vague: distinguishing "no such user" from "wrong password"
    # tells an attacker which emails exist.
    message = "Invalid credentials"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "Not allowed"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Already exists"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
    message = "Payload too large"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "Upstream unavailable"
