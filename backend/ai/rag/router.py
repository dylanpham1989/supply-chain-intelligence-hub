import re
from enum import StrEnum


class Route(StrEnum):
    SEMANTIC = "semantic"
    STRUCTURED = "structured"


# Questions that want a complete set, a count or an ordering. Retrieval returns
# the top k, so "how many shipments were late" answered from an index is a
# guess dressed up as a number.
AGGREGATE_PATTERNS = (
    r"\bhow many\b",
    r"\bhow much\b",
    r"\bcount\b",
    r"\btotal\b",
    r"\bsum\b",
    r"\baverage\b",
    r"\bavg\b",
    r"\blist all\b",
    r"\bshow all\b",
    r"\ball (?:the )?(?:late|delayed|shipments|deliveries)\b",
    r"\btop \d+\b",
    r"\bwhich suppliers?\b",
    r"\bon[- ]time rate\b",
)
AGGREGATE_RE = re.compile("|".join(AGGREGATE_PATTERNS), re.IGNORECASE)


def route(question: str) -> Route:
    """Rule based on purpose.

    An llm classifier would be more accurate and would add a model call to every
    question before any work starts. The rules cover the shapes that matter, and
    a wrong guess degrades to retrieval rather than failing.
    """
    return Route.STRUCTURED if AGGREGATE_RE.search(question) else Route.SEMANTIC
