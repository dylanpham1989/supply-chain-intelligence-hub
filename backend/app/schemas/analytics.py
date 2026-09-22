from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Summary(BaseModel):
    total_shipments: int
    delayed: int
    in_transit: int
    delivered: int
    total_value_usd: Decimal
    on_time_rate: float | None
    avg_delay_days: float | None
    since: date


class StatusCount(BaseModel):
    status: str
    shipments: int
    value_usd: Decimal


class StatusBreakdown(BaseModel):
    items: list[StatusCount]


class TimeseriesPoint(BaseModel):
    month: str
    shipments: int
    late: int
    value_usd: Decimal


class Timeseries(BaseModel):
    items: list[TimeseriesPoint]


class SupplierRanking(BaseModel):
    supplier_id: str
    name: str
    shipments: int
    late: int
    on_time_rate: float | None


class TopSuppliers(BaseModel):
    items: list[SupplierRanking]


class RiskSlice(BaseModel):
    label: str
    shipments: int


class RiskBreakdown(BaseModel):
    items: list[RiskSlice]
