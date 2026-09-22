from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class IngestionError(Exception):
    """Base for anything that goes wrong reading a document."""


class PermanentError(IngestionError):
    """Retrying will not help. A scanned pdf is still scanned next time."""


class TransientError(IngestionError):
    """Worth retrying: a timeout, a connection reset."""


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    text: str
    tables: list[list[list[str]]] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedRow:
    data: dict[str, Any]
    line_no: int


@dataclass(frozen=True)
class ParsedDoc:
    pages: list[ParsedPage] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)


class Parser(Protocol):
    """Adding a format means adding a parser, not editing the worker."""

    def parse(self, path: Path) -> ParsedDoc: ...
