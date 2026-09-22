from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from app.models import Document, DocumentChunk
from app.repositories.base import TenantRepository
from app.schemas.document import DocumentFilters


class DocumentRepository(TenantRepository[Document]):
    model = Document

    async def search(self, filters: DocumentFilters) -> tuple[Sequence[Document], int]:
        stmt = self._scoped()
        if filters.doc_type is not None:
            stmt = stmt.where(Document.doc_type == filters.doc_type)
        if filters.status is not None:
            stmt = stmt.where(Document.status == filters.status)

        page = (
            stmt.order_by(Document.created_at.desc(), Document.id.desc())
            .limit(filters.size)
            .offset(filters.offset)
        )
        rows = (await self.session.execute(page)).scalars().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
        ).scalar_one()
        return rows, total

    async def chunks(
        self, document_id: UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[DocumentChunk], int]:
        base = select(DocumentChunk).where(
            DocumentChunk.tenant_id == self.tenant_id,
            DocumentChunk.document_id == document_id,
        )
        rows = (
            (
                await self.session.execute(
                    base.order_by(DocumentChunk.chunk_index).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        total = (
            await self.session.execute(
                select(func.count()).select_from(base.order_by(None).subquery())
            )
        ).scalar_one()
        return rows, total
