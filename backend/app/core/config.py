"""Settings. Nothing else in the codebase reads os.environ."""

import json
from contextlib import suppress
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Defaults so `make up` needs no config. Rejected outside local/test, see below.
INSECURE_JWT_SECRET = "insecure-local-secret-do-not-use-outside-development"  # noqa: S105
INSECURE_S3_SECRET = "minioadmin"  # noqa: S105

Environment = Literal["local", "test", "staging", "prod"]
VectorBackend = Literal["pgvector", "pinecone"]
LLMProviderName = Literal["mock", "anthropic", "openai", "hf"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Environment = "local"
    debug: bool = False
    app_name: str = "Supply Chain Intelligence Hub"
    api_prefix: str = "/api/v1"

    git_sha: str = "unknown"
    built_at: str = "unknown"

    database_url: str = "postgresql+asyncpg://app_user:app_password@localhost:5432/scih"
    db_pool_size: int = 10
    db_max_overflow: int = 5

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "scih-documents"
    s3_region: str = "us-east-1"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = INSECURE_S3_SECRET

    jwt_secret: str = INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    vector_backend: VectorBackend = "pgvector"
    pinecone_api_key: str | None = None
    pinecone_index: str = "scih"

    llm_provider: LLMProviderName = "mock"
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.1

    max_upload_bytes: int = 20 * 1024 * 1024
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # .env files give us "a,b", ConfigMaps give us '["a","b"]'.
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            with suppress(json.JSONDecodeError):
                return json.loads(text)
        return [item.strip() for item in text.split(",") if item.strip()]

    @model_validator(mode="after")
    def _reject_insecure_defaults(self) -> "Settings":
        if self.env in ("local", "test"):
            return self
        if self.jwt_secret == INSECURE_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set outside local environments")
        if self.s3_secret_key == INSECURE_S3_SECRET:
            raise ValueError("S3_SECRET_KEY must be set outside local environments")
        return self

    @property
    def is_local(self) -> bool:
        return self.env in ("local", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
