from typing import Annotated, Any
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocType
from app.schemas.common import PaginationParams
from app.schemas.shipment import ShipmentRead

MAX_QUESTION_CHARS = 1000


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)
    doc_type: DocType | None = None
    document_ids: list[UUID] | None = Field(None, max_length=20)
    top_k: int = Field(8, ge=1, le=20)


class Citation(BaseModel):
    number: int
    chunk_id: UUID
    document_id: UUID
    filename: str | None
    page_no: int | None
    section: str | None
    score: float


class AskResponse(BaseModel):
    question: str
    answer: str
    route: str
    citations: list[Citation] = []
    filters: dict[str, Any] = {}
    shipments: list[ShipmentRead] = []
    model: str
    total_ms: int


class InsightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question: str
    answer: str
    citations: list[dict[str, Any]]
    route: str
    model: str | None
    latency_ms: int | None
    token_in: int | None
    token_out: int | None
    created_at: Any


class InsightFilters(PaginationParams):
    model_config = ConfigDict(extra="forbid")

    route: str | None = None


InsightFilterQuery = Annotated[InsightFilters, Query()]
