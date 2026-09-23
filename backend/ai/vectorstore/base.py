from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class VectorItem:
    chunk_id: UUID
    document_id: UUID
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchHit:
    chunk_id: UUID
    document_id: UUID
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    """One interface over pgvector and pinecone.

    Every method takes the tenant. Filtering after the search instead of during
    it is the mistake this shape exists to prevent: a tenant with little data
    would get nothing back, because the top k would all belong to someone else.
    """

    async def upsert(self, tenant_id: UUID, items: list[VectorItem]) -> int: ...

    async def search(
        self,
        tenant_id: UUID,
        query: list[float],
        *,
        k: int = 8,
        doc_type: str | None = None,
        document_ids: list[UUID] | None = None,
    ) -> list[SearchHit]: ...

    async def delete_document(self, tenant_id: UUID, document_id: UUID) -> int: ...
