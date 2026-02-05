"""Type definitions for authentication."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenClaims:
    """Claims embedded in a JWT token.

    Attributes:
        user_id: The authenticated user's ID
        tenant_id: The active tenant ID (if user is in a tenant context)
        role: The user's role within the tenant
        exp: Token expiration timestamp
        iat: Token issued-at timestamp
        type: Token type ("access" or "refresh")
    """

    user_id: str
    tenant_id: str | None = None
    role: str | None = None
    exp: int = 0
    iat: int = 0
    type: str = "access"


@dataclass
class TokenPair:
    """A pair of access and refresh tokens.

    Attributes:
        access_token: Short-lived token for API access (15 min)
        refresh_token: Long-lived token for getting new access tokens (7 days)
        token_type: Always "Bearer"
        expires_in: Access token TTL in seconds
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900  # 15 minutes


@dataclass
class TenantInfo:
    """Information about a tenant the user belongs to.

    Attributes:
        id: Tenant ID
        name: Tenant display name
        slug: Tenant URL slug
        role: User's role in this tenant
    """

    id: str
    name: str
    slug: str
    role: str


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user in the system.

    Attributes:
        user_id: The user's unique ID
        email: User's email address
        name: User's display name
        active_tenant_id: Currently active tenant ID (from JWT)
        active_role: User's role in the active tenant
        tenants: List of tenants the user belongs to
    """

    user_id: str
    email: str
    name: str
    active_tenant_id: str | None = None
    active_role: str | None = None
    tenants: list[TenantInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "userId": self.user_id,
            "email": self.email,
            "name": self.name,
            "activeTenantId": self.active_tenant_id,
            "activeRole": self.active_role,
            "tenants": [
                {
                    "id": t.id,
                    "name": t.name,
                    "slug": t.slug,
                    "role": t.role,
                }
                for t in self.tenants
            ],
        }
