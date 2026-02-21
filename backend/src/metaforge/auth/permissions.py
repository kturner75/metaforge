"""Permission checking for entity access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from metaforge.validation import UserContext

if TYPE_CHECKING:
    from metaforge.metadata.loader import EntityModel, FieldDefinition


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


def _role_level(role: str | None) -> int:
    """Return numeric level for a role name, 0 if unknown/None."""
    return ROLE_HIERARCHY.get(role or "", 0)


def _user_role_level(user_context: UserContext | None) -> int:
    """Return the numeric role level for the current user."""
    if not user_context or not user_context.roles:
        return 0
    return _role_level(user_context.roles[0])


def can_access_entity(
    entity_name: str,
    entity_scope: str,
    operation: str,
    user_context: UserContext | None,
    auth_required: bool = True,
    entity_model: "EntityModel | None" = None,
) -> tuple[bool, str | None]:
    """Check if the user can perform an operation on an entity.

    Args:
        entity_name: Name of the entity
        entity_scope: "global" or "tenant"
        operation: "read", "create", "update", or "delete"
        user_context: The authenticated user context (None if unauthenticated)
        auth_required: Whether authentication is required (False allows unauthenticated access)
        entity_model: Optional entity model for per-entity permission overrides

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

    user_level = _user_role_level(user_context)

    # Handle global entities (User, Tenant, TenantMembership)
    if entity_scope == "global" or entity_name in GLOBAL_ENTITIES:
        if operation == "read":
            return True, None
        else:
            if user_level < ROLE_HIERARCHY["admin"]:
                return False, f"Admin role required to {operation} {entity_name}"
            return True, None

    # Handle tenant-scoped entities
    if not user_context.tenant_id:
        return False, "No active tenant. Please select a tenant."

    # Determine minimum role thresholds — use entity permissions if declared, else defaults
    perms = entity_model.permissions if entity_model else None
    thresholds: dict[str, str] = {
        "read": perms.read if perms else "readonly",
        "create": perms.create if perms else "user",
        "update": perms.update if perms else "user",
        "delete": perms.delete if perms else "manager",
    }

    required_role = thresholds.get(operation, "readonly")
    required_level = _role_level(required_role)

    if user_level < required_level:
        return False, f"{required_role.capitalize()} role or higher required to {operation} records"

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


def get_field_access(
    field_def: "FieldDefinition",
    user_context: UserContext | None,
    entity_model: "EntityModel | None" = None,
) -> dict[str, bool]:
    """Return the effective read/write access for a field given the user's role.

    Args:
        field_def: The field definition
        user_context: The authenticated user context
        entity_model: Optional entity model for entity-level field policies

    Returns:
        {"read": bool, "write": bool}
    """
    user_level = _user_role_level(user_context)

    # Look up field policy: entity-level policies take precedence over field-level
    field_name = field_def.name
    field_policy = None

    if entity_model and entity_model.permissions:
        field_policy = entity_model.permissions.field_policies.get(field_name)

    if field_policy is None and field_def.permissions:
        field_policy = field_def.permissions

    if field_policy is None:
        # No policy — full access (subject to readOnly flag)
        return {
            "read": True,
            "write": not field_def.read_only and not field_def.primary_key,
        }

    can_read = user_level >= _role_level(field_policy.read)
    can_write = (
        can_read
        and not field_def.read_only
        and not field_def.primary_key
        and user_level >= _role_level(field_policy.write)
    )
    return {"read": can_read, "write": can_write}


def apply_field_read_policy(
    record: dict,
    entity_model: "EntityModel | None",
    user_context: UserContext | None,
) -> dict:
    """Strip fields the user cannot read from a record dict.

    Args:
        record: The raw record dict from the database
        entity_model: The entity model for field policy lookup
        user_context: The authenticated user context

    Returns:
        A copy of the record with restricted fields removed
    """
    if entity_model is None:
        return record

    perms = entity_model.permissions
    if perms is None or not perms.field_policies:
        return record

    user_level = _user_role_level(user_context)
    result = dict(record)

    for field_name, policy in perms.field_policies.items():
        if user_level < _role_level(policy.read):
            result.pop(field_name, None)
            # Also strip any hydrated display value
            result.pop(f"{field_name}_display", None)

    return result


def apply_field_write_policy(
    data: dict,
    entity_model: "EntityModel | None",
    user_context: UserContext | None,
) -> dict:
    """Strip fields the user cannot write from an incoming payload.

    Args:
        data: The write payload from the client
        entity_model: The entity model for field policy lookup
        user_context: The authenticated user context

    Returns:
        A copy of the data with write-restricted fields removed
    """
    if entity_model is None:
        return data

    perms = entity_model.permissions
    if perms is None or not perms.field_policies:
        return data

    user_level = _user_role_level(user_context)
    result = dict(data)

    for field_name, policy in perms.field_policies.items():
        # Cannot write if below write threshold OR below read threshold
        if user_level < _role_level(policy.read) or user_level < _role_level(policy.write):
            result.pop(field_name, None)

    return result
