"""Cache keys carry the tenant.

Row-level security does not reach into redis. A key that omits the tenant hands
one customer's dashboard to another and nothing downstream will catch it.
"""

from uuid import uuid4

from app.core.cache import SCHEMA_VERSION, cache_key, tag_key

TENANT_A = uuid4()
TENANT_B = uuid4()


def test_key_starts_with_the_tenant() -> None:
    key = cache_key(TENANT_A, "analytics:summary")

    assert key.startswith(f"t:{TENANT_A}:")
    assert SCHEMA_VERSION in key


def test_same_prefix_and_params_differ_by_tenant() -> None:
    params = {"range": "90d"}

    assert cache_key(TENANT_A, "analytics:summary", params) != cache_key(
        TENANT_B, "analytics:summary", params
    )


def test_same_tenant_and_params_are_stable() -> None:
    first = cache_key(TENANT_A, "analytics:summary", {"b": 2, "a": 1})
    second = cache_key(TENANT_A, "analytics:summary", {"a": 1, "b": 2})

    assert first == second, "key must not depend on dict ordering"


def test_different_params_produce_different_keys() -> None:
    assert cache_key(TENANT_A, "shipments", {"status": "delayed"}) != cache_key(
        TENANT_A, "shipments", {"status": "delivered"}
    )


def test_params_are_hashed_rather_than_inlined() -> None:
    key = cache_key(TENANT_A, "shipments", {"search": "user@example.com"})

    assert "user@example.com" not in key


def test_tag_keys_are_tenant_scoped() -> None:
    assert tag_key(TENANT_A, "analytics") != tag_key(TENANT_B, "analytics")
    assert tag_key(TENANT_A, "analytics").startswith(f"t:{TENANT_A}:")
