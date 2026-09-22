import csv
import io
from pathlib import Path
from typing import Any

from charset_normalizer import from_path

from ai.ingestion.base import ParsedDoc, ParsedRow, Parser, PermanentError
from ai.ingestion.mapping import (
    REQUIRED,
    map_headers,
    parse_country,
    parse_date,
    parse_decimal,
    parse_int,
    parse_mode,
)

MAX_ROWS = 20_000
SNIFF_BYTES = 8192


class CsvParser(Parser):
    """Rows the file got wrong are counted and reported, not fatal.

    Real manifests always have a few bad rows. Rejecting the whole upload over
    three of them helps nobody.
    """

    def parse(self, path: Path) -> ParsedDoc:
        text = _decode(path)
        dialect = _sniff(text)

        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames:
            raise PermanentError("csv has no header row")

        mapping, unmapped = map_headers(list(reader.fieldnames))
        missing = [f for f in REQUIRED if f not in mapping.values()]
        if missing:
            raise PermanentError(
                "could not find columns for "
                + ", ".join(missing)
                + f". Headers seen: {', '.join(reader.fieldnames)}"
            )

        rows: list[ParsedRow] = []
        skipped: list[dict[str, Any]] = []

        for line_no, raw in enumerate(reader, start=2):
            if len(rows) >= MAX_ROWS:
                skipped.append({"line": line_no, "reason": f"row limit {MAX_ROWS} reached"})
                break

            record = {field: raw.get(column) for column, field in mapping.items()}
            parsed, problem = _coerce(record)
            if problem:
                skipped.append({"line": line_no, "reason": problem})
                continue
            rows.append(ParsedRow(data=parsed, line_no=line_no))

        return ParsedDoc(
            rows=rows,
            skipped=skipped,
            meta={
                "mapped_columns": mapping,
                "unmapped_columns": unmapped,
                "row_count": len(rows),
                "skipped_count": len(skipped),
            },
        )


def _decode(path: Path) -> str:
    # Manifests exported from excel are rarely utf-8.
    match = from_path(path).best()
    if match is None:
        return path.read_text(encoding="latin-1", errors="replace")
    return str(match)


def _sniff(text: str) -> type[csv.Dialect] | csv.Dialect:
    try:
        return csv.Sniffer().sniff(text[:SNIFF_BYTES], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _coerce(record: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    reference = str(record.get("reference") or "").strip()
    if not reference:
        return {}, "missing reference"

    origin = parse_country(record.get("origin_country"))
    dest = parse_country(record.get("dest_country"))
    if not origin or not dest:
        return {}, "missing or unreadable country code"

    eta = parse_date(record.get("eta"))
    if eta is None:
        return {}, f"unreadable eta {record.get('eta')!r}"

    return {
        "reference": reference[:64],
        "supplier_name": (str(record.get("supplier_name") or "").strip() or None),
        "origin_country": origin,
        "dest_country": dest,
        "mode": parse_mode(record.get("mode")),
        "incoterm": (str(record.get("incoterm") or "").strip()[:8] or None),
        "qty": parse_int(record.get("qty")) or 0,
        "value_usd": parse_decimal(record.get("value_usd")) or 0,
        "weight_kg": parse_decimal(record.get("weight_kg")),
        "eta": eta,
        "ata": parse_date(record.get("ata")),
    }, None
