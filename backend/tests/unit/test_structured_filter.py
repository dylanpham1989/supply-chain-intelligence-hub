"""The model proposes a filter, never sql.

A filter is validated against a schema that forbids unknown keys, so the worst a
bad generation achieves is a validation failure.
"""

from datetime import date

from ai.rag.structured import (
    EU_COUNTRIES,
    ShipmentQueryFilter,
    expand_regions,
    parse_filter,
)


def test_a_plain_json_object_parses() -> None:
    parsed = parse_filter('{"status": "delayed", "limit": 10}')

    assert parsed is not None
    assert parsed.status is not None and parsed.status.value == "delayed"
    assert parsed.limit == 10


def test_json_wrapped_in_prose_is_still_found() -> None:
    parsed = parse_filter('Sure, here you go:\n{"late_only": true}\nHope that helps.')

    assert parsed is not None
    assert parsed.late_only is True


def test_an_invented_key_is_refused() -> None:
    """extra=forbid, so a hallucinated field fails rather than being ignored."""
    assert parse_filter('{"drop_table": "shipments", "status": "delayed"}') is None


def test_an_invalid_enum_value_is_refused() -> None:
    assert parse_filter('{"status": "on_fire"}') is None


def test_an_out_of_range_limit_is_refused() -> None:
    assert parse_filter('{"limit": 100000}') is None


def test_text_with_no_json_returns_nothing() -> None:
    assert parse_filter("I am not able to help with that request.") is None


def test_broken_json_returns_nothing() -> None:
    assert parse_filter('{"status": "delayed"') is None


def test_dates_are_parsed() -> None:
    parsed = parse_filter('{"eta_from": "2026-01-01", "eta_to": "2026-03-31"}')

    assert parsed is not None
    assert parsed.eta_from == date(2026, 1, 1)
    assert parsed.eta_to == date(2026, 3, 31)


def test_a_region_is_expanded_from_the_question() -> None:
    """Asked to list the EU a model produces a plausible subset and misses a few."""
    expanded = expand_regions("late deliveries to the EU in Q1", ShipmentQueryFilter())

    assert expanded.dest_countries is not None
    assert set(expanded.dest_countries) == EU_COUNTRIES
    assert len(expanded.dest_countries) == 27


def test_an_explicit_country_list_is_left_alone() -> None:
    given = ShipmentQueryFilter(dest_countries=["DE"])

    assert expand_regions("shipments to the EU", given).dest_countries == ["DE"]


def test_a_question_with_no_region_is_unchanged() -> None:
    assert expand_regions("late shipments", ShipmentQueryFilter()).dest_countries is None


def test_the_default_limit_is_bounded() -> None:
    assert ShipmentQueryFilter().limit == 50
