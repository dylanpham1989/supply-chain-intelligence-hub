"""The question endpoint, on the mock provider.

The mock needs no key, so this runs anywhere the database does, and a failure
here points at retrieval or at the pipeline rather than at a model.
"""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.embeddings.hf_embedder import get_embedder
from ai.vectorstore.base import VectorItem
from ai.vectorstore.pgvector_store import PgVectorStore
from app.models import Document, DocumentChunk, Tenant
from app.models.enums import DocStatus, DocType

pytestmark = pytest.mark.integration

OWNER = {
    "company_name": "Ask Freight",
    "tenant_slug": "ask-freight",
    "email": "admin@ask.test",
    "password": "asking password",
    "full_name": "Ask Admin",
}

PENALTY_CLAUSE = (
    "4.2 Late Delivery. Where a shipment arrives after the confirmed estimated time of "
    "arrival, the Supplier shall pay a penalty of 2 percent of the shipment value for each "
    "complete week of delay, capped at 10 percent of the order value."
)
PAYMENT_CLAUSE = (
    "6. Payment. Payment terms are 60 days from the date of a valid invoice. Invoices shall "
    "quote the purchase order number and the shipment reference."
)


async def _token(api: AsyncClient) -> str:
    response = await api.post("/api/v1/auth/signup", json=OWNER)
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _index(session: AsyncSession, slug: str, clauses: list[str]) -> None:
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()

    document = Document(
        tenant_id=tenant.id,
        filename="contract.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        s3_key=f"{tenant.id}/contract.pdf",
        doc_type=DocType.CONTRACT,
        status=DocStatus.INDEXED,
    )
    session.add(document)
    await session.flush()

    store = PgVectorStore(session)
    embedder = get_embedder()
    vectors = await embedder.encode(clauses)

    for index, (content, vector) in enumerate(zip(clauses, vectors, strict=True)):
        chunk = DocumentChunk(
            tenant_id=tenant.id,
            document_id=document.id,
            chunk_index=index,
            content=content,
            meta={
                "doc_type": "contract",
                "filename": "contract.pdf",
                "page_no": 1,
                "section": content.split(".")[0],
            },
        )
        session.add(chunk)
        await session.flush()
        await store.upsert(
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


async def test_a_question_about_a_clause_is_answered_with_a_citation(
    api: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(api)
    await _index(session, OWNER["tenant_slug"], [PENALTY_CLAUSE, PAYMENT_CLAUSE])

    response = await api.post(
        "/api/v1/ask",
        json={"question": "What is the penalty for late delivery?"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "semantic"
    assert "2 percent" in body["answer"]
    assert body["citations"], "an answer from context should cite it"
    assert body["citations"][0]["filename"] == "contract.pdf"
    assert body["citations"][0]["section"].startswith("4")


async def test_a_question_with_nothing_indexed_says_so(api: AsyncClient) -> None:
    token = await _token(api)

    response = await api.post(
        "/api/v1/ask",
        json={"question": "What is the penalty for late delivery?"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "I could not find this in the indexed documents."
    assert response.json()["citations"] == []


async def test_an_aggregate_question_goes_to_sql(api: AsyncClient, session: AsyncSession) -> None:
    """Retrieval returns the top k, which is the wrong shape for a count."""
    token = await _token(api)
    for i in range(3):
        created = await api.post(
            "/api/v1/shipments",
            json={
                "reference": f"ASK-{i}",
                "origin_country": "CN",
                "dest_country": "DE",
                "mode": "ocean",
                "qty": 1,
                "value_usd": "100.00",
                "eta": str(date(2026, 1, 10)),
                "ata": str(date(2026, 1, 20)),
                "status": "delayed",
            },
            headers=_auth(token),
        )
        assert created.status_code == 201, created.text

    response = await api.post(
        "/api/v1/ask",
        json={"question": "How many shipments were delayed?"},
        headers=_auth(token),
    )

    body = response.json()
    assert body["route"] == "structured"
    assert len(body["shipments"]) == 3
    assert "3 shipments match" in body["answer"]


async def test_a_region_in_the_question_is_expanded(
    api: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(api)

    response = await api.post(
        "/api/v1/ask",
        json={"question": "Show all late deliveries to the EU"},
        headers=_auth(token),
    )

    body = response.json()
    assert body["route"] == "structured"
    assert len(body["filters"]["dest_countries"]) == 27


async def test_the_question_is_recorded(api: AsyncClient, session: AsyncSession) -> None:
    token = await _token(api)
    await _index(session, OWNER["tenant_slug"], [PENALTY_CLAUSE])

    await api.post(
        "/api/v1/ask",
        json={"question": "What is the penalty for late delivery?"},
        headers=_auth(token),
    )
    history = await api.get("/api/v1/insights", headers=_auth(token))

    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["question"] == "What is the penalty for late delivery?"
    assert items[0]["model"] == "mock-extractive"
    assert items[0]["latency_ms"] is not None


async def test_only_the_asking_tenant_sees_its_history(api: AsyncClient) -> None:
    token = await _token(api)
    await api.post("/api/v1/ask", json={"question": "anything at all"}, headers=_auth(token))

    other = await api.post(
        "/api/v1/auth/signup",
        json={**OWNER, "tenant_slug": "ask-other", "email": "admin@ask-other.test"},
    )
    other_token = other.json()["access_token"]

    history = await api.get("/api/v1/insights", headers=_auth(other_token))

    assert history.json()["total"] == 0


async def test_a_viewer_cannot_ask(api: AsyncClient) -> None:
    admin = await _token(api)
    created = await api.post(
        "/api/v1/users",
        json={
            "email": "viewer@ask.test",
            "password": "viewer password 1",
            "full_name": "Ask Viewer",
            "role": "viewer",
        },
        headers=_auth(admin),
    )
    assert created.status_code == 201
    login = await api.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": OWNER["tenant_slug"],
            "email": "viewer@ask.test",
            "password": "viewer password 1",
        },
    )

    response = await api.post(
        "/api/v1/ask",
        json={"question": "what is the penalty"},
        headers=_auth(login.json()["access_token"]),
    )

    assert response.status_code == 403


async def test_a_question_that_is_too_long_is_refused(api: AsyncClient) -> None:
    token = await _token(api)

    response = await api.post("/api/v1/ask", json={"question": "x" * 2000}, headers=_auth(token))

    assert response.status_code == 422


async def test_an_unknown_field_is_refused(api: AsyncClient) -> None:
    token = await _token(api)

    response = await api.post(
        "/api/v1/ask",
        json={"question": "what is the penalty", "tenant_id": "someone-else"},
        headers=_auth(token),
    )

    assert response.status_code == 422


async def test_a_provider_outage_is_not_a_five_hundred(
    api: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai.llm.base import LLMUnavailableError
    from ai.llm.mock import MockProvider

    token = await _token(api)
    await _index(session, OWNER["tenant_slug"], [PENALTY_CLAUSE])

    async def explode(*args: object, **kwargs: object) -> None:
        raise LLMUnavailableError("provider is down")

    monkeypatch.setattr(MockProvider, "complete", explode)

    response = await api.post(
        "/api/v1/ask",
        json={"question": "What is the penalty for late delivery?"},
        headers=_auth(token),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
