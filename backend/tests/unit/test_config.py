import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_JWT_SECRET, INSECURE_S3_SECRET, Settings

SAFE = {"jwt_secret": "a" * 48, "s3_secret_key": "b" * 32}


def test_local_env_accepts_placeholder_secrets() -> None:
    cfg = Settings(env="local", _env_file=None)

    assert cfg.jwt_secret == INSECURE_JWT_SECRET
    assert cfg.is_local is True


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_deployed_env_rejects_placeholder_jwt_secret(env: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(env=env, s3_secret_key=SAFE["s3_secret_key"], _env_file=None)


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_deployed_env_rejects_placeholder_s3_secret(env: str) -> None:
    with pytest.raises(ValidationError, match="S3_SECRET_KEY"):
        Settings(env=env, jwt_secret=SAFE["jwt_secret"], _env_file=None)


def test_deployed_env_accepts_real_secrets() -> None:
    cfg = Settings(env="prod", _env_file=None, **SAFE)

    assert cfg.is_local is False
    assert cfg.s3_secret_key != INSECURE_S3_SECRET


def test_cors_origins_accept_comma_separated_string() -> None:
    cfg = Settings(
        env="local",
        _env_file=None,
        cors_origins="http://a.test, http://b.test",  # type: ignore[arg-type]
    )

    assert cfg.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_parse_from_environment(monkeypatch: "pytest.MonkeyPatch") -> None:
    """Goes through the env source, which JSON-decodes complex types by default."""
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")

    cfg = Settings(env="local", _env_file=None)

    assert cfg.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_accept_json_array_from_environment(
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test"]')

    cfg = Settings(env="local", _env_file=None)

    assert cfg.cors_origins == ["http://a.test"]
