import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from ai.embeddings.hf_embedder import get_embedder
from ai.ingestion.base import ParsedDoc, PermanentError, TransientError
from ai.ingestion.chunker import SectionAwareChunker
from ai.ingestion.cleaner import clean_pages
from ai.ingestion.csv_parser import CsvParser
from ai.ingestion.pdf_parser import PdfParser, extract_tables
from ai.vectorstore.base import VectorItem
from ai.vectorstore.pgvector_store import PgVectorStore
from app.core.cache import invalidate_tags
from app.core.logging import get_logger
from app.core.storage import get_store
from app.models import Document, DocumentChunk
from app.models.enums import DocStatus, DocType
from worker.db import tenant_session
from worker.manifest import import_rows

log = get_logger(__name__)

CHUNK_META_VERSION = 1


async def process_document(
    ctx: dict[str, Any], tenant_id: str, document_id: str, request_id: str = ""
) -> dict[str, Any]:
    """Parse an uploaded document into chunks, and manifest rows into shipments.

    Idempotent: chunks are deleted before they are written, so a redelivered job
    replaces its output rather than doubling it.
    """
    tenant = UUID(tenant_id)
    doc_id = UUID(document_id)
    started = time.perf_counter()

    async with tenant_session(tenant) as session:
        document = (
            await session.execute(select(Document).where(Document.id == doc_id))
        ).scalar_one_or_none()
        if document is None:
            log.warning("ingest.document_missing", document_id=document_id)
            return {"status": "missing"}

        document.status = DocStatus.PROCESSING
        document.error = None
        await session.flush()
        s3_key = document.s3_key
        doc_type = document.doc_type
        filename = document.filename

    log.info(
        "ingest.started",
        tenant_id=tenant_id,
        document_id=document_id,
        doc_type=doc_type,
        request_id=request_id,
    )

    try:
        parsed = await _parse(s3_key, doc_type)
    except PermanentError as exc:
        await _fail(tenant, doc_id, str(exc))
        log.warning("ingest.failed", document_id=document_id, error=str(exc))
        return {"status": "failed", "error": str(exc)}
    except TransientError:
        await _fail(tenant, doc_id, "temporary failure, retrying")
        raise

    async with tenant_session(tenant) as session:
        document = (
            await session.execute(select(Document).where(Document.id == doc_id))
        ).scalar_one()

        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))

        chunks = _build_chunks(parsed, doc_type=doc_type, filename=filename)
        for index, (content, meta) in enumerate(chunks):
            session.add(
                DocumentChunk(
                    tenant_id=tenant,
                    document_id=doc_id,
                    chunk_index=index,
                    content=content,
                    token_count=max(1, len(content) // 4),
                    page_no=meta.get("page_no"),
                    meta=meta,
                )
            )

        imported = 0
        skipped_rows: list[dict[str, Any]] = list(parsed.skipped)
        if doc_type == DocType.MANIFEST and parsed.rows:
            imported, extra_skipped = await import_rows(session, tenant, parsed.rows)
            skipped_rows.extend(extra_skipped)

        document.status = DocStatus.INDEXED
        document.page_count = parsed.page_count or None
        document.indexed_at = datetime.now(UTC)
        document.error = None
        await session.flush()

    if imported and ctx.get("redis") is not None:
        # The dashboard is cached, and a job writing shipments is just as much a
        # write as an api call. Without this the numbers sit stale until the ttl.
        await invalidate_tags(ctx["redis"], tenant, ["analytics", "shipments"])

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    log.info(
        "ingest.completed",
        tenant_id=tenant_id,
        document_id=document_id,
        chunks=len(chunks),
        imported_rows=imported,
        skipped_rows=len(skipped_rows),
        duration_ms=elapsed_ms,
        request_id=request_id,
    )

    if ctx.get("redis") is not None:
        await ctx["redis"].enqueue_job("embed_document", tenant_id, document_id)

    return {
        "status": "indexed",
        "chunks": len(chunks),
        "imported_rows": imported,
        "skipped_rows": skipped_rows[:20],
        "duration_ms": elapsed_ms,
    }


EMBED_BATCH = 32


async def embed_document(ctx: dict[str, Any], tenant_id: str, document_id: str) -> dict[str, Any]:
    """Vectorise the chunks that do not have a vector yet.

    Selecting on embedding IS NULL makes this idempotent without any extra
    bookkeeping: a repeat run embeds whatever is still missing and nothing else.
    """
    tenant = UUID(tenant_id)
    doc_id = UUID(document_id)
    started = time.perf_counter()
    embedder = get_embedder()
    embedded = 0

    async with tenant_session(tenant) as session:
        pending = (
            (
                await session.execute(
                    select(DocumentChunk)
                    .where(
                        DocumentChunk.document_id == doc_id,
                        DocumentChunk.embedding.is_(None),
                    )
                    .order_by(DocumentChunk.chunk_index)
                )
            )
            .scalars()
            .all()
        )

        store = PgVectorStore(session)
        for start in range(0, len(pending), EMBED_BATCH):
            batch = pending[start : start + EMBED_BATCH]
            vectors = await embedder.encode([chunk.content for chunk in batch])
            embedded += await store.upsert(
                tenant,
                [
                    VectorItem(
                        chunk_id=chunk.id,
                        document_id=doc_id,
                        content=chunk.content,
                        embedding=vector,
                        metadata=chunk.meta,
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ],
            )

        document = (
            await session.execute(select(Document).where(Document.id == doc_id))
        ).scalar_one_or_none()
        if document is not None:
            # Recorded so a model change is visible rather than showing up as
            # retrieval quietly getting worse.
            document.embedding_model = embedder.model_name
            document.embedding_dim = embedder.dimensions
            await session.flush()

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    log.info(
        "embed.completed",
        tenant_id=tenant_id,
        document_id=document_id,
        embedded=embedded,
        model=embedder.model_name,
        duration_ms=elapsed_ms,
    )
    return {"status": "embedded", "embedded": embedded, "duration_ms": elapsed_ms}


async def _parse(s3_key: str, doc_type: DocType) -> ParsedDoc:
    store = get_store()
    with tempfile.TemporaryDirectory(prefix="scih-ingest-") as tmp:
        local = Path(tmp) / Path(s3_key).name
        await store.download_to(s3_key, local)

        if doc_type == DocType.MANIFEST:
            return CsvParser().parse(local)

        parsed = PdfParser().parse(local)
        thin = list(parsed.meta.get("thin_pages") or [])
        if thin:
            tables = extract_tables(local, thin)
            if tables:
                pages = [
                    (
                        page
                        if page.page_no not in tables
                        else type(page)(
                            page_no=page.page_no,
                            text=page.text,
                            tables=tables[page.page_no],
                        )
                    )
                    for page in parsed.pages
                ]
                parsed = ParsedDoc(pages=pages, meta=parsed.meta)
        return parsed


def _build_chunks(
    parsed: ParsedDoc, *, doc_type: DocType, filename: str
) -> list[tuple[str, dict[str, Any]]]:
    chunker = SectionAwareChunker()
    out: list[tuple[str, dict[str, Any]]] = []

    # Page furniture repeated on every page would otherwise end up in every
    # chunk, which makes them all look faintly alike to an embedding.
    for page in clean_pages(parsed.pages):
        for section, body in chunker.split_sections(page.text):
            for piece in [body] if len(body) <= chunker.max_size else chunker.split(body):
                out.append(
                    (
                        piece,
                        {
                            "v": CHUNK_META_VERSION,
                            "doc_type": doc_type.value,
                            "filename": filename,
                            "page_no": page.page_no,
                            "section": section,
                        },
                    )
                )
        for table in page.tables:
            rendered = "\n".join(" | ".join(cell for cell in row) for row in table)
            if rendered.strip():
                out.append(
                    (
                        rendered,
                        {
                            "v": CHUNK_META_VERSION,
                            "doc_type": doc_type.value,
                            "filename": filename,
                            "page_no": page.page_no,
                            "section": "table",
                        },
                    )
                )

    if doc_type == DocType.MANIFEST and parsed.rows:
        # A manifest belongs in the shipments table. One summary is enough to
        # make it findable by a question; the numbers come from sql.
        summary = _summarise_manifest(parsed, filename)
        out.append(
            (
                summary,
                {
                    "v": CHUNK_META_VERSION,
                    "doc_type": doc_type.value,
                    "filename": filename,
                    "section": "summary",
                },
            )
        )

    return out


def _summarise_manifest(parsed: ParsedDoc, filename: str) -> str:
    rows = [r.data for r in parsed.rows]
    lanes = sorted({f"{r['origin_country']}-{r['dest_country']}" for r in rows})
    etas = sorted(str(r["eta"]) for r in rows)
    total = sum(r["value_usd"] for r in rows)
    return (
        f"Manifest {filename}: {len(rows)} shipments, "
        f"lanes {', '.join(lanes[:12])}, "
        f"arrival dates {etas[0]} to {etas[-1]}, "
        f"total declared value {total} USD."
    )


async def _fail(tenant_id: UUID, document_id: UUID, message: str) -> None:
    async with tenant_session(tenant_id) as session:
        document = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if document is None:
            return
        document.status = DocStatus.FAILED
        document.error = message[:2000]
        await session.flush()
