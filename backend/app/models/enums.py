from enum import StrEnum

from sqlalchemy import Enum


class UserRole(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class ShipmentStatus(StrEnum):
    PLANNED = "planned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class RiskLabel(StrEnum):
    ON_TIME = "on_time"
    AT_RISK = "at_risk"
    DELAYED = "delayed"


class TransportMode(StrEnum):
    AIR = "air"
    OCEAN = "ocean"
    ROAD = "road"
    RAIL = "rail"


class DocType(StrEnum):
    CONTRACT = "contract"
    MANIFEST = "manifest"
    INVOICE = "invoice"


class DocStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class AlertKind(StrEnum):
    LATE_DELIVERY = "late_delivery"
    CONTRACT_EXPIRY = "contract_expiry"
    SUPPLIER_RISK = "supplier_risk"
    SLA_BREACH = "sla_breach"


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def pg_enum[E: StrEnum](enum_cls: type[E], name: str) -> Enum:
    """Postgres enum whose labels are the member values, not the member names."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )
