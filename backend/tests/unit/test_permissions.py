import ast
import re
from pathlib import Path

import pytest

from app.core.permissions import KNOWN_PERMISSIONS, PERMISSIONS, has_permission
from app.models.enums import UserRole

API_DIR = Path(__file__).resolve().parents[2] / "app" / "api"

ROLE_MATRIX = [
    (UserRole.ADMIN, "shipment:read", True),
    (UserRole.ADMIN, "shipment:write", True),
    (UserRole.ADMIN, "user:write", True),
    (UserRole.ADMIN, "tenant:write", True),
    (UserRole.ANALYST, "shipment:read", True),
    (UserRole.ANALYST, "shipment:write", True),
    (UserRole.ANALYST, "document:upload", True),
    (UserRole.ANALYST, "insight:create", True),
    (UserRole.ANALYST, "user:read", True),
    (UserRole.ANALYST, "user:write", False),
    (UserRole.ANALYST, "tenant:write", False),
    (UserRole.ANALYST, "shipment:delete", False),
    (UserRole.VIEWER, "shipment:read", True),
    (UserRole.VIEWER, "alert:read", True),
    (UserRole.VIEWER, "shipment:write", False),
    (UserRole.VIEWER, "document:upload", False),
    (UserRole.VIEWER, "insight:create", False),
    (UserRole.VIEWER, "user:read", False),
    (UserRole.VIEWER, "user:write", False),
]


@pytest.mark.parametrize(("role", "permission", "expected"), ROLE_MATRIX)
def test_role_permission_matrix(role: UserRole, permission: str, expected: bool) -> None:
    assert has_permission(role, permission) is expected


def test_admin_holds_every_permission() -> None:
    for permission in KNOWN_PERMISSIONS:
        assert has_permission(UserRole.ADMIN, permission)


def test_viewer_holds_no_write_permission() -> None:
    writes = [p for p in KNOWN_PERMISSIONS if p.split(":")[1] != "read"]

    assert [p for p in writes if has_permission(UserRole.VIEWER, p)] == []


def test_analyst_permissions_are_a_subset_of_known_ones() -> None:
    assert PERMISSIONS[UserRole.ANALYST] <= KNOWN_PERMISSIONS


def test_every_permission_asked_for_by_a_route_exists() -> None:
    """A typo in require("shipmnt:read") would deny everyone but the admin wildcard.

    Nothing would fail at import or at request time, so read the strings out of
    the source instead.
    """
    asked: set[str] = set()
    for path in API_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require"
            ):
                asked.update(
                    arg.value
                    for arg in node.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                )

    assert asked, "no require() calls found, has the guard moved?"
    assert asked <= KNOWN_PERMISSIONS, f"unknown permissions: {sorted(asked - KNOWN_PERMISSIONS)}"


def test_permission_strings_follow_the_resource_action_shape() -> None:
    bad = [p for p in KNOWN_PERMISSIONS if not re.fullmatch(r"[a-z]+:[a-z]+", p)]

    assert bad == []
