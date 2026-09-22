from app.db.base import Base
from app.models.alert import Alert
from app.models.contract import Contract
from app.models.document import Document, DocumentChunk
from app.models.insight import Insight
from app.models.refresh_token import RefreshToken
from app.models.shipment import Shipment
from app.models.supplier import Supplier
from app.models.tenant import Tenant
from app.models.user import User

# Tables that carry tenant data and therefore need a row-level security policy.
# The RLS migration reads this list, so adding a model here is what turns its
# policy on.
TENANT_SCOPED_TABLES = (
    "users",
    "suppliers",
    "shipments",
    "contracts",
    "documents",
    "document_chunks",
    "insights",
    "alerts",
    "refresh_tokens",
)

__all__ = [
    "TENANT_SCOPED_TABLES",
    "Alert",
    "Base",
    "Contract",
    "Document",
    "DocumentChunk",
    "Insight",
    "RefreshToken",
    "Shipment",
    "Supplier",
    "Tenant",
    "User",
]
