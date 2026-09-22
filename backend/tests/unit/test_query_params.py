"""Query models have to be flattened into real parameters.

FastAPI flattens one pydantic query model per endpoint. A second one is not an
error: both quietly become query parameters named after the argument, so every
request to that endpoint fails validation. Nothing in the type system says so.
"""

from app.main import create_app

MODEL_ARGUMENT_NAMES = {"filters", "pagination", "params", "query"}


def _query_params(spec: dict, path: str, method: str) -> list[str]:
    op = spec["paths"][path][method]
    return [p["name"] for p in op.get("parameters", []) if p["in"] == "query"]


def test_no_endpoint_exposes_a_model_as_a_single_query_parameter() -> None:
    spec = create_app().openapi()

    offenders = [
        (path, method, name)
        for path, ops in spec["paths"].items()
        for method in ops
        for name in _query_params(spec, path, method)
        if name in MODEL_ARGUMENT_NAMES
    ]

    assert offenders == [], f"query models were not flattened: {offenders}"


def test_list_endpoints_accept_paging() -> None:
    spec = create_app().openapi()

    for path in ("/api/v1/shipments", "/api/v1/suppliers", "/api/v1/alerts", "/api/v1/users"):
        names = _query_params(spec, path, "get")

        assert "page" in names, path
        assert "size" in names, path


def test_shipment_filters_reach_the_api() -> None:
    names = _query_params(create_app().openapi(), "/api/v1/shipments", "get")

    for expected in ("status", "mode", "supplier_id", "eta_from", "eta_to", "sort", "order"):
        assert expected in names, expected
