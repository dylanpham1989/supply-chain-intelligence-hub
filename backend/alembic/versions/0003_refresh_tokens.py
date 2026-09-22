"""refresh tokens

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22

"""

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "refresh_tokens"

# Same predicate as 0002, repeated rather than imported so this revision keeps
# standing on its own.
TENANT_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.UUID(), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
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
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_refresh_tokens_tenant_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index("ix_refresh_tokens_family", TABLE, ["family_id"], unique=False)
    op.create_index("ix_refresh_tokens_tenant_user", TABLE, ["tenant_id", "user_id"], unique=False)

    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {TABLE}
            USING ({TENANT_PREDICATE})
            WITH CHECK ({TENANT_PREDICATE})
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO app_user")


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {TABLE}")
    op.drop_index("ix_refresh_tokens_tenant_user", table_name=TABLE)
    op.drop_index("ix_refresh_tokens_family", table_name=TABLE)
    op.drop_table(TABLE)
