"""row level security

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

Autogenerate cannot see policies, so this one is written by hand. Anything that
changes the policies has to be edited here too.
"""

from alembic import op
from app.models import TENANT_SCOPED_TABLES

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

# NULLIF turns an unset GUC into NULL, and NULL = anything is never true, so a
# request that forgot to set the tenant sees nothing instead of everything.
TENANT_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # ENABLE alone exempts the table owner, which is who migrations run as.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # WITH CHECK is what postgres would infer from USING anyway, but writing
        # it out makes the write side of the policy obvious to the next reader.
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING ({TENANT_PREDICATE})
                WITH CHECK ({TENANT_PREDICATE})
            """
        )

    # Grants are per table and the tables did not exist when init-db.sql ran.
    for table in ("tenants", *TENANT_SCOPED_TABLES):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_user")


def downgrade() -> None:
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
