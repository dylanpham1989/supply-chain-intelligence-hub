"""Aggregates in SQL, not in Python.

Pulling ten thousand rows into the process to count them is the mistake these
replace. FILTER and generate_series say it in one statement, and the tenant
predicate keeps the plan on the tenant-leading indexes even though the policy
would already restrict the rows.
"""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

SUMMARY_SQL = text("""
    SELECT
        count(*)                                                   AS total_shipments,
        count(*) FILTER (WHERE status = 'delayed')                 AS delayed,
        count(*) FILTER (WHERE status = 'in_transit')              AS in_transit,
        count(*) FILTER (WHERE status = 'delivered')               AS delivered,
        coalesce(sum(value_usd), 0)                                AS total_value_usd,
        count(*) FILTER (WHERE ata IS NOT NULL AND ata <= eta)::float
            / NULLIF(count(*) FILTER (WHERE ata IS NOT NULL), 0)   AS on_time_rate,
        avg(ata - eta) FILTER (WHERE ata IS NOT NULL AND ata > eta) AS avg_delay_days
    FROM shipments
    WHERE tenant_id = :tenant_id AND created_at >= :since
""")

BY_STATUS_SQL = text("""
    SELECT status::text AS status, count(*) AS shipments, coalesce(sum(value_usd), 0) AS value_usd
    FROM shipments
    WHERE tenant_id = :tenant_id AND created_at >= :since
    GROUP BY status
    ORDER BY shipments DESC
""")

# generate_series, so a month with no shipments is a zero rather than a gap the
# chart silently closes up.
TIMESERIES_SQL = text("""
    SELECT to_char(bucket, 'YYYY-MM')                           AS month,
           count(s.id)                                          AS shipments,
           count(s.id) FILTER (WHERE s.ata > s.eta)             AS late,
           coalesce(sum(s.value_usd), 0)                        AS value_usd
    FROM generate_series(
            date_trunc('month', CAST(:since AS timestamptz)),
            date_trunc('month', now()),
            interval '1 month'
         ) AS bucket
    LEFT JOIN shipments s
           ON date_trunc('month', s.created_at) = bucket
          AND s.tenant_id = :tenant_id
    GROUP BY bucket
    ORDER BY bucket
""")

TOP_SUPPLIERS_SQL = text("""
    SELECT sup.id::text                                          AS supplier_id,
           sup.name                                              AS name,
           count(s.id)                                           AS shipments,
           count(s.id) FILTER (WHERE s.ata IS NOT NULL AND s.ata > s.eta) AS late,
           count(s.id) FILTER (WHERE s.ata IS NOT NULL AND s.ata <= s.eta)::float
               / NULLIF(count(s.id) FILTER (WHERE s.ata IS NOT NULL), 0) AS on_time_rate
    FROM suppliers sup
    LEFT JOIN shipments s ON s.supplier_id = sup.id AND s.tenant_id = sup.tenant_id
    WHERE sup.tenant_id = :tenant_id
    GROUP BY sup.id, sup.name
    HAVING count(s.id) > 0
    ORDER BY on_time_rate NULLS LAST, shipments DESC
    LIMIT :limit
""")

RISK_BREAKDOWN_SQL = text("""
    SELECT coalesce(risk_label::text, 'unscored') AS label, count(*) AS shipments
    FROM shipments
    WHERE tenant_id = :tenant_id AND created_at >= :since
    GROUP BY risk_label
    ORDER BY shipments DESC
""")

SUPPLIER_PERFORMANCE_SQL = text("""
    SELECT count(*)                                                    AS shipments,
           count(*) FILTER (WHERE ata IS NOT NULL)                     AS delivered,
           count(*) FILTER (WHERE ata IS NOT NULL AND ata > eta)       AS late,
           count(*) FILTER (WHERE ata IS NOT NULL AND ata <= eta)::float
               / NULLIF(count(*) FILTER (WHERE ata IS NOT NULL), 0)    AS on_time_rate,
           avg(ata - eta) FILTER (WHERE ata IS NOT NULL AND ata > eta) AS avg_delay_days
    FROM shipments
    WHERE tenant_id = :tenant_id AND supplier_id = :supplier_id
""")

SUPPLIER_MONTHLY_SQL = text("""
    SELECT to_char(date_trunc('month', created_at), 'YYYY-MM')   AS month,
           count(*)                                              AS shipments,
           count(*) FILTER (WHERE ata IS NOT NULL AND ata > eta) AS late
    FROM shipments
    WHERE tenant_id = :tenant_id AND supplier_id = :supplier_id
    GROUP BY 1
    ORDER BY 1
""")


class AnalyticsRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def _one(self, stmt: Any, **params: Any) -> RowMapping:
        result = await self.session.execute(stmt, {"tenant_id": self.tenant_id, **params})
        return result.mappings().one()

    async def _all(self, stmt: Any, **params: Any) -> list[RowMapping]:
        result = await self.session.execute(stmt, {"tenant_id": self.tenant_id, **params})
        return list(result.mappings().all())

    async def summary(self, since: date) -> RowMapping:
        return await self._one(SUMMARY_SQL, since=since)

    async def by_status(self, since: date) -> list[RowMapping]:
        return await self._all(BY_STATUS_SQL, since=since)

    async def timeseries(self, since: date) -> list[RowMapping]:
        return await self._all(TIMESERIES_SQL, since=since)

    async def top_suppliers(self, limit: int) -> list[RowMapping]:
        return await self._all(TOP_SUPPLIERS_SQL, limit=limit)

    async def risk_breakdown(self, since: date) -> list[RowMapping]:
        return await self._all(RISK_BREAKDOWN_SQL, since=since)

    async def supplier_performance(self, supplier_id: UUID) -> RowMapping:
        return await self._one(SUPPLIER_PERFORMANCE_SQL, supplier_id=supplier_id)

    async def supplier_monthly(self, supplier_id: UUID) -> list[RowMapping]:
        return await self._all(SUPPLIER_MONTHLY_SQL, supplier_id=supplier_id)
