from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.models.enums import AlertKind, AlertSeverity
from app.schemas.common import PaginationParams


class AlertFilters(PaginationParams):
    model_config = ConfigDict(extra="forbid")

    kind: AlertKind | None = None
    severity: AlertSeverity | None = None
    unread_only: bool = False


AlertFilterQuery = Annotated[AlertFilters, Query()]


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: AlertKind
    severity: AlertSeverity
    title: str
    body: str | None
    entity_type: str | None
    entity_id: UUID | None
    is_read: bool
    created_at: datetime
