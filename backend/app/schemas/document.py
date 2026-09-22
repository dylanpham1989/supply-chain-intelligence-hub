from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.models.enums import DocStatus, DocType
from app.schemas.common import PaginationParams


class DocumentFilters(PaginationParams):
    model_config = ConfigDict(extra="forbid")

    doc_type: DocType | None = None
    status: DocStatus | None = None


DocumentFilterQuery = Annotated[DocumentFilters, Query()]


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    doc_type: DocType
    status: DocStatus
    page_count: int | None
    error: str | None
    indexed_at: datetime | None
    created_at: datetime


class DocumentAccepted(BaseModel):
    document_id: UUID
    status: DocStatus
    job_id: str | None


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chunk_index: int
    content: str
    page_no: int | None
    token_count: int | None
    meta: dict[str, Any]


class DownloadLink(BaseModel):
    url: str
    expires_in: int
