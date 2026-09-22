"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-22 11:48:56.167816

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tenants",
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )
    op.create_table(
        "alerts",
        sa.Column(
            "kind",
            sa.Enum(
                "late_delivery", "contract_expiry", "supplier_risk", "sla_breach", name="alert_kind"
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("low", "medium", "high", "critical", name="alert_severity"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_alerts_tenant_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index("ix_alerts_tenant_created", "alerts", ["tenant_id", "created_at"], unique=False)
    op.create_index(
        "ix_alerts_tenant_unread",
        "alerts",
        ["tenant_id", "created_at"],
        unique=False,
        postgresql_where="is_read = false",
    )
    op.create_table(
        "suppliers",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("on_time_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("risk_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_suppliers_tenant_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_suppliers_tenant_id_name")),
    )
    op.create_index(
        "ix_suppliers_tenant_risk", "suppliers", ["tenant_id", "risk_score"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.Enum("admin", "analyst", "viewer", name="user_role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_users_tenant_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("tenant_id", "email", name=op.f("uq_users_tenant_id_email")),
    )
    op.create_table(
        "documents",
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column(
            "doc_type", sa.Enum("contract", "manifest", "invoice", name="doc_type"), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "indexed", "failed", name="doc_status"),
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_documents_tenant_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_documents_uploaded_by"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("s3_key", name=op.f("uq_documents_s3_key")),
    )
    op.create_index(
        "ix_documents_tenant_status", "documents", ["tenant_id", "status"], unique=False
    )
    op.create_table(
        "insights",
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("route", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_in", sa.Integer(), nullable=True),
        sa.Column("token_out", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_insights_created_by"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_insights_tenant_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_insights")),
    )
    op.create_index(
        "ix_insights_tenant_created", "insights", ["tenant_id", "created_at"], unique=False
    )
    op.create_table(
        "shipments",
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("supplier_id", sa.UUID(), nullable=True),
        sa.Column("origin_country", sa.String(length=2), nullable=False),
        sa.Column("dest_country", sa.String(length=2), nullable=False),
        sa.Column(
            "mode", sa.Enum("air", "ocean", "road", "rail", name="transport_mode"), nullable=False
        ),
        sa.Column("incoterm", sa.String(length=8), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("value_usd", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("eta", sa.Date(), nullable=False),
        sa.Column("ata", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "planned", "in_transit", "delivered", "delayed", "cancelled", name="shipment_status"
            ),
            nullable=False,
        ),
        sa.Column(
            "risk_label", sa.Enum("on_time", "at_risk", "delayed", name="risk_label"), nullable=True
        ),
        sa.Column("risk_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name=op.f("fk_shipments_supplier_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_shipments_tenant_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipments")),
        sa.UniqueConstraint(
            "tenant_id", "reference", name=op.f("uq_shipments_tenant_id_reference")
        ),
    )
    op.create_index(
        "ix_shipments_tenant_created", "shipments", ["tenant_id", "created_at"], unique=False
    )
    op.create_index("ix_shipments_tenant_eta", "shipments", ["tenant_id", "eta"], unique=False)
    op.create_index(
        "ix_shipments_tenant_status", "shipments", ["tenant_id", "status"], unique=False
    )
    op.create_table(
        "contracts",
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("contract_number", sa.String(length=64), nullable=False),
        sa.Column("supplier_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("penalty_terms", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_contracts_document_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name=op.f("fk_contracts_supplier_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_contracts_tenant_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
        sa.UniqueConstraint(
            "tenant_id", "contract_number", name=op.f("uq_contracts_tenant_id_contract_number")
        ),
    )
    op.create_index(
        "ix_contracts_tenant_expiry", "contracts", ["tenant_id", "effective_to"], unique=False
    )
    op.create_table(
        "document_chunks",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_document_chunks_tenant_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name=op.f("uq_document_chunks_document_id_chunk_index")
        ),
    )
    op.create_index(
        "ix_chunks_tenant_doc", "document_chunks", ["tenant_id", "document_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunks_tenant_doc", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_contracts_tenant_expiry", table_name="contracts")
    op.drop_table("contracts")
    op.drop_index("ix_shipments_tenant_status", table_name="shipments")
    op.drop_index("ix_shipments_tenant_eta", table_name="shipments")
    op.drop_index("ix_shipments_tenant_created", table_name="shipments")
    op.drop_table("shipments")
    op.drop_index("ix_insights_tenant_created", table_name="insights")
    op.drop_table("insights")
    op.drop_index("ix_documents_tenant_status", table_name="documents")
    op.drop_table("documents")
    op.drop_table("users")
    op.drop_index("ix_suppliers_tenant_risk", table_name="suppliers")
    op.drop_table("suppliers")
    op.drop_index(
        "ix_alerts_tenant_unread", table_name="alerts", postgresql_where="is_read = false"
    )
    op.drop_index("ix_alerts_tenant_created", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("tenants")

    # Dropping a table leaves its enum type behind, so downgrade followed by
    # upgrade would fail with "type already exists".
    for enum_name in (
        "alert_kind",
        "alert_severity",
        "doc_status",
        "doc_type",
        "risk_label",
        "shipment_status",
        "transport_mode",
        "user_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
