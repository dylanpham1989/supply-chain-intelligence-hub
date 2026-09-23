import re
import time

from ai.llm.base import LLMResponse

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "for",
        "on",
        "at",
        "by",
        "with",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "why",
        "when",
        "where",
        "does",
        "do",
        "did",
        "shall",
        "will",
        "would",
        "could",
        "should",
        "can",
        "may",
        "this",
        "that",
        "these",
        "those",
        "from",
        "under",
        "over",
        "about",
        "into",
        "than",
        "then",
        "there",
        "their",
        "our",
        "your",
        "it",
        "its",
        "as",
        "if",
        "not",
        "no",
        "all",
        "any",
    ]
)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
CITATION_RE = re.compile(r"\[(\d+)\]")
MAX_SENTENCES = 3
NOT_FOUND = "I could not find this in the indexed documents."


class MockProvider:
    """Answers by extraction, with no network call.

    This is what lets CI and a fresh clone exercise the whole pipeline without an
    api key, and it separates two failures that otherwise look identical: bad
    retrieval and a bad generation. If the mock cannot answer from the context,
    the context was wrong.
    """

    model = "mock-extractive"

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.1
    ) -> LLMResponse:
        started = time.perf_counter()
        context, question = _split(user)
        sentences = _sentences_with_sources(context)

        if not sentences:
            return self._respond(NOT_FOUND, started, user)

        wanted = _tokens(question)
        scored = [(source, sentence, _overlap(sentence, wanted)) for source, sentence in sentences]
        scored.sort(key=lambda row: row[2], reverse=True)
        best = [row for row in scored if row[2] > 0][:MAX_SENTENCES]

        if not best:
            return self._respond(NOT_FOUND, started, user)

        lines = [f"{sentence.strip()} [{source}]" for source, sentence, _ in best]
        return self._respond(" ".join(lines), started, user)

    def _respond(self, text: str, started: float, prompt: str) -> LLMResponse:
        return LLMResponse(
            text=text,
            model=self.model,
            token_in=len(prompt) // 4,
            token_out=len(text) // 4,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


def _split(user: str) -> tuple[str, str]:
    marker = "Question:"
    if marker in user:
        context, _, question = user.rpartition(marker)
        return context, question
    return user, user


def _sentences_with_sources(context: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    current: int | None = None
    for line in context.splitlines():
        match = CITATION_RE.match(line.strip())
        if match:
            current = int(match.group(1))
            line = line[match.end() :]
        if current is None:
            continue
        for sentence in SENTENCE_RE.split(line):
            if len(sentence.strip()) > 20:
                out.append((current, sentence.strip()))
    return out


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9.]+", text.lower()) if w not in STOPWORDS}


def _overlap(sentence: str, wanted: set[str]) -> float:
    words = _tokens(sentence)
    if not wanted or not words:
        return 0.0
    return len(words & wanted) / len(wanted)
