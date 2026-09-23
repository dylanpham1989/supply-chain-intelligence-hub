from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.vectorstore.base import SearchHit

# websearch_to_tsquery takes whatever a person types. plainto_ and to_tsquery
# raise on punctuation a user will absolutely type.
SEARCH_SQL = text("""
    SELECT id, document_id, content, metadata,
           ts_rank_cd(content_tsv, websearch_to_tsquery('english', :q)) AS score
    FROM document_chunks
    WHERE tenant_id = CAST(:tenant_id AS uuid)
      AND content_tsv @@ websearch_to_tsquery('english', :q)
      AND (CAST(:doc_type AS text) IS NULL OR metadata->>'doc_type' = CAST(:doc_type AS text))
    ORDER BY score DESC
    LIMIT :k
""")


class KeywordSearch:
    """Full text search over the same chunks.

    Vectors are poor at exact strings. "INV-2026-0412" or "clause 4.2" is a
    lexical match, and an embedding blurs precisely the part that matters.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self, tenant_id: UUID, query: str, *, k: int = 20, doc_type: str | None = None
    ) -> list[SearchHit]:
        if not query.strip():
            return []
        rows = (
            await self.session.execute(
                SEARCH_SQL,
                {"tenant_id": str(tenant_id), "q": query, "k": k, "doc_type": doc_type},
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
