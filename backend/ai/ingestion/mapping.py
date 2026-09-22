"""Header aliases for manifest csv files.

Real manifests come from a dozen different systems and none of them agree on
column names, so a fixed schema would reject most of them.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

FIELD_ALIASES: dict[str, set[str]] = {
    "reference": {"ref", "reference", "ref_no", "shipment_ref", "awb", "bl_no", "booking"},
    "supplier_name": {"supplier", "vendor", "shipper", "supplier_name", "seller"},
    "origin_country": {"origin", "from", "origin_country", "pol", "port_of_loading"},
    "dest_country": {"destination", "to", "dest_country", "pod", "port_of_discharge"},
    "mode": {"mode", "transport_mode", "shipment_mode"},
    "incoterm": {"incoterm", "incoterms", "terms"},
    "qty": {"qty", "quantity", "units", "pieces", "cartons"},
    "value_usd": {"value", "value_usd", "amount", "invoice_value", "total_value"},
    "weight_kg": {"weight", "weight_kg", "gross_weight"},
    "eta": {"eta", "expected_arrival", "est_arrival", "estimated_arrival"},
    "ata": {"ata", "actual_arrival", "delivered_on", "arrival_date"},
}

REQUIRED = ("reference", "origin_country", "dest_country", "eta")

MODE_ALIASES = {
    "air": "air",
    "airfreight": "air",
    "avia": "air",
    "sea": "ocean",
    "ocean": "ocean",
    "vessel": "ocean",
    "fcl": "ocean",
    "lcl": "ocean",
    "road": "road",
    "truck": "road",
    "ltl": "road",
    "ftl": "road",
    "rail": "rail",
    "train": "rail",
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d", "%d.%m.%Y")
NULLISH = {"", "n/a", "na", "null", "none", "-", "tbd", "unknown"}


def normalise_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def map_headers(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """Returns the column to field mapping and the headers nothing matched."""
    mapping: dict[str, str] = {}
    unmapped: list[str] = []

    for header in headers:
        key = normalise_header(header)
        for field, aliases in FIELD_ALIASES.items():
            if key in aliases and field not in mapping.values():
                mapping[header] = field
                break
        else:
            unmapped.append(header)

    return mapping, unmapped


def parse_decimal(value: Any) -> Decimal | None:
    text = str(value).strip().replace(",", "").replace("$", "")
    if text.lower() in NULLISH:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    parsed = parse_decimal(value)
    return int(parsed) if parsed is not None else None


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if text.lower() in NULLISH:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_country(value: Any) -> str | None:
    text = re.sub(r"[^A-Za-z]", "", str(value)).upper()
    return text[:2] if len(text) >= 2 else None


def parse_mode(value: Any) -> str:
    key = re.sub(r"[^a-z]", "", str(value).lower())
    return MODE_ALIASES.get(key, "ocean")
