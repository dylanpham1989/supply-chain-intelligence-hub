"""Which questions go to sql instead of retrieval.

Retrieval returns the top k. "How many shipments were late" answered from an
index is a guess with a number on it.
"""

import pytest

from ai.rag.router import Route, route

STRUCTURED = [
    "How many shipments were delayed last quarter?",
    "Show all late deliveries to the EU in Q1",
    "List all shipments from Shenzhen Precision Parts",
    "What is the total value of delayed shipments?",
    "Which suppliers have the worst on-time rate?",
    "Give me the top 5 suppliers by volume",
    "What is the average delay in days?",
    "Count the shipments arriving next month",
]

SEMANTIC = [
    "What is the penalty for late delivery?",
    "Who is the notified party on the Globex contract?",
    "What does clause 4.2 say?",
    "Under what circumstances can the buyer reject goods?",
    "What are the payment terms?",
    "Explain the force majeure provision",
]


@pytest.mark.parametrize("question", STRUCTURED)
def test_aggregate_questions_go_to_sql(question: str) -> None:
    assert route(question) is Route.STRUCTURED, question


@pytest.mark.parametrize("question", SEMANTIC)
def test_questions_about_wording_go_to_retrieval(question: str) -> None:
    assert route(question) is Route.SEMANTIC, question


def test_routing_ignores_case() -> None:
    assert route("HOW MANY SHIPMENTS ARE LATE") is Route.STRUCTURED


def test_an_empty_question_falls_back_to_retrieval() -> None:
    assert route("") is Route.SEMANTIC
