import re
from dataclasses import dataclass
from typing import Any

# Roughly a paragraph. Small enough that an embedding stays specific, large
# enough that a clause keeps its context.
TARGET_CHARS = 800
OVERLAP_CHARS = 120
MAX_CHARS = 1500
SEPARATORS = ("\n\n", "\n", ". ", " ")

# The uppercase letter matters. Without it a wrapped body line such as
# "2 percent of the shipment value ..." reads as clause 2 and the real clause
# gets cut in half, which is exactly the half a question needs.
SECTION_RE = re.compile(
    r"^[ \t]*(?:ARTICLE\s+[IVXLC\d]+|Section\s+\d+|\d+(?:\.\d+)*)[.)]?[ \t]+[A-Z]",
    re.MULTILINE,
)
# Headings are short. A long line that happens to start with a number is prose.
MAX_HEADING_CHARS = 80


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    meta: dict[str, Any]


class RecursiveChunker:
    def __init__(
        self,
        target: int = TARGET_CHARS,
        overlap: int = OVERLAP_CHARS,
        max_size: int = MAX_CHARS,
    ) -> None:
        if overlap >= target:
            raise ValueError("overlap must be smaller than target")
        self.target = target
        self.overlap = overlap
        self.max_size = max_size

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.max_size:
            return [text]

        pieces = self._split_on_separator(text)
        return self._merge(pieces)

    def _split_on_separator(self, text: str) -> list[str]:
        for separator in SEPARATORS:
            parts = [p for p in text.split(separator) if p.strip()]
            if len(parts) > 1:
                return [p + separator if separator.strip() else p for p in parts]
        # No separator left: cut on length rather than return something oversized.
        return [text[i : i + self.target] for i in range(0, len(text), self.target)]

    def _merge(self, pieces: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""

        for piece in pieces:
            if len(piece) > self.max_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self.split(piece))
                continue

            if len(current) + len(piece) <= self.target:
                current += piece
                continue

            if current:
                chunks.append(current.strip())
                # Carry the tail forward so a sentence cut in half survives whole
                # in one of the two chunks.
                current = current[-self.overlap :] + piece
            else:
                current = piece

        if current.strip():
            chunks.append(current.strip())
        return [c for c in chunks if c]


class SectionAwareChunker(RecursiveChunker):
    """Keeps a numbered clause together when it fits.

    "What is the penalty for late delivery" wants the whole of 4.2, not the
    first two thirds of it.
    """

    def split_sections(self, text: str) -> list[tuple[str | None, str]]:
        matches = [m for m in SECTION_RE.finditer(text) if _is_heading_line(text, m.start())]
        if not matches:
            return [(None, text)]

        sections: list[tuple[str | None, str]] = []
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append((None, preamble))

        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[match.start() : end].strip()
            if body:
                sections.append((_section_label(body), body))
        return sections

    def split(self, text: str) -> list[str]:
        out: list[str] = []
        for _, body in self.split_sections(text):
            if len(body) <= self.max_size:
                out.append(body)
            else:
                out.extend(super().split(body))
        return out


def _is_heading_line(text: str, start: int) -> bool:
    end = text.find("\n", start)
    line = text[start : end if end != -1 else len(text)]
    return len(line.strip()) <= MAX_HEADING_CHARS


def _section_label(body: str) -> str | None:
    first = body.splitlines()[0].strip()
    return first[:120] if first else None
