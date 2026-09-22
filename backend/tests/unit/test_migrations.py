"""Guards against the schema and the migrations drifting apart."""

import re
from pathlib import Path

from app.models import TENANT_SCOPED_TABLES, Base

MIGRATIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _tables_with_a_policy_in_migrations() -> set[str]:
    """Every table a migration creates a tenant policy for."""
    tables: set[str] = set()
    for path in sorted(MIGRATIONS.glob("*.py")):
        source = path.read_text()
        literals = dict(re.findall(r'^([A-Z_]+) = "([a-z_]+)"$', source, re.M))
        for name in re.findall(r"CREATE POLICY tenant_isolation ON \{(\w+)\}", source):
            if name in literals:
                tables.add(literals[name])
        block = re.search(r"TENANT_SCOPED_TABLES = \((.*?)\)", source, re.S)
        if block and "CREATE POLICY" in source:
            tables.update(re.findall(r'"([a-z_]+)"', block.group(1)))
    return tables


def test_migrations_create_a_policy_for_every_tenant_table() -> None:
    """A tenant table with no policy is a silent leak, so catch it at test time.

    Migrations spell their tables out instead of importing the list, because a
    migration has to keep describing the schema as it was. A new tenant table
    fails this until its own policy migration ships.
    """
    assert _tables_with_a_policy_in_migrations() == set(TENANT_SCOPED_TABLES)


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
