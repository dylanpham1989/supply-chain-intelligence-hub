from collections.abc import Sequence
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm.base import LLMUnavailableError
from ai.rag.pipeline import Answer, RagPipeline
from ai.rag.structured import ShipmentQueryFilter
from app.core import ratelimit
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.models import Insight, Shipment, Supplier, User
from app.schemas.ask import AskRequest
from app.schemas.common import PaginationParams

log = get_logger(__name__)

# Questions cost money at a hosted provider, so they are capped per tenant
# rather than per user.
ASK_LIMIT = 20
ASK_WINDOW_S = 60
STRUCTURED_PREVIEW = 25


class RagService:
    def __init__(self, session: AsyncSession, redis: Redis, tenant_id: UUID) -> None:
        self.session = session
        self.redis = redis
        self.tenant_id = tenant_id
        self.pipeline = RagPipeline(session, tenant_id)

    async def ask(self, payload: AskRequest, *, user: User) -> tuple[Answer, list[Shipment]]:
        await ratelimit.enforce(
            self.redis, f"rl:ask:{self.tenant_id}", limit=ASK_LIMIT, window_s=ASK_WINDOW_S
        )

        try:
            result = await self.pipeline.answer(
                payload.question,
                k=payload.top_k,
                doc_type=payload.doc_type.value if payload.doc_type else None,
                document_ids=payload.document_ids,
            )
        except LLMUnavailableError as exc:
            # The model being down is not this service being broken.
            log.warning("rag.provider_unavailable", error=str(exc))
            raise ServiceUnavailableError("The language model is unavailable") from exc

        shipments: list[Shipment] = []
        if result.route == "structured":
            shipments = await self._run_filters(result.filters)
            result.answer = _describe_result(shipments, result.filters)

        self.session.add(
            Insight(
                tenant_id=self.tenant_id,
                question=result.question,
                answer=result.answer,
                citations=[
                    {
                        "number": c.number,
                        "chunk_id": str(c.chunk_id),
                        "document_id": str(c.document_id),
                        "filename": c.filename,
                        "page_no": c.page_no,
                        "section": c.section,
                        "score": c.score,
                    }
                    for c in result.citations
                ],
                route=result.route,
                model=result.model,
                latency_ms=result.total_ms,
                token_in=result.token_in,
                token_out=result.token_out,
                created_by=user.id,
            )
        )
        await self.session.flush()
        return result, shipments

    async def history(
        self, filters: PaginationParams, route: str | None = None
    ) -> tuple[Sequence[Insight], int]:
        stmt = select(Insight).where(Insight.tenant_id == self.tenant_id)
        if route:
            stmt = stmt.where(Insight.route == route)
        page = (
            stmt.order_by(Insight.created_at.desc(), Insight.id.desc())
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

    async def _run_filters(self, raw: dict[str, object]) -> list[Shipment]:
        filters = ShipmentQueryFilter.model_validate(raw)
        stmt = select(Shipment).where(Shipment.tenant_id == self.tenant_id)

        if filters.status is not None:
            stmt = stmt.where(Shipment.status == filters.status)
        if filters.mode is not None:
            stmt = stmt.where(Shipment.mode == filters.mode)
        if filters.dest_countries:
            stmt = stmt.where(Shipment.dest_country.in_(filters.dest_countries))
        if filters.origin_countries:
            stmt = stmt.where(Shipment.origin_country.in_(filters.origin_countries))
        if filters.eta_from is not None:
            stmt = stmt.where(Shipment.eta >= filters.eta_from)
        if filters.eta_to is not None:
            stmt = stmt.where(Shipment.eta <= filters.eta_to)
        if filters.late_only:
            stmt = stmt.where(Shipment.ata.is_not(None), Shipment.ata > Shipment.eta)
        if filters.supplier_name:
            stmt = stmt.join(Supplier, Shipment.supplier_id == Supplier.id).where(
                Supplier.name.ilike(f"%{filters.supplier_name}%")
            )

        stmt = stmt.order_by(Shipment.eta.desc()).limit(filters.limit)
        return list((await self.session.execute(stmt)).scalars().all())


def _describe_result(shipments: list[Shipment], filters: dict[str, object]) -> str:
    if not shipments:
        return "No shipments match that question."

    late = sum(1 for s in shipments if s.ata and s.ata > s.eta)
    lanes = sorted({f"{s.origin_country} to {s.dest_country}" for s in shipments})[:6]
    parts = [f"{len(shipments)} shipments match"]
    if filters:
        parts.append("with " + ", ".join(f"{k}={v}" for k, v in filters.items()))
    parts.append(f"{late} of them arrived after the estimate")
    parts.append("lanes: " + ", ".join(lanes))
    return ". ".join(parts) + "."
