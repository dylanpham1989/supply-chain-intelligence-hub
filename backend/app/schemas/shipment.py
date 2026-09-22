from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RiskLabel, ShipmentStatus, TransportMode
from app.schemas.common import PaginationParams

# Literal, not str: a free-form sort column would let a caller order by
# password_hash and read it out of the ordering, and getattr would 500 on a typo.
ShipmentSort = Literal["created_at", "eta", "value_usd", "reference"]
SortOrder = Literal["asc", "desc"]


class ShipmentFilters(PaginationParams):
    model_config = ConfigDict(extra="forbid")

    status: ShipmentStatus | None = None
    mode: TransportMode | None = None
    risk_label: RiskLabel | None = None
    supplier_id: UUID | None = None
    origin_country: str | None = Field(None, min_length=2, max_length=2)
    dest_country: str | None = Field(None, min_length=2, max_length=2)
    eta_from: date | None = None
    eta_to: date | None = None
    late_only: bool = False
    search: str | None = Field(None, min_length=1, max_length=100)
    sort: ShipmentSort = "created_at"
    order: SortOrder = "desc"


ShipmentFilterQuery = Annotated[ShipmentFilters, Query()]


class ShipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    supplier_id: UUID | None
    origin_country: str
    dest_country: str
    mode: TransportMode
    incoterm: str | None
    qty: int
    value_usd: Decimal
    weight_kg: Decimal | None
    eta: date
    ata: date | None
    status: ShipmentStatus
    risk_label: RiskLabel | None
    risk_score: Decimal | None
    delay_days: int | None
    created_at: datetime


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1, max_length=64)
    supplier_id: UUID | None = None
    origin_country: str = Field(min_length=2, max_length=2)
    dest_country: str = Field(min_length=2, max_length=2)
    mode: TransportMode
    incoterm: str | None = Field(None, max_length=8)
    qty: int = Field(0, ge=0)
    value_usd: Decimal = Field(Decimal(0), ge=0)
    weight_kg: Decimal | None = Field(None, ge=0)
    eta: date
    ata: date | None = None
    status: ShipmentStatus = ShipmentStatus.PLANNED


class ShipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: UUID | None = None
    incoterm: str | None = Field(None, max_length=8)
    qty: int | None = Field(None, ge=0)
    value_usd: Decimal | None = Field(None, ge=0)
    weight_kg: Decimal | None = Field(None, ge=0)
    eta: date | None = None
    ata: date | None = None
    status: ShipmentStatus | None = None
