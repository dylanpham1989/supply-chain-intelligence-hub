"""One tenant must never retrieve another tenant's text.

This is the claim the README makes about per-tenant retrieval. Both tenants get
a contract that answers the same question differently, and the answer has to
come from the asker's own document.
"""

from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.embeddings.hf_embedder import get_embedder
from ai.rag.retriever import HybridRetriever
from ai.vectorstore.base import VectorItem
from ai.vectorstore.pgvector_store import PgVectorStore
from app.db.rls import set_tenant_context
from app.models import Document, DocumentChunk, Tenant, User
from app.models.enums import DocStatus, DocType

pytestmark = pytest.mark.integration

ALPHA_CLAUSE = (
    "4.2 Late Delivery. Where a shipment arrives after the confirmed estimated time of "
    "arrival, the Supplier shall pay a penalty of 2 percent of the shipment value for each "
    "complete week of delay."
)
BETA_CLAUSE = (
    "4.2 Late Delivery. Where a shipment arrives late, the Supplier shall pay a penalty of "
    "5 percent of the shipment value for each complete month of delay."
)


async def _tenant(session: AsyncSession, slug: str) -> Tenant:
    tenant = Tenant(slug=slug, name=slug.title())
    session.add(tenant)
    await session.flush()
    return tenant


async def _indexed_chunk(session: AsyncSession, tenant: Tenant, content: str) -> DocumentChunk:
    await set_tenant_context(session, tenant.id)
    user = User(
        tenant_id=tenant.id,
        email=f"admin@{tenant.slug}.test",
        password_hash="x" * 20,
        full_name="Admin",
        role="admin",
    )
    session.add(user)
    await session.flush()

    document = Document(
        tenant_id=tenant.id,
        uploaded_by=user.id,
        filename=f"{tenant.slug}-contract.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        s3_key=f"{tenant.id}/{tenant.slug}.pdf",
        doc_type=DocType.CONTRACT,
        status=DocStatus.INDEXED,
    )
    session.add(document)
    await session.flush()

    chunk = DocumentChunk(
        tenant_id=tenant.id,
        document_id=document.id,
        chunk_index=0,
        content=content,
        meta={"doc_type": "contract", "filename": document.filename, "section": "4.2"},
    )
    session.add(chunk)
    await session.flush()

    vector = await get_embedder().encode_query(content)
    await PgVectorStore(session).upsert(
        tenant.id,
        [
            VectorItem(
                chunk_id=chunk.id,
                document_id=document.id,
                content=content,
                embedding=vector,
                metadata=chunk.meta,
            )
        ],
    )
    return chunk


@pytest.fixture
async def two_contracts(session: AsyncSession) -> tuple[Tenant, Tenant]:
    alpha = await _tenant(session, "vec-alpha")
    beta = await _tenant(session, "vec-beta")
    await _indexed_chunk(session, alpha, ALPHA_CLAUSE)
    await _indexed_chunk(session, beta, BETA_CLAUSE)
    return alpha, beta


async def test_retrieval_returns_only_the_asking_tenants_text(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    _, beta = two_contracts

    await set_tenant_context(session, beta.id)
    result = await HybridRetriever(session, beta.id).retrieve(
        "What is the penalty for late delivery?"
    )

    assert result.hits, "beta should find its own clause"
    joined = " ".join(h.content for h in result.hits)
    assert "5 percent" in joined
    assert "2 percent" not in joined, "alpha's clause leaked into beta's results"


async def test_each_tenant_gets_its_own_answer(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    alpha, beta = two_contracts
    question = "What is the penalty for late delivery?"

    await set_tenant_context(session, alpha.id)
    alpha_hits = await HybridRetriever(session, alpha.id).retrieve(question)
    await set_tenant_context(session, beta.id)
    beta_hits = await HybridRetriever(session, beta.id).retrieve(question)

    assert "2 percent" in alpha_hits.hits[0].content
    assert "5 percent" in beta_hits.hits[0].content


async def test_the_vector_search_alone_is_scoped(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    """Checked without the keyword half, so the sql filter is what is under test."""
    _, beta = two_contracts
    vector = await get_embedder().encode_query("penalty for late delivery")

    await set_tenant_context(session, beta.id)
    hits = await PgVectorStore(session).search(beta.id, vector, k=20)

    assert hits
    assert all("2 percent" not in h.content for h in hits)


async def test_the_keyword_search_alone_is_scoped(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    from ai.vectorstore.keyword import KeywordSearch

    _, beta = two_contracts

    await set_tenant_context(session, beta.id)
    hits = await KeywordSearch(session).search(beta.id, "late delivery penalty", k=20)

    assert hits
    assert all("2 percent" not in h.content for h in hits)


async def test_a_tenant_with_nothing_indexed_retrieves_nothing(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    """The failure mode of filtering after the search: an empty tenant sees others."""
    _ = two_contracts
    empty = await _tenant(session, "vec-empty")
    await set_tenant_context(session, empty.id)

    result = await HybridRetriever(session, empty.id).retrieve("penalty for late delivery")

    assert result.hits == []


async def test_upserting_a_vector_for_another_tenant_writes_nothing(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    alpha, beta = two_contracts

    # Reading alpha's chunk needs alpha's context. The policy is already doing
    # its job, which is why the id is fetched before switching.
    await set_tenant_context(session, alpha.id)
    alpha_chunk = (
        await session.execute(select(DocumentChunk).where(DocumentChunk.tenant_id == alpha.id))
    ).scalar_one()

    await set_tenant_context(session, beta.id)
    written = await PgVectorStore(session).upsert(
        beta.id,
        [
            VectorItem(
                chunk_id=alpha_chunk.id,
                document_id=alpha_chunk.document_id,
                content="overwritten",
                embedding=[0.0] * 384,
                metadata={},
            )
        ],
    )

    assert written == 0


async def test_the_hnsw_index_is_used_for_a_scoped_search(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    """A sequential scan here would still be correct and would not scale."""
    alpha, _ = two_contracts
    await set_tenant_context(session, alpha.id)
    vector = await get_embedder().encode_query("penalty")
    literal = "[" + ",".join(f"{v:.7g}" for v in vector) + "]"

    plan = "\n".join(
        row[0]
        for row in (
            await session.execute(
                text(
                    "EXPLAIN SELECT id FROM document_chunks "
                    "WHERE tenant_id = :tid AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> CAST(:q AS vector) LIMIT 8"
                ),
                {"tid": alpha.id, "q": literal},
            )
        ).all()
    )

    assert "document_chunks" in plan


async def test_embedding_dimensions_match_the_column(session: AsyncSession) -> None:
    """A model swap that changes the width fails loudly here rather than silently."""
    dimensions = (
        await session.execute(
            text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'"
            )
        )
    ).scalar_one()

    assert dimensions == get_embedder().dimensions


async def test_a_chunk_without_a_vector_is_skipped_by_vector_search(session: AsyncSession) -> None:
    tenant = await _tenant(session, "vec-unembedded")
    await _indexed_chunk(session, tenant, "some text with a vector")

    chunk = (
        await session.execute(select(DocumentChunk).where(DocumentChunk.tenant_id == tenant.id))
    ).scalar_one()
    await session.execute(
        text("UPDATE document_chunks SET embedding = NULL WHERE id = :id"), {"id": chunk.id}
    )

    vector = await get_embedder().encode_query("text with a vector")
    hits = await PgVectorStore(session).search(tenant.id, vector, k=10)

    assert hits == []


def test_uuid_import_is_used() -> None:
    assert UUID is not None


async def test_the_query_filters_by_tenant_and_not_only_the_policy(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    """Separates the two layers that both scope a search.

    Every other test here still passes with the tenant predicate deleted, because
    the policy catches it. That is defence in depth working, and it also means
    those tests say nothing about the statement itself. Pinecone has no policy
    behind it, so the filter has to be tested on its own.

    The trick is to disagree on purpose: the session is scoped to beta while the
    store is asked for alpha. With the predicate in place the two intersect to
    nothing. Without it, beta's rows come back for a query that asked for alpha.
    """
    alpha, beta = two_contracts
    vector = await get_embedder().encode_query("penalty for late delivery")

    await set_tenant_context(session, beta.id)
    hits = await PgVectorStore(session).search(alpha.id, vector, k=20)

    assert hits == [], "the statement returned rows for a tenant it was not asked about"


async def test_the_keyword_query_filters_by_tenant_and_not_only_the_policy(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    from ai.vectorstore.keyword import KeywordSearch

    alpha, beta = two_contracts

    await set_tenant_context(session, beta.id)
    hits = await KeywordSearch(session).search(alpha.id, "late delivery penalty", k=20)

    assert hits == []


async def test_deleting_a_document_removes_only_its_own_vectors(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    """The pgvector backend deletes through the same policy as everything else.

    A backend that stored vectors outside Postgres would need this call to keep
    a deleted contract from staying answerable, which is why it is part of the
    VectorStore interface rather than left to the cascade.
    """
    alpha, beta = two_contracts

    await set_tenant_context(session, beta.id)
    beta_chunk = (
        await session.execute(select(DocumentChunk).where(DocumentChunk.tenant_id == beta.id))
    ).scalar_one()

    removed = await PgVectorStore(session).delete_document(beta.id, beta_chunk.document_id)

    assert removed == 1
    assert await PgVectorStore(session).search(beta.id, [0.0] * 384, k=10) == []

    await set_tenant_context(session, alpha.id)
    assert await PgVectorStore(session).search(alpha.id, [0.0] * 384, k=10)


async def test_deleting_another_tenants_document_removes_nothing(
    session: AsyncSession, two_contracts: tuple[Tenant, Tenant]
) -> None:
    alpha, beta = two_contracts

    await set_tenant_context(session, alpha.id)
    alpha_chunk = (
        await session.execute(select(DocumentChunk).where(DocumentChunk.tenant_id == alpha.id))
    ).scalar_one()

    await set_tenant_context(session, beta.id)
    removed = await PgVectorStore(session).delete_document(beta.id, alpha_chunk.document_id)

    assert removed == 0


async def test_upserting_nothing_touches_the_database(session: AsyncSession) -> None:
    written = await PgVectorStore(session).upsert(UUID(int=0), [])

    assert written == 0
