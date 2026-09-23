import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai.embeddings.hf_embedder import get_embedder
from ai.vectorstore.base import SearchHit
from ai.vectorstore.fusion import reciprocal_rank_fusion
from ai.vectorstore.keyword import KeywordSearch
from ai.vectorstore.pgvector_store import PgVectorStore

CANDIDATES = 20
TOP_K = 8


@dataclass(frozen=True)
class Retrieved:
    hits: list[SearchHit]
    vector_count: int
    keyword_count: int
    latency_ms: int


class HybridRetriever:
    """Vectors and full text, merged by rank.

    Either alone has a blind spot: an embedding blurs "INV-2026-0412", and
    keywords miss a question phrased differently from the document.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.vectors = PgVectorStore(session)
        self.keywords = KeywordSearch(session)

    async def retrieve(
        self,
        question: str,
        *,
        k: int = TOP_K,
        doc_type: str | None = None,
        document_ids: list[UUID] | None = None,
    ) -> Retrieved:
        started = time.perf_counter()

        query_vector = await get_embedder().encode_query(question)
        vector_hits = await self.vectors.search(
            self.tenant_id,
            query_vector,
            k=CANDIDATES,
            doc_type=doc_type,
            document_ids=document_ids,
        )
        keyword_hits = await self.keywords.search(
            self.tenant_id, question, k=CANDIDATES, doc_type=doc_type
        )
        if document_ids:
            allowed = set(document_ids)
            keyword_hits = [h for h in keyword_hits if h.document_id in allowed]

        fused = reciprocal_rank_fusion([vector_hits, keyword_hits], limit=k)

        return Retrieved(
            hits=fused,
            vector_count=len(vector_hits),
            keyword_count=len(keyword_hits),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
