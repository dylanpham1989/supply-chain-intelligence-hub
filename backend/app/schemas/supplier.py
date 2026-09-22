from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginationParams

SupplierSort = Literal["name", "on_time_rate", "risk_score", "created_at"]


class SupplierFilters(PaginationParams):
    model_config = ConfigDict(extra="forbid")

    country: str | None = Field(None, min_length=2, max_length=2)
    category: str | None = Field(None, max_length=64)
    search: str | None = Field(None, min_length=1, max_length=100)
    sort: SupplierSort = "name"
    order: Literal["asc", "desc"] = "asc"


SupplierFilterQuery = Annotated[SupplierFilters, Query()]


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    country: str
    category: str
    contact_email: str | None
    on_time_rate: Decimal | None
    risk_score: Decimal | None
    created_at: datetime


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=2, max_length=2)
    category: str = Field(min_length=1, max_length=64)
    contact_email: str | None = Field(None, max_length=320)


class SupplierPerformance(BaseModel):
    supplier_id: UUID
    name: str
    shipments: int
    delivered: int
    late: int
    on_time_rate: float | None
    avg_delay_days: float | None
    monthly: list["SupplierMonth"]


class SupplierMonth(BaseModel):
    month: str
    shipments: int
    late: int
