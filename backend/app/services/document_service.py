from collections.abc import Sequence
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.storage import PRESIGN_TTL_S, get_store
from app.core.uploads import build_key, read_and_validate, safe_filename
from app.models import Document, DocumentChunk, User
from app.models.enums import DocStatus, DocType
from app.repositories.document_repo import DocumentRepository
from app.schemas.document import DocumentFilters

log = get_logger(__name__)

PROCESS_TASK = "process_document"


class DocumentService:
    def __init__(self, session: AsyncSession, queue: ArqRedis | None, tenant_id: UUID) -> None:
        self.session = session
        self.queue = queue
        self.tenant_id = tenant_id
        self.repo = DocumentRepository(session, tenant_id)

    async def upload(
        self, upload: UploadFile, doc_type: DocType, *, user: User, request_id: str = ""
    ) -> Document:
        data, content_type = await read_and_validate(upload, doc_type)

        document_id = UUID(str(uuid7()))
        key = build_key(self.tenant_id, document_id, doc_type)

        # The bucket is ensured at startup, not here: readiness checks it, and a
        # pod that is not ready never receives an upload to create it with.
        await get_store().put(key, data, content_type)

        document = Document(
            id=document_id,
            tenant_id=self.tenant_id,
            uploaded_by=user.id,
            filename=safe_filename(upload.filename),
            content_type=content_type,
            size_bytes=len(data),
            s3_key=key,
            doc_type=doc_type,
            status=DocStatus.PENDING,
        )
        self.session.add(document)
        await self.session.flush()

        document.job_id = await self._enqueue(document_id, request_id)
        await self.session.flush()

        log.info(
            "document.uploaded",
            tenant_id=str(self.tenant_id),
            document_id=str(document_id),
            doc_type=doc_type,
            size_bytes=len(data),
            request_id=request_id,
        )
        return document

    async def reprocess(self, document_id: UUID, *, request_id: str = "") -> Document:
        document = await self.get(document_id)
        document.status = DocStatus.PENDING
        document.error = None
        document.job_id = await self._enqueue(document_id, request_id)
        await self.session.flush()
        return document

    async def search(self, filters: DocumentFilters) -> tuple[Sequence[Document], int]:
        return await self.repo.search(filters)

    async def get(self, document_id: UUID) -> Document:
        document = await self.repo.get(document_id)
        if document is None:
            raise NotFoundError("Document not found")
        return document

    async def chunks(
        self, document_id: UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[DocumentChunk], int]:
        await self.get(document_id)
        return await self.repo.chunks(document_id, limit=limit, offset=offset)

    async def download_url(self, document_id: UUID) -> tuple[str, int]:
        document = await self.get(document_id)
        url = await get_store().presigned_url(document.s3_key)
        return url, PRESIGN_TTL_S

    async def delete(self, document_id: UUID) -> None:
        document = await self.get(document_id)
        key = document.s3_key
        await self.repo.delete(document_id)
        await get_store().delete(key)

    async def _enqueue(self, document_id: UUID, request_id: str) -> str | None:
        if self.queue is None:
            # No worker configured, for example in a test that only checks upload.
            return None
        job = await self.queue.enqueue_job(
            PROCESS_TASK, str(self.tenant_id), str(document_id), request_id
        )
        return job.job_id if job else None
