"""Authentication middleware for FastAPI."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from metaforge.auth.jwt_service import JWTService, JWTError
from metaforge.auth.types import TokenClaims
from metaforge.validation import UserContext


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that extracts JWT from Authorization header and sets user context.

    The middleware:
    1. Extracts Bearer token from Authorization header
    2. Decodes and validates the JWT
    3. Sets request.state.user_context with the claims
    4. Sets request.state.token_claims for additional info

    If no token is present or token is invalid, user_context is set to None.
    The middleware does NOT reject unauthenticated requests - that's handled
    by the endpoint dependencies.
    """

    def __init__(self, app, jwt_service: JWTService):
        """Initialize middleware with JWT service.

        Args:
            app: The ASGI application
            jwt_service: JWT service for token validation
        """
        super().__init__(app)
        self._jwt_service = jwt_service

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request and extract authentication info."""
        # Initialize to unauthenticated
        request.state.user_context = None
        request.state.token_claims = None

        # Skip auth for certain paths
        if self._should_skip_auth(request.url.path):
            return await call_next(request)

        # Try to extract and validate token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            try:
                claims = self._jwt_service.decode_token(token)

                # Only accept access tokens (not refresh tokens)
                if claims.type == "access":
                    request.state.token_claims = claims
                    request.state.user_context = UserContext(
                        user_id=claims.user_id,
                        tenant_id=claims.tenant_id,
                        roles=[claims.role] if claims.role else [],
                    )
            except JWTError:
                # Invalid token - leave user_context as None
                pass

        return await call_next(request)

    def _should_skip_auth(self, path: str) -> bool:
        """Check if a path should skip authentication processing.

        Auth endpoints handle their own token validation differently,
        so we skip the middleware for those paths.
        """
        skip_paths = [
            "/api/auth/login",
            "/api/auth/refresh",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]
        return any(path.startswith(p) for p in skip_paths)


def get_user_context(request: Request) -> UserContext | None:
    """Get the user context from the request state.

    Args:
        request: The FastAPI/Starlette request

    Returns:
        UserContext if authenticated, None otherwise
    """
    return getattr(request.state, "user_context", None)


def get_token_claims(request: Request) -> TokenClaims | None:
    """Get the token claims from the request state.

    Args:
        request: The FastAPI/Starlette request

    Returns:
        TokenClaims if authenticated, None otherwise
    """
    return getattr(request.state, "token_claims", None)
