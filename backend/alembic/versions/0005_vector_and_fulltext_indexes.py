"""vector and fulltext indexes

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23

"""

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "document_chunks"

# HNSW rather than IVFFlat. IVFFlat has to train its lists on existing rows, and
# a migration always runs against an empty table, which would leave the index
# built on nothing and recall poor in a way nothing reports.
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX ix_chunks_embedding ON {TABLE} "
        f"USING hnsw (embedding vector_cosine_ops) "
        f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})"
    )

    # A generated column stays in step with content without a trigger to forget.
    op.execute(
        f"ALTER TABLE {TABLE} ADD COLUMN content_tsv tsvector "
        f"GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute(f"CREATE INDEX ix_chunks_tsv ON {TABLE} USING gin (content_tsv)")

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks TO app_user")


def downgrade() -> None:
    op.drop_column("documents", "embedding_dim")
    op.execute("DROP INDEX IF EXISTS ix_chunks_tsv")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
