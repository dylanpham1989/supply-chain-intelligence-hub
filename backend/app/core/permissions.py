from app.models.enums import UserRole

WILDCARD = "*"

# Endpoints ask for a permission, never for a role. Adding a role is a new entry
# here rather than an edit to every route.
PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.ADMIN: frozenset({WILDCARD}),
    UserRole.ANALYST: frozenset(
        {
            "shipment:read",
            "shipment:write",
            "supplier:read",
            "supplier:write",
            "contract:read",
            "document:read",
            "document:upload",
            "insight:read",
            "insight:create",
            "alert:read",
            "alert:write",
            "user:read",
        }
    ),
    UserRole.VIEWER: frozenset(
        {
            "shipment:read",
            "supplier:read",
            "contract:read",
            "document:read",
            "insight:read",
            "alert:read",
        }
    ),
}

# The full vocabulary, including permissions only the admin wildcard covers.
# test_permissions asserts every string passed to require() appears here.
KNOWN_PERMISSIONS: frozenset[str] = frozenset(
    {
        "shipment:read",
        "shipment:write",
        "shipment:delete",
        "supplier:read",
        "supplier:write",
        "contract:read",
        "contract:write",
        "document:read",
        "document:upload",
        "document:delete",
        "insight:read",
        "insight:create",
        "alert:read",
        "alert:write",
        "user:read",
        "user:write",
        "tenant:write",
    }
)


def has_permission(role: UserRole, permission: str) -> bool:
    granted = PERMISSIONS.get(role, frozenset())
    return WILDCARD in granted or permission in granted
