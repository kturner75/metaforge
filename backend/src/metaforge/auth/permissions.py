"""Permission checking for entity access."""

from metaforge.validation import UserContext


# Role hierarchy - higher number = more permissions
# Higher roles automatically have all permissions of lower roles
ROLE_HIERARCHY = {
    "readonly": 1,
    "user": 2,
    "manager": 3,
    "admin": 4,
}

# Global entities that require admin role for write operations
GLOBAL_ENTITIES = {"User", "Tenant", "TenantMembership"}


def can_access_entity(
    entity_name: str,
    entity_scope: str,
    operation: str,
    user_context: UserContext | None,
    auth_required: bool = True,
) -> tuple[bool, str | None]:
    """Check if the user can perform an operation on an entity.

    Args:
        entity_name: Name of the entity
        entity_scope: "global" or "tenant"
        operation: "read", "create", "update", or "delete"
        user_context: The authenticated user context (None if unauthenticated)
        auth_required: Whether authentication is required (False allows unauthenticated access)

    Returns:
        Tuple of (allowed, error_message). error_message is None if allowed.
    """
    # When auth is not required and no user context, allow access to non-global entities
    if not user_context:
        if not auth_required:
            # Allow unauthenticated access when auth is not configured
            if entity_scope != "global" and entity_name not in GLOBAL_ENTITIES:
                return True, None
        return False, "Authentication required"

    user_role = user_context.roles[0] if user_context.roles else None
    role_level = ROLE_HIERARCHY.get(user_role, 0) if user_role else 0

    # Handle global entities (User, Tenant, TenantMembership)
    if entity_scope == "global" or entity_name in GLOBAL_ENTITIES:
        if operation == "read":
            # Anyone authenticated can read global entities
            # (they'll be filtered appropriately)
            return True, None
        else:
            # Write operations require admin role
            if role_level < ROLE_HIERARCHY["admin"]:
                return False, f"Admin role required to {operation} {entity_name}"
            return True, None

    # Handle tenant-scoped entities
    # Must have an active tenant
    if not user_context.tenant_id:
        return False, "No active tenant. Please select a tenant."

    # Check operation-specific permissions
    if operation == "read":
        # All roles can read
        return True, None
    elif operation in ("create", "update"):
        # readonly cannot create/update
        if role_level < ROLE_HIERARCHY["user"]:
            return False, f"User role or higher required to {operation} records"
        return True, None
    elif operation == "delete":
        # Only manager+ can delete
        if role_level < ROLE_HIERARCHY["manager"]:
            return False, "Manager role or higher required to delete records"
        return True, None

    return True, None


def has_role_or_higher(user_context: UserContext | None, required_role: str) -> bool:
    """Check if user has the required role or a higher one.

    Args:
        user_context: The user context
        required_role: The minimum required role

    Returns:
        True if user has the required role or higher
    """
    if not user_context or not user_context.roles:
        return False

    user_role = user_context.roles[0]
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 999)

    return user_level >= required_level


def get_effective_tenant_filter(
    entity_scope: str,
    user_context: UserContext | None,
) -> dict | None:
    """Get the tenant filter to apply to queries.

    For tenant-scoped entities, returns a filter to restrict
    results to the user's active tenant.

    Args:
        entity_scope: "global" or "tenant"
        user_context: The user context

    Returns:
        Filter dict to merge with query, or None for global entities
    """
    if entity_scope == "global":
        return None

    if not user_context or not user_context.tenant_id:
        # No tenant context - return impossible filter to prevent data leak
        return {"tenantId": {"eq": "__no_tenant__"}}

    return {"tenantId": {"eq": user_context.tenant_id}}
