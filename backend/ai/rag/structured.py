"""Aggregate questions answered from the table.

The model proposes a filter as json and never sql. A filter is validated against
a schema that forbids unknown fields, so the worst a bad generation can do is
fail validation. Generated sql would have to be trusted or parsed, and neither
is a position worth being in.
"""

import json
import re
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.enums import ShipmentStatus, TransportMode

EU_COUNTRIES = frozenset(
    [
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
    ]
)
REGIONS: dict[str, frozenset[str]] = {
    "eu": EU_COUNTRIES,
    "europe": EU_COUNTRIES,
    "asia": frozenset(["CN", "VN", "JP", "KR", "TW", "TH", "IN", "ID", "MY", "SG", "PH"]),
    "north america": frozenset(["US", "CA", "MX"]),
    "us": frozenset({"US"}),
}

FILTER_SCHEMA_HINT = """Return only a json object with these optional keys:
status: one of planned, in_transit, delivered, delayed, cancelled
mode: one of air, ocean, road, rail
dest_countries: list of ISO-3166 alpha-2 codes
origin_countries: list of ISO-3166 alpha-2 codes
supplier_name: string
eta_from: YYYY-MM-DD
eta_to: YYYY-MM-DD
late_only: boolean
limit: integer between 1 and 200
Use no other keys. Return {} if the question names no filter."""

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class ShipmentQueryFilter(BaseModel):
    # An invented key is a validation error rather than something ignored in
    # silence, which is the difference between a wrong answer and a caught one.
    model_config = ConfigDict(extra="forbid")

    status: ShipmentStatus | None = None
    mode: TransportMode | None = None
    dest_countries: list[str] | None = Field(None, max_length=40)
    origin_countries: list[str] | None = Field(None, max_length=40)
    supplier_name: str | None = Field(None, max_length=120)
    eta_from: date | None = None
    eta_to: date | None = None
    late_only: bool = False
    limit: int = Field(50, ge=1, le=200)


def parse_filter(raw: str) -> ShipmentQueryFilter | None:
    match = JSON_RE.search(raw)
    if not match:
        return None
    try:
        return ShipmentQueryFilter.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValidationError):
        return None


def expand_regions(question: str, filters: ShipmentQueryFilter) -> ShipmentQueryFilter:
    """Regions are resolved here, not by the model.

    Asked to list the EU, a model will produce a plausible subset and leave a
    few members out, and nothing downstream would notice.
    """
    if filters.dest_countries:
        return filters
    lowered = question.lower()
    for name, countries in REGIONS.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return filters.model_copy(update={"dest_countries": sorted(countries)})
    return filters


def describe(filters: ShipmentQueryFilter) -> dict[str, Any]:
    return filters.model_dump(exclude_none=True, exclude_defaults=True)


STATUS_WORDS = {
    "delayed": "delayed",
    "late": "delayed",
    "delivered": "delivered",
    "arrived": "delivered",
    "in transit": "in_transit",
    "planned": "planned",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}
MODE_WORDS = {"air": "air", "ocean": "ocean", "sea": "ocean", "road": "road", "rail": "rail"}
QUARTERS = {
    "q1": (1, 3),
    "q2": (4, 6),
    "q3": (7, 9),
    "q4": (10, 12),
}
YEAR_RE = re.compile(r"\b(20\d{2})\b")


def extract_filter(question: str) -> ShipmentQueryFilter:
    """Read a filter straight out of the question.

    Used when the model does not return usable json, which the offline mock
    never does. Without it a structured question falls back to an empty filter
    and answers "50 shipments match" to "how many were delayed", which is worse
    than an error because it looks like an answer.
    """
    lowered = question.lower()
    values: dict[str, Any] = {}

    for word, status in STATUS_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            values["status"] = status
            break

    for word, mode in MODE_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            values["mode"] = mode
            break

    if re.search(r"\blate\b|\bbehind schedule\b|\boverdue\b", lowered):
        values["late_only"] = True
        # "late deliveries" is about arrival, not about the status column.
        values.pop("status", None)

    year = YEAR_RE.search(lowered)
    for name, (first, last) in QUARTERS.items():
        if re.search(rf"\b{name}\b", lowered):
            y = int(year.group(1)) if year else date.today().year
            values["eta_from"] = date(y, first, 1)
            values["eta_to"] = date(y + ((last == 12 and 0) or 0), last, 28 if last == 2 else 30)
            break

    if match := re.search(r"\btop (\d+)\b", lowered):
        values["limit"] = min(200, max(1, int(match.group(1))))

    return ShipmentQueryFilter.model_validate(values)
