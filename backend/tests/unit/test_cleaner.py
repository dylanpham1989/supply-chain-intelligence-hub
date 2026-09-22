"""Page furniture removal.

A header repeated on every page ends up in every chunk, which makes them all
look faintly alike to an embedding and wastes context on nothing.
"""

from ai.ingestion.base import ParsedPage
from ai.ingestion.cleaner import clean_pages


def _pages(*texts: str) -> list[ParsedPage]:
    return [ParsedPage(page_no=i, text=t) for i, t in enumerate(texts, start=1)]


HEADER = "ACME LOGISTICS CONFIDENTIAL"
FOOTER = "Page footer, commercial in confidence"


def test_no_pages_is_not_an_error() -> None:
    assert clean_pages([]) == []


def test_a_line_on_every_page_is_removed() -> None:
    pages = _pages(
        f"{HEADER}\nClause one says something about delivery terms.\n{FOOTER}",
        f"{HEADER}\nClause two says something about payment terms.\n{FOOTER}",
        f"{HEADER}\nClause three says something about termination.\n{FOOTER}",
        f"{HEADER}\nClause four says something about governing law.\n{FOOTER}",
    )

    cleaned = clean_pages(pages)

    assert len(cleaned) == 4
    for page in cleaned:
        assert HEADER not in page.text
        assert FOOTER not in page.text
        assert "Clause" in page.text


def test_a_line_on_one_page_is_kept() -> None:
    pages = _pages(
        "Only here once, a clause about indemnity and liability limits.",
        "Clause two says something about payment terms and invoicing.",
        "Clause three says something about termination and notice periods.",
    )

    cleaned = clean_pages(pages)

    assert "indemnity" in cleaned[0].text


def test_two_pages_are_left_alone() -> None:
    """With so few pages, a repeat is as likely to be content as furniture."""
    pages = _pages(f"{HEADER}\nClause one about delivery.", f"{HEADER}\nClause two about payment.")

    cleaned = clean_pages(pages)

    assert all(HEADER in page.text for page in cleaned)


def test_an_empty_page_is_dropped() -> None:
    pages = _pages(
        "A real clause with enough words in it to count as content here.",
        "   \n\n  ",
        "Another real clause with enough words in it to count as content.",
    )

    cleaned = clean_pages(pages)

    assert len(cleaned) == 2


def test_ligatures_and_runs_of_space_are_normalised() -> None:
    pages = _pages("The ﬁnal    clause    confirms    the    speciﬁcation applies here.")

    text = clean_pages(pages)[0].text

    assert "final clause confirms the specification" in text
    assert "  " not in text


def test_page_numbers_survive_cleaning() -> None:
    pages = _pages(
        "Clause one about delivery terms and the agreed schedule of work.",
        "Clause two about payment terms and the invoicing arrangements.",
    )

    assert [p.page_no for p in clean_pages(pages)] == [1, 2]
