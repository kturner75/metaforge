"""Authentication module for MetaForge."""

from metaforge.auth.types import (
    AuthenticatedUser,
    TokenClaims,
    TokenPair,
)
from metaforge.auth.password import PasswordService
from metaforge.auth.jwt_service import JWTService
from metaforge.auth.middleware import AuthMiddleware, get_user_context
from metaforge.auth.dependencies import (
    get_current_user,
    require_role,
    require_authenticated,
)
from metaforge.auth.permissions import can_access_entity, ROLE_HIERARCHY

__all__ = [
    "AuthenticatedUser",
    "TokenClaims",
    "TokenPair",
    "PasswordService",
    "JWTService",
    "AuthMiddleware",
    "get_user_context",
    "get_current_user",
    "require_role",
    "require_authenticated",
    "can_access_entity",
    "ROLE_HIERARCHY",
]
