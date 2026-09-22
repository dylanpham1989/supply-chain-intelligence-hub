"""Two demo tenants with enough history for the dashboard to look real.

Deterministic on purpose: the same seed every time means screenshots, tests and
the demo script all talk about the same numbers.
"""

import asyncio
import random
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.db.rls import set_tenant_context
from app.models import Alert, Contract, Shipment, Supplier, Tenant, User
from app.models.enums import (
    AlertKind,
    AlertSeverity,
    RiskLabel,
    ShipmentStatus,
    TransportMode,
    UserRole,
)

SEED = 42
TODAY = date(2026, 9, 22)

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_PASSWORD = "Demo1234!"  # noqa: S105 - documented demo credential

TENANTS = [
    {
        "slug": "acme-logistics",
        "name": "Acme Logistics",
        "plan": "growth",
        "domain": "acme.test",
        "suppliers": [
            ("Shenzhen Precision Parts", "CN", "electronics"),
            ("Hanoi Textile Group", "VN", "textiles"),
            ("Osaka Bearings", "JP", "industrial"),
            ("Rotterdam Chemicals", "NL", "chemicals"),
            ("Monterrey Steelworks", "MX", "metals"),
            ("Pune Auto Components", "IN", "automotive"),
            ("Busan Cold Chain", "KR", "food"),
            ("Gdansk Packaging", "PL", "packaging"),
        ],
        "lanes": [("CN", "DE"), ("VN", "NL"), ("JP", "US"), ("MX", "US"), ("IN", "GB")],
    },
    {
        "slug": "globex-manufacturing",
        "name": "Globex Manufacturing",
        "plan": "trial",
        "domain": "globex.test",
        "suppliers": [
            ("Taipei Semiconductors", "TW", "electronics"),
            ("Bremen Machine Tools", "DE", "industrial"),
            ("Sao Paulo Resins", "BR", "chemicals"),
            ("Istanbul Fasteners", "TR", "metals"),
            ("Bangkok Wiring", "TH", "electronics"),
            ("Cairo Glassworks", "EG", "materials"),
        ],
        "lanes": [("TW", "US"), ("DE", "FR"), ("BR", "ES"), ("TR", "IT"), ("TH", "AU")],
    },
]

SHIPMENTS_PER_TENANT = 120
MODES = [TransportMode.OCEAN, TransportMode.AIR, TransportMode.ROAD, TransportMode.RAIL]
MODE_WEIGHTS = [0.55, 0.2, 0.2, 0.05]
INCOTERMS = ["FOB", "CIF", "DAP", "EXW", "DDP"]


async def seed(session: AsyncSession) -> None:
    rng = random.Random(SEED)  # noqa: S311 - demo data, not cryptography

    for spec in TENANTS:
        tenant = Tenant(slug=spec["slug"], name=spec["name"], plan=spec["plan"])
        session.add(tenant)
        await session.flush()

        # Rows inserted from here on have to satisfy the tenant policy.
        await set_tenant_context(session, tenant.id)

        _add_users(session, tenant.id, str(spec["domain"]), str(spec["name"]))
        suppliers = _add_suppliers(session, tenant.id, spec["suppliers"])  # type: ignore[arg-type]
        await session.flush()

        shipments = _add_shipments(session, tenant.id, suppliers, spec["lanes"], rng)  # type: ignore[arg-type]
        await session.flush()

        _update_supplier_stats(suppliers, shipments)
        _add_contracts(session, tenant.id, suppliers, rng)
        _add_alerts(session, tenant.id, shipments, suppliers)
        await session.flush()

    await session.commit()


def _add_users(session: AsyncSession, tenant_id: UUID, domain: str, company: str) -> None:
    password_hash = pwd.hash(DEMO_PASSWORD)
    people = [
        (UserRole.ADMIN, "admin", f"{company} Admin"),
        (UserRole.ANALYST, "analyst", f"{company} Analyst"),
        (UserRole.VIEWER, "viewer", f"{company} Viewer"),
    ]
    for role, local, full_name in people:
        session.add(
            User(
                tenant_id=tenant_id,
                email=f"{local}@{domain}",
                password_hash=password_hash,
                full_name=full_name,
                role=role,
            )
        )


def _add_suppliers(
    session: AsyncSession, tenant_id: UUID, specs: list[tuple[str, str, str]]
) -> list[Supplier]:
    suppliers = [
        Supplier(
            tenant_id=tenant_id,
            name=name,
            country=country,
            category=category,
            contact_email=f"sales@{name.split()[0].lower()}.example",
        )
        for name, country, category in specs
    ]
    session.add_all(suppliers)
    return suppliers


def _add_shipments(
    session: AsyncSession,
    tenant_id: UUID,
    suppliers: list[Supplier],
    lanes: list[tuple[str, str]],
    rng: random.Random,
) -> list[Shipment]:
    shipments: list[Shipment] = []

    for i in range(SHIPMENTS_PER_TENANT):
        # Spread over the last 12 months so the timeseries chart has shape.
        created_offset = rng.randint(0, 364)
        origin, dest = rng.choice(lanes)
        supplier = rng.choice([s for s in suppliers if s.country == origin] or suppliers)
        mode = rng.choices(MODES, weights=MODE_WEIGHTS, k=1)[0]

        transit = {
            TransportMode.OCEAN: rng.randint(24, 42),
            TransportMode.AIR: rng.randint(3, 8),
            TransportMode.ROAD: rng.randint(4, 12),
            TransportMode.RAIL: rng.randint(14, 25),
        }[mode]

        departed = TODAY - timedelta(days=created_offset)
        eta = departed + timedelta(days=transit)
        status, ata, risk = _resolve_outcome(eta, mode, rng)

        shipments.append(
            Shipment(
                tenant_id=tenant_id,
                reference=f"{origin}{dest}-2026-{i + 1:04d}",
                supplier_id=supplier.id,
                origin_country=origin,
                dest_country=dest,
                mode=mode,
                incoterm=rng.choice(INCOTERMS),
                qty=rng.randint(20, 4000),
                value_usd=Decimal(rng.randint(4_000, 480_000)),
                weight_kg=Decimal(rng.randint(80, 26_000)),
                eta=eta,
                ata=ata,
                status=status,
                risk_label=risk,
                # Set explicitly, not left to now(), so the timeseries chart has
                # twelve months of history to draw.
                created_at=datetime.combine(departed, time(9, 0), tzinfo=UTC),
            )
        )

    session.add_all(shipments)
    return shipments


def _resolve_outcome(
    eta: date, mode: TransportMode, rng: random.Random
) -> tuple[ShipmentStatus, date | None, RiskLabel | None]:
    if eta > TODAY:
        at_risk = rng.random() < 0.25
        status = (
            ShipmentStatus.IN_TRANSIT
            if eta - TODAY < timedelta(days=21)
            else (ShipmentStatus.PLANNED)
        )
        return status, None, RiskLabel.AT_RISK if at_risk else RiskLabel.ON_TIME

    if rng.random() < 0.03:
        return ShipmentStatus.CANCELLED, None, None

    # Ocean freight and long lanes are the ones that slip.
    late_chance = 0.32 if mode == TransportMode.OCEAN else 0.14
    if rng.random() < late_chance:
        slip = rng.randint(1, 18)
        return ShipmentStatus.DELAYED, eta + timedelta(days=slip), RiskLabel.DELAYED

    early = rng.randint(0, 3)
    return ShipmentStatus.DELIVERED, eta - timedelta(days=early), RiskLabel.ON_TIME


def _update_supplier_stats(suppliers: list[Supplier], shipments: list[Shipment]) -> None:
    for supplier in suppliers:
        arrived = [s for s in shipments if s.supplier_id == supplier.id and s.ata is not None]
        if not arrived:
            continue
        on_time = sum(1 for s in arrived if s.ata is not None and s.ata <= s.eta)
        rate = Decimal(on_time) / Decimal(len(arrived))
        supplier.on_time_rate = round(rate, 4)
        supplier.risk_score = round(Decimal(1) - rate, 4)


def _add_contracts(
    session: AsyncSession, tenant_id: UUID, suppliers: list[Supplier], rng: random.Random
) -> None:
    for i, supplier in enumerate(suppliers[:5], start=1):
        start = TODAY - timedelta(days=rng.randint(120, 600))
        session.add(
            Contract(
                tenant_id=tenant_id,
                title=f"Master supply agreement with {supplier.name}",
                contract_number=f"MSA-2026-{i:03d}",
                supplier_id=supplier.id,
                effective_from=start,
                effective_to=start + timedelta(days=730),
                currency="USD",
                penalty_terms=(
                    "Late delivery penalty of 2% of shipment value per full week of "
                    "delay, capped at 10% of the order value."
                ),
            )
        )


def _add_alerts(
    session: AsyncSession,
    tenant_id: UUID,
    shipments: list[Shipment],
    suppliers: list[Supplier],
) -> None:
    late = [s for s in shipments if s.status == ShipmentStatus.DELAYED][:8]
    for shipment in late:
        delay = shipment.delay_days or 0
        session.add(
            Alert(
                tenant_id=tenant_id,
                kind=AlertKind.LATE_DELIVERY,
                severity=AlertSeverity.HIGH if delay > 7 else AlertSeverity.MEDIUM,
                title=f"{shipment.reference} arrived {delay} days late",
                body=(
                    f"Lane {shipment.origin_country} to {shipment.dest_country} "
                    f"via {shipment.mode}."
                ),
                entity_type="shipment",
                entity_id=shipment.id,
            )
        )

    risky = sorted(
        (s for s in suppliers if s.risk_score is not None),
        key=lambda s: s.risk_score or Decimal(0),
        reverse=True,
    )[:4]
    for supplier in risky:
        session.add(
            Alert(
                tenant_id=tenant_id,
                kind=AlertKind.SUPPLIER_RISK,
                severity=AlertSeverity.MEDIUM,
                title=f"{supplier.name} on-time rate is {supplier.on_time_rate:.0%}",
                entity_type="supplier",
                entity_id=supplier.id,
            )
        )


async def main() -> int:
    # Seeding inserts tenants, which app_user cannot do, and it is a dev-only task.
    engine = create_async_engine(settings.database_owner_url, echo=False)
    async with engine.connect() as conn:
        existing = (await conn.execute(select(Tenant.slug))).scalars().all()
    if existing:
        print(f"already seeded: {', '.join(existing)}. run `make clean` first.")
        await engine.dispose()
        return 0

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await seed(session)

    async with engine.connect() as conn:
        for table in ("tenants", "users", "suppliers", "shipments", "contracts", "alerts"):
            count = (
                await conn.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            ).scalar()
            print(f"{table:12} {count}")
    await engine.dispose()
    print("\nlogin: admin@acme.test / Demo1234!  (tenant acme-logistics)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
