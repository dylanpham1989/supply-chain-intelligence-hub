from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator

MAX_EMAIL_LENGTH = 320


def _normalise_email(value: str) -> str:
    """Validate syntax and normalise, without rejecting reserved domains.

    pydantic's EmailStr turns away .test, .internal and similar, which breaks both
    the demo seed and any customer on an internal domain. Whether an address can
    actually receive mail is not something syntax can answer; a verification email
    is what settles that.
    """
    if len(value) > MAX_EMAIL_LENGTH:
        raise ValueError("email is too long")
    try:
        result = validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized.lower()


Email = Annotated[str, AfterValidator(_normalise_email)]
