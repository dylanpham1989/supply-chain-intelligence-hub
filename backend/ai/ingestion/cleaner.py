import re
from collections import Counter

from ai.ingestion.base import ParsedPage

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "­": ""}
WHITESPACE = re.compile(r"[ \t]{2,}")
BLANK_LINES = re.compile(r"\n{3,}")
MIN_PAGE_CHARS = 20
# A line on more than this share of pages is furniture, not content.
REPEAT_THRESHOLD = 0.6


def clean_pages(pages: list[ParsedPage]) -> list[ParsedPage]:
    if not pages:
        return []

    furniture = _repeated_lines(pages)
    cleaned: list[ParsedPage] = []

    for page in pages:
        lines = [ln for ln in page.text.splitlines() if ln.strip() not in furniture]
        text = _normalise("\n".join(lines))
        if len(text.strip()) < MIN_PAGE_CHARS and not page.tables:
            continue
        cleaned.append(ParsedPage(page_no=page.page_no, text=text, tables=page.tables))

    return cleaned


def _repeated_lines(pages: list[ParsedPage]) -> set[str]:
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        for line in {ln.strip() for ln in page.text.splitlines() if ln.strip()}:
            counts[line] += 1
    cutoff = len(pages) * REPEAT_THRESHOLD
    return {line for line, n in counts.items() if n >= cutoff and len(line) < 120}


def _normalise(text: str) -> str:
    for bad, good in LIGATURES.items():
        text = text.replace(bad, good)
    text = WHITESPACE.sub(" ", text)
    text = BLANK_LINES.sub("\n\n", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()
