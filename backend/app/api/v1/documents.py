from typing import Annotated
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status

from app.core.context import current_request_id
from app.core.deps import DbSession, get_current_user, require
from app.models import User
from app.models.enums import DocType
from app.schemas.common import Page
from app.schemas.document import (
    ChunkRead,
    DocumentAccepted,
    DocumentFilterQuery,
    DocumentRead,
    DownloadLink,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


def get_queue(request: Request) -> ArqRedis | None:
    queue: ArqRedis | None = getattr(request.app.state, "queue", None)
    return queue


def _service(
    session: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    queue: Annotated[ArqRedis | None, Depends(get_queue)],
) -> DocumentService:
    return DocumentService(session, queue, user.tenant_id)


Service = Annotated[DocumentService, Depends(_service)]
Reader = Annotated[User, Depends(require("document:read"))]
Uploader = Annotated[User, Depends(require("document:upload"))]
Remover = Annotated[User, Depends(require("document:delete"))]


@router.post("", response_model=DocumentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    service: Service,
    user: Uploader,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[DocType, Form()],
) -> DocumentAccepted:
    """Accepts the file and hands it to a worker.

    Parsing a large pdf takes tens of seconds, which is longer than a client or
    a proxy will wait, and a failed request would lose the upload entirely.
    """
    # The middleware already generated one if the caller did not send one.
    request_id = current_request_id()
    document = await service.upload(file, doc_type, user=user, request_id=request_id)
    return DocumentAccepted(document_id=document.id, status=document.status, job_id=document.job_id)


@router.get("", response_model=Page[DocumentRead])
async def list_documents(
    filters: DocumentFilterQuery, service: Service, _: Reader
) -> Page[DocumentRead]:
    rows, total = await service.search(filters)
    return Page[DocumentRead](
        items=[DocumentRead.model_validate(d) for d in rows],
        total=total,
        page=filters.page,
        size=filters.size,
    )


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, service: Service, _: Reader) -> DocumentRead:
    return DocumentRead.model_validate(await service.get(document_id))


@router.get("/{document_id}/chunks", response_model=Page[ChunkRead])
async def get_chunks(
    document_id: UUID,
    service: Service,
    _: Reader,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[ChunkRead]:
    rows, total = await service.chunks(document_id, limit=size, offset=(page - 1) * size)
    return Page[ChunkRead](
        items=[ChunkRead.model_validate(c) for c in rows], total=total, page=page, size=size
    )


@router.get("/{document_id}/download", response_model=DownloadLink)
async def download_document(document_id: UUID, service: Service, _: Reader) -> DownloadLink:
    url, ttl = await service.download_url(document_id)
    return DownloadLink(url=url, expires_in=ttl)


@router.post("/{document_id}/reprocess", response_model=DocumentAccepted)
async def reprocess_document(document_id: UUID, service: Service, _: Uploader) -> DocumentAccepted:
    document = await service.reprocess(document_id, request_id=current_request_id())
    return DocumentAccepted(document_id=document.id, status=document.status, job_id=document.job_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, service: Service, _: Remover) -> Response:
    await service.delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
