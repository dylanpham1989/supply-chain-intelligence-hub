"""Provider selection.

The hosted providers are an optional dependency group. Asking for one that is
not installed has to say so, rather than failing later inside a request.
"""

import sys

import pytest

from ai.llm.base import LLMUnavailableError
from ai.llm.factory import get_llm
from ai.llm.mock import MockProvider


def test_the_default_is_the_mock() -> None:
    assert isinstance(get_llm(), MockProvider)
    assert get_llm().model == "mock-extractive"


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown llm provider"):
        get_llm("gpt5000")


@pytest.mark.parametrize("name", ["anthropic", "openai", "hf"])
def test_every_named_provider_can_be_constructed(name: str) -> None:
    provider = get_llm(name)

    assert provider.model


async def test_a_missing_package_raises_unavailable_not_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller turns this into a 503; an ImportError would be a 500."""
    monkeypatch.setitem(sys.modules, "anthropic", None)
    provider = get_llm("anthropic")

    with pytest.raises(LLMUnavailableError, match="not installed"):
        await provider.complete(system="s", user="u")


async def test_the_mock_answers_from_the_numbered_context() -> None:
    provider = MockProvider()

    response = await provider.complete(
        system="ignored",
        user=(
            "Context:\n"
            "[1] (contract.pdf)\n"
            "The Supplier shall pay a penalty of 2 percent of the shipment value.\n\n"
            "[2] (contract.pdf)\n"
            "Payment terms are 60 days from the date of a valid invoice.\n\n"
            "Question: What is the penalty for late delivery?"
        ),
    )

    assert "2 percent" in response.text
    assert "[1]" in response.text
    assert response.token_in > 0


async def test_the_mock_declines_when_the_context_has_nothing() -> None:
    provider = MockProvider()

    response = await provider.complete(
        system="ignored",
        user="Context:\n[1] (a.pdf)\nUnrelated text about nothing.\n\nQuestion: zzzz qqqq",
    )

    assert response.text == "I could not find this in the indexed documents."


async def test_the_mock_does_not_repeat_the_same_sentence() -> None:
    """The same clause turns up in several chunks; saying it three times reads badly."""
    provider = MockProvider()
    clause = "The Supplier shall pay a penalty of 2 percent of the shipment value."

    response = await provider.complete(
        system="ignored",
        user=(
            f"Context:\n[1] (a.pdf)\n{clause}\n\n"
            f"[2] (a.pdf)\n{clause}\n\n"
            f"[3] (a.pdf)\n{clause}\n\n"
            "Question: What is the penalty for late delivery?"
        ),
    )

    assert response.text.count("2 percent") == 1


async def test_the_mock_does_not_quote_the_source_header_back() -> None:
    """ "[1] (contract.pdf, page 4, 4.2 Late Delivery)" is provenance, not an answer."""
    provider = MockProvider()

    response = await provider.complete(
        system="ignored",
        user=(
            "Context:\n"
            "[1] (contract.pdf, page 4, 4.2 Late Delivery)\n"
            "The Supplier shall pay a penalty of 2 percent of the shipment value.\n\n"
            "Question: What is the penalty for late delivery?"
        ),
    )

    assert "contract.pdf" not in response.text
    assert "page 4" not in response.text
    assert "2 percent" in response.text
