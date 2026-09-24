"""The model proposes a filter, never sql.

A filter is validated against a schema that forbids unknown keys, so the worst a
bad generation achieves is a validation failure.
"""

from datetime import date

import pytest

from ai.rag.structured import (
    EU_COUNTRIES,
    ShipmentQueryFilter,
    expand_regions,
    extract_filter,
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


# The extractor is the fallback that runs whenever the model does not return
# usable json, which for the offline default is always.
EXTRACTION_CASES = [
    ("How many shipments were delayed?", {"status": "delayed"}),
    ("Show all late deliveries", {"late_only": True}),
    ("list all cancelled shipments", {"status": "cancelled"}),
    ("how many air shipments are there", {"mode": "air"}),
    ("total value of ocean freight", {"mode": "ocean"}),
    ("top 5 suppliers", {"limit": 5}),
]


@pytest.mark.parametrize(("question", "expected"), EXTRACTION_CASES)
def test_a_filter_is_read_out_of_the_question(question: str, expected: dict[str, object]) -> None:
    extracted = extract_filter(question).model_dump(exclude_defaults=True)

    for key, value in expected.items():
        assert extracted.get(key) == value, (question, key, extracted)


def test_late_is_about_arrival_not_the_status_column() -> None:
    """A shipment can be marked delivered and still have arrived late."""
    extracted = extract_filter("show all late deliveries to the EU")

    assert extracted.late_only is True
    assert extracted.status is None


def test_a_quarter_becomes_a_date_range() -> None:
    extracted = extract_filter("late deliveries in Q1 2026")

    assert extracted.eta_from == date(2026, 1, 1)
    assert extracted.eta_to is not None
    assert extracted.eta_to.month == 3


def test_a_question_with_no_filter_words_extracts_nothing() -> None:
    extracted = extract_filter("how many shipments are there")

    assert extracted.model_dump(exclude_defaults=True) == {}


def test_an_extracted_limit_is_bounded() -> None:
    assert extract_filter("top 99999 suppliers").limit == 200
