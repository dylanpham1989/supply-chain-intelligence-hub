"""document job id

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22

"""

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("job_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "job_id")
