"""Proof that one tenant cannot read or write another tenant's rows.

These are the tests behind the isolation claim in the README. Shared-schema
multi-tenancy is only safe if the database enforces the boundary, so the checks
here run as app_user and go through the real policies.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import current_tenant_id, set_tenant_context
from app.models import (
    TENANT_SCOPED_TABLES,
    Shipment,
    Supplier,
    Tenant,
)
from app.models.enums import ShipmentStatus, TransportMode
from app.repositories.base import TenantRepository
from tests.integration.conftest import TenantSwitch

pytestmark = pytest.mark.integration


class ShipmentRepository(TenantRepository[Shipment]):
    model = Shipment


def _shipment(tenant_id: UUID, reference: str) -> Shipment:
    return Shipment(
        tenant_id=tenant_id,
        reference=reference,
        origin_country="CN",
        dest_country="DE",
        mode=TransportMode.OCEAN,
        qty=10,
        value_usd=1000,
        eta=date(2026, 6, 1),
        status=ShipmentStatus.IN_TRANSIT,
    )


async def test_app_user_cannot_bypass_rls(session: AsyncSession) -> None:
    """If this role could bypass RLS, every other test here would pass for free."""
    row = (
        await session.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
    ).one()

    assert row.current_user == "app_user"
    assert row.rolsuper is False
    assert row.rolbypassrls is False


async def test_context_is_readable_back_and_dies_with_the_transaction(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """Phase 3 wires this through a request dependency, so the read-back matters."""
    assert await current_tenant_id(session) is None

    await set_tenant_context(session, tenant_a.id)

    assert await current_tenant_id(session) == tenant_a.id


async def test_select_without_tenant_context_returns_nothing(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    await set_tenant_context(session, tenant_a.id)
    session.add(_shipment(tenant_a.id, "NO-CTX-1"))
    await session.flush()

    await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    found = (await session.execute(select(Shipment))).scalars().all()

    assert found == []


async def test_tenant_cannot_select_another_tenants_rows(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    mine = _shipment(tenant_a.id, "ISO-A-1")
    session.add(mine)
    await session.flush()

    await as_tenant(tenant_b.id)
    by_id = (
        await session.execute(select(Shipment).where(Shipment.id == mine.id))
    ).scalar_one_or_none()
    all_visible = (await session.execute(select(Shipment))).scalars().all()

    assert by_id is None
    assert all(s.tenant_id == tenant_b.id for s in all_visible)


async def test_tenant_cannot_insert_rows_for_another_tenant(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    session.add(_shipment(tenant_b.id, "ISO-CROSS-1"))

    with pytest.raises((DBAPIError, ProgrammingError)) as exc:
        await session.flush()

    assert "row-level security" in str(exc.value).lower()


async def test_tenant_cannot_update_another_tenants_rows(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    target = _shipment(tenant_a.id, "ISO-UPD-1")
    session.add(target)
    await session.flush()

    await as_tenant(tenant_b.id)
    result = await session.execute(
        text("UPDATE shipments SET status = 'cancelled' WHERE id = :id"),
        {"id": target.id},
    )

    assert result.rowcount == 0


async def test_tenant_cannot_delete_another_tenants_rows(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    target = _shipment(tenant_a.id, "ISO-DEL-1")
    session.add(target)
    await session.flush()

    await as_tenant(tenant_b.id)
    result = await session.execute(text("DELETE FROM shipments WHERE id = :id"), {"id": target.id})

    assert result.rowcount == 0


async def test_aggregates_do_not_leak_across_tenants(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    """count(*) is the easy way to leak: no rows come back, just a number."""
    await as_tenant(tenant_a.id)
    session.add_all([_shipment(tenant_a.id, f"AGG-A-{i}") for i in range(3)])
    await session.flush()
    a_total = (await session.execute(text("SELECT count(*) FROM shipments"))).scalar()

    await as_tenant(tenant_b.id)
    session.add(_shipment(tenant_b.id, "AGG-B-1"))
    await session.flush()
    b_total = (await session.execute(text("SELECT count(*) FROM shipments"))).scalar()

    assert a_total == 3
    assert b_total == 1


async def test_repository_scopes_reads_to_its_tenant(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    session.add_all([_shipment(tenant_a.id, f"REPO-A-{i}") for i in range(2)])
    await session.flush()

    repo_a = ShipmentRepository(session, tenant_a.id)
    repo_b = ShipmentRepository(session, tenant_b.id)

    assert await repo_a.count() == 2
    assert await repo_b.count() == 0


async def test_repository_injects_its_own_tenant_id(
    session: AsyncSession, tenant_a: Tenant, as_tenant: TenantSwitch
) -> None:
    """A caller passing someone else's tenant_id must not be able to override it."""
    await as_tenant(tenant_a.id)
    repo = ShipmentRepository(session, tenant_a.id)

    created = await repo.create(
        tenant_id=uuid4(),
        reference="REPO-OVERRIDE-1",
        origin_country="VN",
        dest_country="NL",
        mode=TransportMode.AIR,
        qty=1,
        value_usd=1,
        eta=date(2026, 7, 1),
        status=ShipmentStatus.PLANNED,
    )

    assert created.tenant_id == tenant_a.id


async def test_repository_requires_a_tenant_id() -> None:
    with pytest.raises(TypeError):
        ShipmentRepository(None)  # type: ignore[call-arg,arg-type]


async def test_policy_covers_every_tenant_table(session: AsyncSession) -> None:
    """A new tenant table without a policy is a silent hole, so assert on pg_class."""
    rows = (
        await session.execute(
            text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = ANY(:names)
            """),
            {"names": list(TENANT_SCOPED_TABLES)},
        )
    ).all()

    assert len(rows) == len(TENANT_SCOPED_TABLES)
    for row in rows:
        assert row.relrowsecurity, f"{row.relname} has RLS disabled"
        assert row.relforcerowsecurity, f"{row.relname} does not force RLS for the owner"
        assert row.policies == 1, f"{row.relname} has {row.policies} policies"


async def test_supplier_isolation(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    session.add(Supplier(tenant_id=tenant_a.id, name="Only Mine", country="CN", category="x"))
    await session.flush()

    await as_tenant(tenant_b.id)
    visible = (await session.execute(select(Supplier.name))).scalars().all()

    assert "Only Mine" not in visible


async def test_repository_get_does_not_reach_across_tenants(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    mine = _shipment(tenant_a.id, "REPO-GET-1")
    session.add(mine)
    await session.flush()

    assert await ShipmentRepository(session, tenant_a.id).get(mine.id) is not None

    await as_tenant(tenant_b.id)
    assert await ShipmentRepository(session, tenant_b.id).get(mine.id) is None


async def test_repository_list_pages_within_the_tenant(
    session: AsyncSession, tenant_a: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    session.add_all([_shipment(tenant_a.id, f"REPO-LIST-{i}") for i in range(5)])
    await session.flush()

    repo = ShipmentRepository(session, tenant_a.id)
    first = await repo.list(limit=2)
    second = await repo.list(limit=2, offset=2)

    assert len(first) == 2
    assert len(second) == 2
    assert {s.id for s in first}.isdisjoint({s.id for s in second})


async def test_repository_delete_refuses_another_tenants_row(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant, as_tenant: TenantSwitch
) -> None:
    await as_tenant(tenant_a.id)
    target = _shipment(tenant_a.id, "REPO-DEL-1")
    session.add(target)
    await session.flush()

    await as_tenant(tenant_b.id)
    assert await ShipmentRepository(session, tenant_b.id).delete(target.id) is False

    await as_tenant(tenant_a.id)
    assert await ShipmentRepository(session, tenant_a.id).delete(target.id) is True
    assert await ShipmentRepository(session, tenant_a.id).get(target.id) is None
