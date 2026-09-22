"""Manifest headers, which no two systems spell the same way."""

from datetime import date
from decimal import Decimal

from ai.ingestion.mapping import (
    map_headers,
    normalise_header,
    parse_country,
    parse_date,
    parse_decimal,
    parse_int,
    parse_mode,
)


def test_headers_normalise_to_a_common_shape() -> None:
    assert normalise_header("  Ref No ") == "ref_no"
    assert normalise_header("Invoice Value (USD)") == "invoice_value_usd"


def test_real_world_headers_map_to_fields() -> None:
    headers = ["Ref No", "Vendor", "POL", "POD", "Mode", "Cartons", "Invoice Value", "ETA"]

    mapping, unmapped = map_headers(headers)

    assert mapping["Ref No"] == "reference"
    assert mapping["Vendor"] == "supplier_name"
    assert mapping["POL"] == "origin_country"
    assert mapping["POD"] == "dest_country"
    assert mapping["Cartons"] == "qty"
    assert mapping["Invoice Value"] == "value_usd"
    assert unmapped == []


def test_unknown_headers_are_reported_rather_than_dropped_silently() -> None:
    _, unmapped = map_headers(["Ref No", "Container Seal", "Broker Notes"])

    assert unmapped == ["Container Seal", "Broker Notes"]


def test_a_field_is_not_claimed_twice() -> None:
    mapping, _ = map_headers(["Ref", "Reference"])

    assert list(mapping.values()).count("reference") == 1


def test_dates_are_read_in_several_formats() -> None:
    for text in ("2026-03-14", "14/03/2026", "14-Mar-2026", "14.03.2026"):
        assert parse_date(text) == date(2026, 3, 14), text


def test_american_ordering_is_read_as_written() -> None:
    assert parse_date("03/14/2026") == date(2026, 3, 14)


def test_nullish_values_become_none_rather_than_errors() -> None:
    for text in ("", "N/A", "n/a", "-", "TBD", "unknown"):
        assert parse_date(text) is None, text
        assert parse_decimal(text) is None, text


def test_money_survives_thousand_separators_and_symbols() -> None:
    assert parse_decimal("$1,234.50") == Decimal("1234.50")
    assert parse_int("2,000") == 2000


def test_unreadable_money_is_none_not_an_exception() -> None:
    assert parse_decimal("about twelve dollars") is None


def test_country_codes_are_taken_from_messy_input() -> None:
    assert parse_country("cn") == "CN"
    assert parse_country("DE - Hamburg") == "DE"
    assert parse_country("") is None


def test_transport_modes_map_from_trade_shorthand() -> None:
    assert parse_mode("FCL") == "ocean"
    assert parse_mode("LCL") == "ocean"
    assert parse_mode("Airfreight") == "air"
    assert parse_mode("Truck") == "road"
    assert parse_mode("train") == "rail"


def test_an_unknown_mode_falls_back_rather_than_failing_the_row() -> None:
    assert parse_mode("barge") == "ocean"
