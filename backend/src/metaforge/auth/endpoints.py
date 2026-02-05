"""Authentication API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from metaforge.auth.dependencies import require_authenticated
from metaforge.auth.jwt_service import JWTService, InvalidTokenError, TokenExpiredError
from metaforge.auth.password import PasswordService
from metaforge.auth.types import AuthenticatedUser, TenantInfo, TokenPair
from metaforge.validation import UserContext


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Request body for login."""

    email: str
    password: str
    tenant_id: str | None = None


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str
    tenant_id: str | None = None


class LoginResponse(BaseModel):
    """Response body for login."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class MeResponse(BaseModel):
    """Response body for /me endpoint."""

    user_id: str
    email: str
    name: str
    active_tenant_id: str | None
    active_role: str | None
    tenants: list[dict[str, Any]]


class RegisterRequest(BaseModel):
    """Request body for user registration."""

    email: str
    password: str
    name: str
    tenant_id: str | None = None  # Optional: add user to tenant (admin only)
    role: str = "user"  # Role in tenant (admin only)


class RegisterResponse(BaseModel):
    """Response body for registration."""

    user_id: str
    email: str
    name: str
    tenant_id: str | None = None
    role: str | None = None


class ChangePasswordRequest(BaseModel):
    """Request body for changing password."""

    current_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    """Request body for password reset request."""

    email: str


class ResetPasswordResponse(BaseModel):
    """Response body for password reset request."""

    message: str
    reset_token: str  # In production, this would be emailed instead


class ResetPasswordConfirm(BaseModel):
    """Request body for password reset confirmation."""

    reset_token: str
    new_password: str


def create_auth_router(
    jwt_service: JWTService,
    password_service: PasswordService,
    get_db,  # Callable that returns the database adapter
    get_metadata_loader,  # Callable that returns the metadata loader
) -> APIRouter:
    """Create the auth router with injected dependencies.

    Args:
        jwt_service: JWT service for token operations
        password_service: Password service for verification
        get_db: Function returning the database adapter
        get_metadata_loader: Function returning the metadata loader

    Returns:
        Configured APIRouter
    """

    @router.post("/login", response_model=LoginResponse)
    async def login(request: LoginRequest) -> LoginResponse:
        """Authenticate user and return tokens.

        Args:
            request: Login credentials

        Returns:
            Token pair with access and refresh tokens

        Raises:
            HTTPException 401 if credentials invalid
            HTTPException 403 if user inactive or no tenant access
        """
        db = get_db()
        metadata_loader = get_metadata_loader()

        if not db or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        # Get User entity
        user_entity = metadata_loader.get_entity("User")
        if not user_entity:
            raise HTTPException(500, "User entity not configured")

        # Find user by email
        result = db.query(
            user_entity,
            filter={
                "conditions": [{"field": "email", "operator": "eq", "value": request.email}]
            },
            limit=1,
        )

        users = result.get("data", [])
        if not users:
            raise HTTPException(401, "Invalid email or password")

        user = users[0]

        # Check password
        password_hash = user.get("passwordHash")
        if not password_hash or not password_service.verify(request.password, password_hash):
            raise HTTPException(401, "Invalid email or password")

        # Check if user is active
        if not user.get("active", True):
            raise HTTPException(403, "User account is disabled")

        user_id = user.get("id")

        # Get user's tenant memberships
        membership_entity = metadata_loader.get_entity("TenantMembership")
        if not membership_entity:
            raise HTTPException(500, "TenantMembership entity not configured")

        memberships_result = db.query(
            membership_entity,
            filter={
                "conditions": [{"field": "userId", "operator": "eq", "value": user_id}]
            },
        )
        memberships = memberships_result.get("data", [])

        # Determine which tenant to use
        tenant_id = None
        role = None

        if request.tenant_id:
            # User specified a tenant - verify membership
            membership = next(
                (m for m in memberships if m.get("tenantId") == request.tenant_id),
                None,
            )
            if not membership:
                raise HTTPException(403, "You are not a member of the specified tenant")

            # Verify tenant is active
            tenant_entity = metadata_loader.get_entity("Tenant")
            if tenant_entity:
                tenant = db.get(tenant_entity, request.tenant_id)
                if not tenant or not tenant.get("active", True):
                    raise HTTPException(403, "Tenant is disabled")

            tenant_id = request.tenant_id
            role = membership.get("role", "user")

        elif memberships:
            # No tenant specified - use first available membership
            membership = memberships[0]
            tenant_id = membership.get("tenantId")
            role = membership.get("role", "user")

        # Generate tokens
        token_pair = jwt_service.generate_token_pair(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
        )

        return LoginResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            token_type=token_pair.token_type,
            expires_in=token_pair.expires_in,
        )

    @router.post("/register", response_model=RegisterResponse, status_code=201)
    async def register(request: RegisterRequest, http_request: Request) -> RegisterResponse:
        """Register a new user.

        If tenant_id is provided, requires admin authentication and adds user
        to the specified tenant with the given role.

        If no tenant_id is provided, creates a standalone user (self-registration).

        Args:
            request: Registration details

        Returns:
            Created user info

        Raises:
            HTTPException 400 if email already exists
            HTTPException 403 if tenant_id provided without admin auth
        """
        db = get_db()
        metadata_loader = get_metadata_loader()

        if not db or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        # Check if adding to tenant (requires admin auth)
        user_context = getattr(http_request.state, "user_context", None)

        if request.tenant_id:
            if not user_context:
                raise HTTPException(403, "Authentication required to add users to tenants")
            user_role = user_context.roles[0] if user_context.roles else None
            if user_role != "admin":
                raise HTTPException(403, "Admin role required to add users to tenants")

            # Verify tenant exists
            tenant_entity = metadata_loader.get_entity("Tenant")
            if tenant_entity:
                tenant = db.get(tenant_entity, request.tenant_id)
                if not tenant:
                    raise HTTPException(400, "Tenant not found")
                if not tenant.get("active", True):
                    raise HTTPException(400, "Tenant is disabled")

        # Check if email already exists
        user_entity = metadata_loader.get_entity("User")
        if not user_entity:
            raise HTTPException(500, "User entity not configured")

        existing = db.query(
            user_entity,
            filter={
                "conditions": [{"field": "email", "operator": "eq", "value": request.email}]
            },
            limit=1,
        )
        if existing.get("data"):
            raise HTTPException(400, "A user with this email already exists")

        # Create user with hashed password
        user_data = {
            "email": request.email,
            "passwordHash": password_service.hash(request.password),
            "name": request.name,
            "active": 1,
        }
        user = db.create(user_entity, user_data)
        user_id = user.get("id")

        # If tenant specified, create membership
        tenant_id = None
        role = None

        if request.tenant_id:
            membership_entity = metadata_loader.get_entity("TenantMembership")
            if membership_entity:
                membership_data = {
                    "userId": user_id,
                    "tenantId": request.tenant_id,
                    "role": request.role,
                }
                db.create(membership_entity, membership_data)
                tenant_id = request.tenant_id
                role = request.role

        return RegisterResponse(
            user_id=user_id,
            email=user.get("email"),
            name=user.get("name"),
            tenant_id=tenant_id,
            role=role,
        )

    @router.post("/refresh", response_model=LoginResponse)
    async def refresh(request: RefreshRequest) -> LoginResponse:
        """Refresh access token using refresh token.

        Optionally switch to a different tenant during refresh.

        Args:
            request: Refresh token and optional tenant ID

        Returns:
            New token pair

        Raises:
            HTTPException 401 if refresh token invalid or expired
            HTTPException 403 if user inactive or no tenant access
        """
        db = get_db()
        metadata_loader = get_metadata_loader()

        if not db or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        # Validate refresh token
        try:
            user_id = jwt_service.validate_refresh_token(request.refresh_token)
        except TokenExpiredError:
            raise HTTPException(401, "Refresh token has expired. Please log in again.")
        except InvalidTokenError as e:
            raise HTTPException(401, f"Invalid refresh token: {e}")

        # Verify user still exists and is active
        user_entity = metadata_loader.get_entity("User")
        if not user_entity:
            raise HTTPException(500, "User entity not configured")

        user = db.get(user_entity, user_id)
        if not user:
            raise HTTPException(401, "User not found")
        if not user.get("active", True):
            raise HTTPException(403, "User account is disabled")

        # Get user's tenant memberships
        membership_entity = metadata_loader.get_entity("TenantMembership")
        if not membership_entity:
            raise HTTPException(500, "TenantMembership entity not configured")

        memberships_result = db.query(
            membership_entity,
            filter={
                "conditions": [{"field": "userId", "operator": "eq", "value": user_id}]
            },
        )
        memberships = memberships_result.get("data", [])

        # Determine tenant
        tenant_id = None
        role = None

        if request.tenant_id:
            membership = next(
                (m for m in memberships if m.get("tenantId") == request.tenant_id),
                None,
            )
            if not membership:
                raise HTTPException(403, "You are not a member of the specified tenant")

            tenant_entity = metadata_loader.get_entity("Tenant")
            if tenant_entity:
                tenant = db.get(tenant_entity, request.tenant_id)
                if not tenant or not tenant.get("active", True):
                    raise HTTPException(403, "Tenant is disabled")

            tenant_id = request.tenant_id
            role = membership.get("role", "user")
        elif memberships:
            membership = memberships[0]
            tenant_id = membership.get("tenantId")
            role = membership.get("role", "user")

        # Generate new tokens
        token_pair = jwt_service.generate_token_pair(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
        )

        return LoginResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            token_type=token_pair.token_type,
            expires_in=token_pair.expires_in,
        )

    @router.get("/me")
    async def get_me(
        http_request: Request,
        user_context: UserContext = Depends(require_authenticated),
    ) -> dict[str, Any]:
        """Get current user information and available tenants.

        Returns:
            User info including all tenant memberships
        """
        db = get_db()
        metadata_loader = get_metadata_loader()

        if not db or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        # Get user details
        user_entity = metadata_loader.get_entity("User")
        if not user_entity:
            raise HTTPException(500, "User entity not configured")

        user = db.get(user_entity, user_context.user_id)
        if not user:
            raise HTTPException(404, "User not found")

        # Get all tenant memberships with tenant details
        membership_entity = metadata_loader.get_entity("TenantMembership")
        tenant_entity = metadata_loader.get_entity("Tenant")

        tenants: list[TenantInfo] = []

        if membership_entity:
            memberships_result = db.query(
                membership_entity,
                filter={
                    "conditions": [
                        {"field": "userId", "operator": "eq", "value": user_context.user_id}
                    ]
                },
            )

            for membership in memberships_result.get("data", []):
                tenant_id = membership.get("tenantId")
                if tenant_entity and tenant_id:
                    tenant = db.get(tenant_entity, tenant_id)
                    if tenant and tenant.get("active", True):
                        tenants.append(
                            TenantInfo(
                                id=tenant_id,
                                name=tenant.get("name", ""),
                                slug=tenant.get("slug", ""),
                                role=membership.get("role", "user"),
                            )
                        )

        authenticated_user = AuthenticatedUser(
            user_id=user_context.user_id,
            email=user.get("email", ""),
            name=user.get("name", ""),
            active_tenant_id=user_context.tenant_id,
            active_role=user_context.roles[0] if user_context.roles else None,
            tenants=tenants,
        )

        return authenticated_user.to_dict()

    @router.post("/change-password")
    async def change_password(
        request: ChangePasswordRequest,
        http_request: Request,
        user_context: UserContext = Depends(require_authenticated),
    ) -> dict[str, str]:
        """Change password for authenticated user.

        Args:
            request: Current and new password

        Returns:
            Success message

        Raises:
            HTTPException 400 if current password is incorrect
        """
        db = get_db()
        metadata_loader = get_metadata_loader()

        if not db or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        user_entity = metadata_loader.get_entity("User")
        if not user_entity:
            raise HTTPException(500, "User entity not configured")

        user = db.get(user_entity, user_context.user_id)
        if not user:
            raise HTTPException(404, "User not found")

        # Verify current password
        current_hash = user.get("passwordHash")
        if not current_hash or not password_service.verify(request.current_password, current_hash):
            raise HTTPException(400, "Current password is incorrect")

        # Update password
        new_hash = password_service.hash(request.new_password)
        db.update(user_entity, user_context.user_id, {"passwordHash": new_hash})

        return {"message": "Password changed successfully"}

    @router.post("/reset-password/request", response_model=ResetPasswordResponse)
    async def request_password_reset(request: ResetPasswordRequest) -> ResetPasswordResponse:
        """Request a password reset token.

        In production, this would send the token via email.
        For development, the token is returned in the response.

        Args:
            request: Email address

        Returns:
            Reset token (for dev) or success message
        """
        db = get_db()
        metadata_loader = get_metadata_loader()

        if not db or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        user_entity = metadata_loader.get_entity("User")
        if not user_entity:
            raise HTTPException(500, "User entity not configured")

        # Find user by email
        result = db.query(
            user_entity,
            filter={
                "conditions": [{"field": "email", "operator": "eq", "value": request.email}]
            },
            limit=1,
        )

        users = result.get("data", [])
        if not users:
            # Don't reveal whether email exists - return same response
            # In production, you'd still return success but not send email
            raise HTTPException(404, "If an account exists with this email, a reset link will be sent")

        user = users[0]
        user_id = user.get("id")

        # Generate reset token
        reset_token = jwt_service.generate_reset_token(user_id)

        return ResetPasswordResponse(
            message="Password reset token generated. In production, this would be emailed.",
            reset_token=reset_token,
        )

    @router.post("/reset-password/confirm")
    async def confirm_password_reset(request: ResetPasswordConfirm) -> dict[str, str]:
        """Confirm password reset using token.

        Args:
            request: Reset token and new password

        Returns:
            Success message

        Raises:
            HTTPException 400 if token is invalid or expired
        """
        db = get_db()
        metadata_loader = get_metadata_loader()

        if not db or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        # Validate reset token
        try:
            user_id = jwt_service.validate_reset_token(request.reset_token)
        except TokenExpiredError:
            raise HTTPException(400, "Reset token has expired. Please request a new one.")
        except InvalidTokenError as e:
            raise HTTPException(400, f"Invalid reset token: {e}")

        user_entity = metadata_loader.get_entity("User")
        if not user_entity:
            raise HTTPException(500, "User entity not configured")

        # Verify user exists
        user = db.get(user_entity, user_id)
        if not user:
            raise HTTPException(400, "User not found")

        # Update password
        new_hash = password_service.hash(request.new_password)
        db.update(user_entity, user_id, {"passwordHash": new_hash})

        return {"message": "Password has been reset successfully"}

    return router
