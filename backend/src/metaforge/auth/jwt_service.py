"""JWT token generation and validation service."""

import time
from typing import Any

import jwt

from metaforge.auth.types import TokenClaims, TokenPair


class JWTError(Exception):
    """Base exception for JWT-related errors."""

    pass


class TokenExpiredError(JWTError):
    """Raised when a token has expired."""

    pass


class InvalidTokenError(JWTError):
    """Raised when a token is invalid or malformed."""

    pass


class JWTService:
    """Service for generating and validating JWT tokens.

    Uses HS256 algorithm with a shared secret key.
    """

    # Token TTLs
    ACCESS_TOKEN_TTL = 15 * 60  # 15 minutes
    REFRESH_TOKEN_TTL = 7 * 24 * 60 * 60  # 7 days
    RESET_TOKEN_TTL = 60 * 60  # 1 hour

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initialize the JWT service.

        Args:
            secret_key: Secret key for signing tokens (should be at least 32 chars)
            algorithm: JWT algorithm (default HS256)
        """
        self._secret_key = secret_key
        self._algorithm = algorithm

    def generate_token_pair(
        self,
        user_id: str,
        tenant_id: str | None = None,
        role: str | None = None,
    ) -> TokenPair:
        """Generate a new access/refresh token pair.

        Args:
            user_id: The authenticated user's ID
            tenant_id: Optional tenant ID to include in token
            role: User's role in the tenant

        Returns:
            TokenPair with access and refresh tokens
        """
        now = int(time.time())

        # Access token
        access_claims = {
            "sub": user_id,
            "iat": now,
            "exp": now + self.ACCESS_TOKEN_TTL,
            "type": "access",
        }
        if tenant_id:
            access_claims["tenant_id"] = tenant_id
        if role:
            access_claims["role"] = role

        access_token = jwt.encode(
            access_claims,
            self._secret_key,
            algorithm=self._algorithm,
        )

        # Refresh token (doesn't include tenant/role, those are selected at refresh time)
        refresh_claims = {
            "sub": user_id,
            "iat": now,
            "exp": now + self.REFRESH_TOKEN_TTL,
            "type": "refresh",
        }
        refresh_token = jwt.encode(
            refresh_claims,
            self._secret_key,
            algorithm=self._algorithm,
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.ACCESS_TOKEN_TTL,
        )

    def decode_token(self, token: str) -> TokenClaims:
        """Decode and validate a JWT token.

        Args:
            token: The JWT token string

        Returns:
            TokenClaims with the decoded claims

        Raises:
            TokenExpiredError: If the token has expired
            InvalidTokenError: If the token is invalid or malformed
        """
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {e}")

        return TokenClaims(
            user_id=payload.get("sub", ""),
            tenant_id=payload.get("tenant_id"),
            role=payload.get("role"),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
            type=payload.get("type", "access"),
        )

    def validate_refresh_token(self, token: str) -> str:
        """Validate a refresh token and return the user ID.

        Args:
            token: The refresh token string

        Returns:
            The user ID from the token

        Raises:
            TokenExpiredError: If the token has expired
            InvalidTokenError: If the token is invalid or not a refresh token
        """
        claims = self.decode_token(token)

        if claims.type != "refresh":
            raise InvalidTokenError("Not a refresh token")

        return claims.user_id

    def generate_reset_token(self, user_id: str) -> str:
        """Generate a password reset token.

        Args:
            user_id: The user's ID

        Returns:
            JWT token for password reset (valid for 1 hour)
        """
        now = int(time.time())

        claims = {
            "sub": user_id,
            "iat": now,
            "exp": now + self.RESET_TOKEN_TTL,
            "type": "reset",
        }

        return jwt.encode(
            claims,
            self._secret_key,
            algorithm=self._algorithm,
        )

    def validate_reset_token(self, token: str) -> str:
        """Validate a password reset token and return the user ID.

        Args:
            token: The reset token string

        Returns:
            The user ID from the token

        Raises:
            TokenExpiredError: If the token has expired
            InvalidTokenError: If the token is invalid or not a reset token
        """
        claims = self.decode_token(token)

        if claims.type != "reset":
            raise InvalidTokenError("Not a password reset token")

        return claims.user_id
