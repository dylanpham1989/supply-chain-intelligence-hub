"""Chunking decides what a question can find.

A clause cut in half is a clause that answers half the question, and nothing
downstream can recover the missing part.
"""

import pytest

from ai.ingestion.chunker import MAX_CHARS, RecursiveChunker, SectionAwareChunker

CONTRACT = """4.1 Measurement
On-time means arrival at the destination on or before the estimated time of arrival
confirmed at the time of booking.
4.2 Late Delivery
Where a shipment arrives after the confirmed estimated time of arrival, the Supplier shall pay a penalty of
2 percent of the shipment value for each complete week of delay, capped at 10 percent of the value of
the affected purchase order.
5. Quality and Inspection
The Buyer may inspect goods within 10 working days of arrival.
"""


def test_short_text_is_one_chunk() -> None:
    assert RecursiveChunker().split("a short clause") == ["a short clause"]


def test_empty_text_produces_nothing() -> None:
    assert RecursiveChunker().split("   \n  ") == []


def test_no_chunk_exceeds_the_maximum() -> None:
    text = " ".join(f"sentence number {i}." for i in range(800))

    chunks = RecursiveChunker().split(text)

    assert chunks
    assert all(len(c) <= MAX_CHARS for c in chunks), [len(c) for c in chunks]


def test_no_chunk_is_blank() -> None:
    text = "\n\n\n".join(f"Paragraph {i} with some words in it." for i in range(60))

    assert all(c.strip() for c in RecursiveChunker().split(text))


def test_chunks_overlap_so_a_split_sentence_survives_whole() -> None:
    chunker = RecursiveChunker(target=200, overlap=60, max_size=400)
    text = " ".join(f"word{i}" for i in range(300))

    chunks = chunker.split(text)

    assert len(chunks) > 1
    tail = chunks[0][-40:].strip()
    assert tail in chunks[1], "the tail of one chunk should reappear in the next"


def test_overlap_must_be_smaller_than_target() -> None:
    with pytest.raises(ValueError, match="overlap"):
        RecursiveChunker(target=100, overlap=100)


def test_numbered_clauses_are_kept_whole() -> None:
    sections = dict(SectionAwareChunker().split_sections(CONTRACT))

    penalty = next(body for label, body in sections.items() if label and label.startswith("4.2"))

    assert "2 percent" in penalty
    assert "capped at 10 percent" in penalty
    assert "affected purchase order" in penalty


def test_a_wrapped_body_line_starting_with_a_number_is_not_a_clause() -> None:
    """This is the bug the uppercase rule exists for.

    "2 percent of the shipment value ..." read as clause 2, which cut the real
    clause in half and dropped the number a reader is looking for.
    """
    labels = [label for label, _ in SectionAwareChunker().split_sections(CONTRACT)]

    assert not any(label and label.startswith("2 percent") for label in labels)
    assert [label for label in labels if label] == [
        "4.1 Measurement",
        "4.2 Late Delivery",
        "5. Quality and Inspection",
    ]


def test_text_with_no_clause_numbers_stays_in_one_section() -> None:
    plain = "Just some prose with no numbering at all, running on for a while."

    assert SectionAwareChunker().split_sections(plain) == [(None, plain)]


def test_a_very_long_clause_is_split_rather_than_returned_oversized() -> None:
    long_clause = "7. Force Majeure\n" + ("Neither party is liable. " * 200)

    chunks = SectionAwareChunker().split(long_clause)

    assert len(chunks) > 1
    assert all(len(c) <= MAX_CHARS for c in chunks)
