"""Citations map an answer back to the chunk it came from."""

from uuid import uuid4

from ai.rag.prompts import MAX_CONTEXT_CHARS, build_context, parse_citations
from ai.vectorstore.base import SearchHit


def _hit(content: str, **meta: object) -> SearchHit:
    return SearchHit(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content=content,
        score=0.9,
        metadata=meta,
    )


def test_context_numbers_every_source() -> None:
    context, sources = build_context([_hit("first"), _hit("second")])

    assert "[1]" in context
    assert "[2]" in context
    assert [s.number for s in sources] == [1, 2]


def test_the_header_carries_where_the_text_came_from() -> None:
    context, _ = build_context(
        [_hit("clause text", filename="contract.pdf", page_no=4, section="4.2 Late Delivery")]
    )

    assert "contract.pdf" in context
    assert "page 4" in context
    assert "4.2 Late Delivery" in context


def test_context_is_capped() -> None:
    context, sources = build_context([_hit("x" * 4000) for _ in range(10)])

    assert len(context) <= MAX_CONTEXT_CHARS + 200
    assert len(sources) < 10


def test_only_cited_sources_come_back() -> None:
    _, sources = build_context([_hit("a"), _hit("b"), _hit("c")])

    citations = parse_citations("The answer is in [2].", sources)

    assert [c.number for c in citations] == [2]


def test_citations_keep_the_order_they_appear_in() -> None:
    _, sources = build_context([_hit("a"), _hit("b"), _hit("c")])

    citations = parse_citations("First [3], then [1].", sources)

    assert [c.number for c in citations] == [3, 1]


def test_a_repeated_citation_is_listed_once() -> None:
    _, sources = build_context([_hit("a"), _hit("b")])

    assert len(parse_citations("[1] and again [1].", sources)) == 1


def test_a_citation_that_does_not_exist_is_dropped() -> None:
    """A model will write [9] when it was handed three sources."""
    _, sources = build_context([_hit("a"), _hit("b"), _hit("c")])

    citations = parse_citations("According to [9] and [2].", sources)

    assert [c.number for c in citations] == [2]


def test_an_answer_with_no_citations_returns_none() -> None:
    _, sources = build_context([_hit("a")])

    assert parse_citations("I could not find this in the indexed documents.", sources) == []
