from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.vectorstore.base import SearchHit, VectorItem

# Higher means better recall and a slower query. 40 is a reasonable middle for
# an index this size; it is a per-session setting, not an index property.
EF_SEARCH = 40

# The tenant predicate is in the statement, not applied to the results. Postgres
# can use the tenant-leading index for it, and a search that returns nothing is
# better than one that returns someone else's documents.
# Every optional parameter is cast. asyncpg infers types from the statement, and
# a bare :param compared against NULL gives it nothing to infer from.
SEARCH_SQL = text("""
    SELECT id, document_id, content, metadata,
           1 - (embedding <=> CAST(:query AS vector)) AS score
    FROM document_chunks
    WHERE tenant_id = CAST(:tenant_id AS uuid)
      AND embedding IS NOT NULL
      AND (CAST(:doc_type AS text) IS NULL OR metadata->>'doc_type' = CAST(:doc_type AS text))
      AND (
            CAST(:filter_docs AS boolean) IS FALSE
            OR document_id = ANY(CAST(:document_ids AS uuid[]))
          )
    ORDER BY embedding <=> CAST(:query AS vector)
    LIMIT :k
""")

UPSERT_SQL = text("""
    UPDATE document_chunks
       SET embedding = CAST(:embedding AS vector)
     WHERE id = CAST(:chunk_id AS uuid) AND tenant_id = CAST(:tenant_id AS uuid)
""")

DELETE_SQL = text("""
    UPDATE document_chunks
       SET embedding = NULL
     WHERE tenant_id = CAST(:tenant_id AS uuid) AND document_id = CAST(:document_id AS uuid)
""")


class PgVectorStore:
    """Vectors next to the rows they describe.

    The same row-level security policy covers them, which is one fewer boundary
    to get right, and there is no second system to keep in step.
    """

    backend = "pgvector"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, tenant_id: UUID, items: list[VectorItem]) -> int:
        if not items:
            return 0
        written = 0
        for item in items:
            result: CursorResult[None] = await self.session.execute(  # type: ignore[assignment]
                UPSERT_SQL,
                {
                    "chunk_id": str(item.chunk_id),
                    "tenant_id": str(tenant_id),
                    "embedding": _vector_literal(item.embedding),
                },
            )
            written += result.rowcount or 0
        await self.session.flush()
        return written

    async def search(
        self,
        tenant_id: UUID,
        query: list[float],
        *,
        k: int = 8,
        doc_type: str | None = None,
        document_ids: list[UUID] | None = None,
    ) -> list[SearchHit]:
        await self.session.execute(text(f"SET LOCAL hnsw.ef_search = {EF_SEARCH}"))
        rows = (
            await self.session.execute(
                SEARCH_SQL,
                {
                    "tenant_id": str(tenant_id),
                    "query": _vector_literal(query),
                    "k": k,
                    "doc_type": doc_type,
                    "filter_docs": bool(document_ids),
                    "document_ids": [str(d) for d in (document_ids or [])],
                },
            )
        ).mappings()

        return [
            SearchHit(
                chunk_id=row["id"],
                document_id=row["document_id"],
                content=row["content"],
                score=float(row["score"]),
                metadata=dict(row["metadata"] or {}),
            )
            for row in rows
        ]

    async def delete_document(self, tenant_id: UUID, document_id: UUID) -> int:
        result: CursorResult[None] = await self.session.execute(  # type: ignore[assignment]
            DELETE_SQL, {"tenant_id": str(tenant_id), "document_id": str(document_id)}
        )
        await self.session.flush()
        return result.rowcount or 0


def _vector_literal(values: list[float]) -> str:
    """pgvector reads its own bracket syntax; asyncpg has no adapter for a list."""
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


def as_items(rows: list[dict[str, Any]]) -> list[VectorItem]:
    return [
        VectorItem(
            chunk_id=row["id"],
            document_id=row["document_id"],
            content=row["content"],
            embedding=row["embedding"],
            metadata=row.get("metadata") or {},
        )
        for row in rows
    ]
