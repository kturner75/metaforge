"""FastAPI dependencies for authentication."""

from functools import wraps
from typing import Callable

from fastapi import Depends, HTTPException, Request

from metaforge.auth.middleware import get_user_context
from metaforge.auth.permissions import ROLE_HIERARCHY
from metaforge.validation import UserContext


def get_current_user(request: Request) -> UserContext | None:
    """Dependency to get the current user context.

    This is a soft dependency - returns None if not authenticated.
    Use require_authenticated for endpoints that require auth.

    Args:
        request: The FastAPI request

    Returns:
        UserContext if authenticated, None otherwise
    """
    return get_user_context(request)


def require_authenticated(request: Request) -> UserContext:
    """Dependency that requires authentication.

    Use this for endpoints that must have an authenticated user.

    Args:
        request: The FastAPI request

    Returns:
        UserContext for the authenticated user

    Raises:
        HTTPException 401 if not authenticated
    """
    user_context = get_user_context(request)
    if not user_context:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_context


def require_role(*required_roles: str) -> Callable[[Request], UserContext]:
    """Create a dependency that requires specific roles.

    The user must have at least one of the required roles, or a role
    higher in the hierarchy that implies the required role.

    Args:
        required_roles: One or more role names required for access

    Returns:
        A FastAPI dependency function

    Example:
        @app.get("/admin-only")
        async def admin_endpoint(user: UserContext = Depends(require_role("admin"))):
            ...
    """

    def dependency(request: Request) -> UserContext:
        user_context = require_authenticated(request)

        # Check if user has any of the required roles
        user_roles = user_context.roles or []

        for user_role in user_roles:
            # Check direct match
            if user_role in required_roles:
                return user_context

            # Check hierarchy - higher roles can access lower role endpoints
            user_level = ROLE_HIERARCHY.get(user_role, -1)
            for required_role in required_roles:
                required_level = ROLE_HIERARCHY.get(required_role, 999)
                if user_level >= required_level:
                    return user_context

        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions. Required roles: {', '.join(required_roles)}",
        )

    return dependency


def require_tenant(request: Request) -> UserContext:
    """Dependency that requires authentication with an active tenant.

    Use this for endpoints that work with tenant-scoped data.

    Args:
        request: The FastAPI request

    Returns:
        UserContext with tenant_id set

    Raises:
        HTTPException 401 if not authenticated
        HTTPException 400 if no tenant selected
    """
    user_context = require_authenticated(request)

    if not user_context.tenant_id:
        raise HTTPException(
            status_code=400,
            detail="No tenant selected. Please select a tenant or include tenant_id in your token.",
        )

    return user_context
