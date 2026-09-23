"""Upload validation and the ingestion job, end to end.

The job is called directly rather than through arq: what matters here is that
parsing, chunking and the manifest import do the right thing, not that redis
delivers a message.
"""

from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.models import Document, DocumentChunk, Shipment
from app.models.enums import DocStatus
from worker.tasks import process_document

pytestmark = pytest.mark.integration

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples"
CONTRACT = SAMPLES / "contract_acme_supply_2026.pdf"
MANIFEST = SAMPLES / "manifest_acme_q1.csv"

OWNER = {
    "company_name": "Ingest Freight",
    "tenant_slug": "ingest-freight",
    "email": "admin@ingest.test",
    "password": "ingest password 1",
    "full_name": "Ingest Admin",
}


@pytest.fixture
async def worker_session(conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the worker at the test transaction.

    The job opens its own session, which would not see rows the test has not
    committed, and would write rows the rollback never removes.
    """
    maker = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    monkeypatch.setattr("worker.db.SessionLocal", maker)


async def _token(api: AsyncClient) -> str:
    response = await api.post("/api/v1/auth/signup", json=OWNER)
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _upload(api: AsyncClient, token: str, path: Path, doc_type: str) -> dict:
    with path.open("rb") as handle:
        response = await api.post(
            "/api/v1/documents",
            files={"file": (path.name, handle, "application/octet-stream")},
            data={"doc_type": doc_type},
            headers=_auth(token),
        )
    assert response.status_code == 202, response.text
    return dict(response.json())


async def _run_job(session: AsyncSession, tenant_id: str, document_id: str) -> dict:
    return await process_document({}, tenant_id, document_id)


async def _tenant_of(session: AsyncSession, document_id: str) -> str:
    row = (
        await session.execute(select(Document.tenant_id).where(Document.id == document_id))
    ).scalar_one()
    return str(row)


async def test_upload_is_accepted_and_queued(api: AsyncClient) -> None:
    token = await _token(api)

    accepted = await _upload(api, token, CONTRACT, "contract")

    assert accepted["status"] == DocStatus.PENDING
    listed = await api.get("/api/v1/documents", headers=_auth(token))
    assert listed.json()["total"] == 1


async def test_the_object_key_is_server_generated(api: AsyncClient, session: AsyncSession) -> None:
    """The client's filename never reaches the object store."""
    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")

    document = (
        await session.execute(select(Document).where(Document.id == accepted["document_id"]))
    ).scalar_one()

    assert CONTRACT.name not in document.s3_key
    assert document.s3_key == f"{document.tenant_id}/{document.id}.pdf"
    assert document.filename == CONTRACT.name


async def test_a_file_that_is_not_a_pdf_is_rejected(api: AsyncClient, tmp_path: Path) -> None:
    token = await _token(api)
    fake = tmp_path / "definitely.pdf"
    fake.write_bytes(b"MZ\x90\x00 this is a windows executable")

    with fake.open("rb") as handle:
        response = await api.post(
            "/api/v1/documents",
            files={"file": ("definitely.pdf", handle, "application/pdf")},
            data={"doc_type": "contract"},
            headers=_auth(token),
        )

    assert response.status_code == 400
    assert "pdf" in response.json()["message"].lower()


async def test_an_empty_file_is_rejected(api: AsyncClient, tmp_path: Path) -> None:
    token = await _token(api)
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")

    with empty.open("rb") as handle:
        response = await api.post(
            "/api/v1/documents",
            files={"file": ("empty.pdf", handle, "application/pdf")},
            data={"doc_type": "contract"},
            headers=_auth(token),
        )

    assert response.status_code == 400


async def test_an_oversized_file_is_rejected(
    api: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    token = await _token(api)
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF-" + b"0" * 5000)

    with big.open("rb") as handle:
        response = await api.post(
            "/api/v1/documents",
            files={"file": ("big.pdf", handle, "application/pdf")},
            data={"doc_type": "contract"},
            headers=_auth(token),
        )

    assert response.status_code == 413


async def test_an_unknown_doc_type_is_rejected(api: AsyncClient) -> None:
    token = await _token(api)

    with CONTRACT.open("rb") as handle:
        response = await api.post(
            "/api/v1/documents",
            files={"file": (CONTRACT.name, handle, "application/pdf")},
            data={"doc_type": "blueprint"},
            headers=_auth(token),
        )

    assert response.status_code == 422


async def test_a_contract_is_parsed_into_chunks(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")
    tenant = await _tenant_of(session, accepted["document_id"])

    result = await _run_job(session, tenant, accepted["document_id"])

    assert result["status"] == "indexed"
    assert result["chunks"] > 5

    fetched = await api.get(f"/api/v1/documents/{accepted['document_id']}", headers=_auth(token))
    assert fetched.json()["status"] == DocStatus.INDEXED
    assert fetched.json()["page_count"] == 2


async def test_a_clause_a_question_would_ask_about_stays_in_one_chunk(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")
    tenant = await _tenant_of(session, accepted["document_id"])
    await _run_job(session, tenant, accepted["document_id"])

    chunks = (
        await api.get(
            f"/api/v1/documents/{accepted['document_id']}/chunks?size=100",
            headers=_auth(token),
        )
    ).json()["items"]

    penalty = [c for c in chunks if "2 percent" in c["content"]]
    assert penalty, "the late delivery penalty is not in any chunk"
    assert "capped at 10 percent" in penalty[0]["content"], "the clause was cut in half"
    assert penalty[0]["meta"]["section"].startswith("4.2")


async def test_running_the_job_twice_does_not_double_the_chunks(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    """Redis delivers at least once, so the job has to be safe to repeat."""
    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")
    tenant = await _tenant_of(session, accepted["document_id"])

    first = await _run_job(session, tenant, accepted["document_id"])
    second = await _run_job(session, tenant, accepted["document_id"])

    count = (
        await session.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == accepted["document_id"])
        )
    ).scalar_one()

    assert first["chunks"] == second["chunks"] == count


async def test_a_manifest_becomes_shipments(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    """Structured data belongs in the table, not only in the index."""
    token = await _token(api)
    accepted = await _upload(api, token, MANIFEST, "manifest")
    tenant = await _tenant_of(session, accepted["document_id"])

    result = await _run_job(session, tenant, accepted["document_id"])

    assert result["imported_rows"] == 42
    assert len(result["skipped_rows"]) == 3

    listed = await api.get("/api/v1/shipments?size=1", headers=_auth(token))
    assert listed.json()["total"] == 42


async def test_bad_rows_are_reported_rather_than_failing_the_upload(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    token = await _token(api)
    accepted = await _upload(api, token, MANIFEST, "manifest")
    tenant = await _tenant_of(session, accepted["document_id"])

    result = await _run_job(session, tenant, accepted["document_id"])

    reasons = {row["reason"] for row in result["skipped_rows"]}
    assert result["status"] == "indexed"
    assert reasons, "a skipped row should say why"
    assert all("line" in row for row in result["skipped_rows"])


async def test_reimporting_a_manifest_does_not_duplicate_shipments(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    token = await _token(api)
    first = await _upload(api, token, MANIFEST, "manifest")
    tenant = await _tenant_of(session, first["document_id"])
    await _run_job(session, tenant, first["document_id"])

    second = await _upload(api, token, MANIFEST, "manifest")
    result = await _run_job(session, tenant, second["document_id"])

    total = (
        await session.execute(
            select(func.count()).select_from(Shipment).where(Shipment.tenant_id == tenant)
        )
    ).scalar_one()

    assert result["imported_rows"] == 0
    assert total == 42


async def test_a_manifest_row_with_an_arrival_after_the_estimate_is_marked_delayed(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    token = await _token(api)
    accepted = await _upload(api, token, MANIFEST, "manifest")
    tenant = await _tenant_of(session, accepted["document_id"])
    await _run_job(session, tenant, accepted["document_id"])

    rows = (
        (
            await session.execute(
                select(Shipment).where(Shipment.tenant_id == tenant, Shipment.ata.is_not(None))
            )
        )
        .scalars()
        .all()
    )

    assert rows
    for shipment in rows:
        expected = "delayed" if shipment.ata and shipment.ata > shipment.eta else "delivered"
        assert shipment.status.value == expected, shipment.reference


async def test_a_scanned_pdf_fails_with_something_a_user_can_read(
    api: AsyncClient, session: AsyncSession, worker_session: None, tmp_path: Path
) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    blank = tmp_path / "scan.pdf"
    page = canvas.Canvas(str(blank), pagesize=A4)
    page.drawString(10, 10, " ")
    page.showPage()
    page.save()

    token = await _token(api)
    accepted = await _upload(api, token, blank, "contract")
    tenant = await _tenant_of(session, accepted["document_id"])

    result = await _run_job(session, tenant, accepted["document_id"])

    assert result["status"] == "failed"
    assert "scanned" in result["error"].lower()

    fetched = await api.get(f"/api/v1/documents/{accepted['document_id']}", headers=_auth(token))
    assert fetched.json()["status"] == DocStatus.FAILED
    assert "traceback" not in (fetched.json()["error"] or "").lower()


async def test_another_tenant_cannot_see_the_document(api: AsyncClient) -> None:
    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")

    other = await api.post(
        "/api/v1/auth/signup",
        json={**OWNER, "tenant_slug": "other-freight", "email": "admin@other.test"},
    )
    other_token = other.json()["access_token"]

    for path in ("", "/chunks", "/download"):
        response = await api.get(
            f"/api/v1/documents/{accepted['document_id']}{path}",
            headers=_auth(other_token),
        )
        assert response.status_code == 404, path


async def test_a_viewer_cannot_upload(api: AsyncClient) -> None:
    admin = await _token(api)
    created = await api.post(
        "/api/v1/users",
        json={
            "email": "viewer@ingest.test",
            "password": "viewer password 1",
            "full_name": "Ingest Viewer",
            "role": "viewer",
        },
        headers=_auth(admin),
    )
    assert created.status_code == 201, created.text
    login = await api.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": OWNER["tenant_slug"],
            "email": "viewer@ingest.test",
            "password": "viewer password 1",
        },
    )
    viewer = login.json()["access_token"]

    with CONTRACT.open("rb") as handle:
        response = await api.post(
            "/api/v1/documents",
            files={"file": (CONTRACT.name, handle, "application/pdf")},
            data={"doc_type": "contract"},
            headers=_auth(viewer),
        )

    assert response.status_code == 403


async def test_a_download_link_is_time_limited(api: AsyncClient) -> None:
    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")

    link = await api.get(
        f"/api/v1/documents/{accepted['document_id']}/download", headers=_auth(token)
    )

    body = link.json()
    assert body["expires_in"] == 300
    assert "X-Amz-Expires" in body["url"] or "Expires" in body["url"]


async def test_a_manifest_summary_chunk_is_written_for_retrieval(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    """The rows go to sql; one summary makes the file findable by a question."""
    token = await _token(api)
    accepted = await _upload(api, token, MANIFEST, "manifest")
    tenant = await _tenant_of(session, accepted["document_id"])
    await _run_job(session, tenant, accepted["document_id"])

    chunks = (
        await api.get(f"/api/v1/documents/{accepted['document_id']}/chunks", headers=_auth(token))
    ).json()["items"]

    assert len(chunks) == 1
    assert chunks[0]["meta"]["section"] == "summary"
    assert "42 shipments" in chunks[0]["content"]
    assert str(date.today().year) in chunks[0]["content"] or "20" in chunks[0]["content"]


async def test_the_embedding_job_writes_vectors(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    """Guards the gap between a chunk existing and being searchable.

    Without this the ingest job can report success while every chunk stays
    unvectorised, and retrieval silently returns nothing.
    """
    from sqlalchemy import func

    from worker.tasks import embed_document

    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")
    tenant = await _tenant_of(session, accepted["document_id"])
    await _run_job(session, tenant, accepted["document_id"])

    result = await embed_document({}, tenant, accepted["document_id"])

    assert result["status"] == "embedded"
    assert result["embedded"] > 0

    unvectorised = (
        await session.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.document_id == accepted["document_id"],
                DocumentChunk.embedding.is_(None),
            )
        )
    ).scalar_one()
    assert unvectorised == 0

    document = (
        await session.execute(select(Document).where(Document.id == accepted["document_id"]))
    ).scalar_one()
    assert document.embedding_model
    assert document.embedding_dim == 384


async def test_running_the_embedding_job_twice_embeds_nothing_new(
    api: AsyncClient, session: AsyncSession, worker_session: None
) -> None:
    from worker.tasks import embed_document

    token = await _token(api)
    accepted = await _upload(api, token, CONTRACT, "contract")
    tenant = await _tenant_of(session, accepted["document_id"])
    await _run_job(session, tenant, accepted["document_id"])

    first = await embed_document({}, tenant, accepted["document_id"])
    second = await embed_document({}, tenant, accepted["document_id"])

    assert first["embedded"] > 0
    assert second["embedded"] == 0, "a repeat run should find nothing left to do"
