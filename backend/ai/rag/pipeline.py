import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm.base import LLMProvider, LLMUnavailableError
from ai.llm.factory import get_llm
from ai.rag import prompts
from ai.rag.retriever import TOP_K, HybridRetriever
from ai.rag.router import Route, route
from ai.rag.structured import FILTER_SCHEMA_HINT, describe, expand_regions, parse_filter
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

FILTER_SYSTEM_PROMPT = (
    "You translate a question about shipments into a filter. " + FILTER_SCHEMA_HINT
)


@dataclass
class Answer:
    question: str
    answer: str
    route: str
    citations: list[prompts.Citation] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    token_in: int = 0
    token_out: int = 0
    retrieve_ms: int = 0
    llm_ms: int = 0
    total_ms: int = 0


class RagPipeline:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        llm: LLMProvider | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.retriever = HybridRetriever(session, tenant_id)
        self.llm = llm or get_llm()

    async def answer(
        self,
        question: str,
        *,
        k: int = TOP_K,
        doc_type: str | None = None,
        document_ids: list[UUID] | None = None,
    ) -> Answer:
        started = time.perf_counter()
        chosen = route(question)

        if chosen is Route.STRUCTURED:
            structured = await self._structured_filters(question)
            if structured is not None:
                return Answer(
                    question=question,
                    answer="",
                    route=Route.STRUCTURED.value,
                    filters=describe(structured),
                    model=self.llm.model,
                    total_ms=round((time.perf_counter() - started) * 1000),
                )
            # A filter the model could not produce is better served by retrieval
            # than by an error.
            log.info("rag.route.fallback", question=question[:120])

        retrieved = await self.retriever.retrieve(
            question, k=k, doc_type=doc_type, document_ids=document_ids
        )
        if not retrieved.hits:
            return Answer(
                question=question,
                answer=prompts.NOT_FOUND,
                route=Route.SEMANTIC.value,
                model=self.llm.model,
                retrieve_ms=retrieved.latency_ms,
                total_ms=round((time.perf_counter() - started) * 1000),
            )

        context, sources = prompts.build_context(retrieved.hits)
        response = await self.llm.complete(
            system=prompts.SYSTEM_PROMPT,
            user=prompts.build_user_prompt(context, question),
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

        citations = prompts.parse_citations(response.text, sources)
        total_ms = round((time.perf_counter() - started) * 1000)

        log.info(
            "rag.answered",
            tenant_id=str(self.tenant_id),
            route=Route.SEMANTIC.value,
            hits=len(retrieved.hits),
            citations=len(citations),
            retrieve_ms=retrieved.latency_ms,
            llm_ms=response.latency_ms,
            total_ms=total_ms,
            provider=self.llm.model,
        )

        return Answer(
            question=question,
            answer=response.text,
            route=Route.SEMANTIC.value,
            citations=citations,
            model=response.model,
            token_in=response.token_in,
            token_out=response.token_out,
            retrieve_ms=retrieved.latency_ms,
            llm_ms=response.latency_ms,
            total_ms=total_ms,
        )

    async def _structured_filters(self, question: str) -> Any:
        try:
            response = await self.llm.complete(
                system=FILTER_SYSTEM_PROMPT,
                user=question,
                max_tokens=300,
                temperature=0.0,
            )
        except LLMUnavailableError:
            return None

        parsed = parse_filter(response.text)
        if parsed is None:
            # The mock cannot produce json, and a hosted model sometimes will not
            # either. An empty filter still answers "list all late shipments".
            from ai.rag.structured import ShipmentQueryFilter

            parsed = ShipmentQueryFilter()
        return expand_regions(question, parsed)
