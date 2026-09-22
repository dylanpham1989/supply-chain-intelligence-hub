"""Guards against the schema and the migrations drifting apart."""

import re
from pathlib import Path

from app.models import TENANT_SCOPED_TABLES, Base

MIGRATIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _tables_in_latest_rls_migration() -> set[str]:
    source = (MIGRATIONS / "0002_row_level_security.py").read_text()
    block = re.search(r"TENANT_SCOPED_TABLES = \((.*?)\)", source, re.S)
    assert block, "could not find the table list in the rls migration"
    return set(re.findall(r'"([a-z_]+)"', block.group(1)))


def test_rls_migration_covers_every_tenant_table() -> None:
    """A tenant table with no policy is a silent leak, so catch it at test time.

    The migration spells the list out instead of importing it, because a migration
    has to keep describing the schema as it was. When a later phase adds a tenant
    table, this fails until that phase ships its own policy migration.
    """
    assert _tables_in_latest_rls_migration() == set(TENANT_SCOPED_TABLES)


def test_every_tenant_scoped_table_exists_in_the_metadata() -> None:
    missing = [t for t in TENANT_SCOPED_TABLES if t not in Base.metadata.tables]

    assert missing == []


def test_tables_with_a_tenant_id_column_are_all_declared_tenant_scoped() -> None:
    """Catches the reverse mistake: a new model that nobody added to the list."""
    with_tenant = {name for name, table in Base.metadata.tables.items() if "tenant_id" in table.c}

    assert with_tenant == set(TENANT_SCOPED_TABLES)


def test_migration_filenames_are_ordered() -> None:
    names = sorted(p.name for p in MIGRATIONS.glob("*.py"))

    assert names == sorted(names)
    assert all(re.match(r"^\d{4}_[a-z_]+\.py$", n) for n in names), names
