from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.ingestion.base import ParsedRow
from app.models import Shipment, Supplier
from app.models.enums import ShipmentStatus, TransportMode


async def import_rows(
    session: AsyncSession, tenant_id: UUID, rows: list[ParsedRow]
) -> tuple[int, list[dict[str, Any]]]:
    """Turn manifest rows into shipments.

    Structured data belongs in the table it describes. Counting late deliveries
    with sql is exact; asking a vector index the same question is not.
    """
    existing = set(
        (await session.execute(select(Shipment.reference).where(Shipment.tenant_id == tenant_id)))
        .scalars()
        .all()
    )
    suppliers = await _supplier_index(session, tenant_id)

    imported = 0
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        data = row.data
        reference = str(data["reference"])

        if reference in existing or reference in seen:
            # Re-uploading the same manifest should not double the shipments.
            skipped.append({"line": row.line_no, "reason": f"{reference} already imported"})
            continue
        seen.add(reference)

        supplier_id = None
        name = data.get("supplier_name")
        if name:
            supplier_id = suppliers.get(name.strip().lower())
            if supplier_id is None:
                supplier = Supplier(
                    tenant_id=tenant_id,
                    name=name.strip()[:200],
                    country=data["origin_country"],
                    category="unclassified",
                )
                session.add(supplier)
                await session.flush()
                supplier_id = supplier.id
                suppliers[name.strip().lower()] = supplier_id

        ata = data.get("ata")
        status = (
            ShipmentStatus.DELAYED
            if ata and ata > data["eta"]
            else ShipmentStatus.DELIVERED
            if ata
            else ShipmentStatus.IN_TRANSIT
        )

        session.add(
            Shipment(
                tenant_id=tenant_id,
                reference=reference,
                supplier_id=supplier_id,
                origin_country=data["origin_country"],
                dest_country=data["dest_country"],
                mode=TransportMode(data["mode"]),
                incoterm=data.get("incoterm"),
                qty=data["qty"],
                value_usd=data["value_usd"],
                weight_kg=data.get("weight_kg"),
                eta=data["eta"],
                ata=ata,
                status=status,
            )
        )
        imported += 1

    await session.flush()
    return imported, skipped


async def _supplier_index(session: AsyncSession, tenant_id: UUID) -> dict[str, UUID]:
    rows = await session.execute(
        select(Supplier.name, Supplier.id).where(Supplier.tenant_id == tenant_id)
    )
    return {name.strip().lower(): supplier_id for name, supplier_id in rows}
