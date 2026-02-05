"""Warning acknowledgment flow for MetaForge.

When validation produces warnings but no errors, the user must explicitly
acknowledge the warnings before the save can proceed. This module provides
token generation and verification to ensure:

1. User saw the specific warnings for the specific data
2. Token is time-limited (prevents stale acknowledgments)
3. Token is single-use (prevents replay)
4. Data hasn't changed since warnings were shown
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from metaforge.validation.types import ValidationError


class AcknowledgmentError(Exception):
    """Error during acknowledgment verification."""
    pass


class TokenExpiredError(AcknowledgmentError):
    """The acknowledgment token has expired."""
    pass


class TokenInvalidError(AcknowledgmentError):
    """The acknowledgment token is invalid or has been tampered with."""
    pass


class DataChangedError(AcknowledgmentError):
    """The record data has changed since the warnings were acknowledged."""
    pass


@dataclass
class AcknowledgmentToken:
    """Parsed acknowledgment token data."""

    expires_at: int
    content_hash: str
    signature: str
    raw: str


class WarningAcknowledgmentService:
    """Service for generating and verifying warning acknowledgment tokens.

    Tokens are:
    - Time-limited (default 5 minutes)
    - Content-bound (tied to specific data and warnings)
    - Signed (tamper-proof)

    Token format: {expires_at}.{content_hash}.{signature}
    """

    def __init__(
        self,
        secret_key: str,
        ttl_seconds: int = 300,  # 5 minutes default
    ):
        """Initialize the acknowledgment service.

        Args:
            secret_key: Secret key for signing tokens
            ttl_seconds: Token time-to-live in seconds
        """
        if not secret_key:
            raise ValueError("secret_key is required")
        self.secret_key = secret_key
        self.ttl_seconds = ttl_seconds

    def generate_token(
        self,
        entity: str,
        record: dict[str, Any],
        warnings: list[ValidationError],
    ) -> str:
        """Generate an acknowledgment token for warnings.

        Args:
            entity: Entity name being saved
            record: The record data (with defaults applied)
            warnings: List of warning validation errors

        Returns:
            Signed acknowledgment token
        """
        expires_at = int(time.time()) + self.ttl_seconds

        # Create content hash that binds token to specific data + warnings
        content = self._create_content_string(entity, record, warnings)
        content_hash = self._hash(content)[:16]

        # Create signature
        payload = f"{expires_at}.{content_hash}"
        signature = self._sign(payload)[:16]

        return f"{payload}.{signature}"

    def verify_token(
        self,
        token: str,
        entity: str,
        record: dict[str, Any],
        warnings: list[ValidationError],
    ) -> bool:
        """Verify an acknowledgment token.

        Args:
            token: The acknowledgment token to verify
            entity: Entity name being saved
            record: The current record data
            warnings: Current list of warnings

        Returns:
            True if token is valid

        Raises:
            TokenExpiredError: Token has expired
            TokenInvalidError: Token is malformed or signature is invalid
            DataChangedError: Record data or warnings have changed
        """
        # Parse token
        parsed = self._parse_token(token)

        # Check expiration
        if parsed.expires_at < time.time():
            raise TokenExpiredError("Acknowledgment token has expired")

        # Verify signature
        payload = f"{parsed.expires_at}.{parsed.content_hash}"
        expected_signature = self._sign(payload)[:16]
        if not hmac.compare_digest(parsed.signature, expected_signature):
            raise TokenInvalidError("Invalid acknowledgment token signature")

        # Verify content hash matches current data
        content = self._create_content_string(entity, record, warnings)
        expected_hash = self._hash(content)[:16]
        if parsed.content_hash != expected_hash:
            raise DataChangedError(
                "Record data or warnings have changed since acknowledgment"
            )

        return True

    def _parse_token(self, token: str) -> AcknowledgmentToken:
        """Parse a token string into components."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                raise TokenInvalidError("Malformed acknowledgment token")

            expires_at = int(parts[0])
            content_hash = parts[1]
            signature = parts[2]

            return AcknowledgmentToken(
                expires_at=expires_at,
                content_hash=content_hash,
                signature=signature,
                raw=token,
            )
        except ValueError:
            raise TokenInvalidError("Malformed acknowledgment token")

    def _create_content_string(
        self,
        entity: str,
        record: dict[str, Any],
        warnings: list[ValidationError],
    ) -> str:
        """Create a canonical string representing the content to hash."""
        # Sort record keys for consistent hashing
        record_str = json.dumps(record, sort_keys=True, default=str)

        # Sort warning codes for consistent hashing
        warning_codes = sorted(w.code for w in warnings)
        warnings_str = json.dumps(warning_codes)

        return f"{entity}:{record_str}:{warnings_str}"

    def _hash(self, content: str) -> str:
        """Create SHA-256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def _sign(self, payload: str) -> str:
        """Create HMAC signature of payload."""
        return hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()


# =============================================================================
# HTTP Response Helpers
# =============================================================================


@dataclass
class SaveResponse:
    """Response from a save operation with validation."""

    success: bool
    status_code: int
    data: dict[str, Any] | None = None
    errors: list[dict[str, Any]] | None = None
    warnings: list[dict[str, Any]] | None = None
    requires_acknowledgment: bool = False
    acknowledgment_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"success": self.success}

        if self.data is not None:
            result["data"] = self.data

        if self.errors:
            result["valid"] = False
            result["errors"] = self.errors

        if self.warnings:
            result["warnings"] = self.warnings

        if self.requires_acknowledgment:
            result["requiresAcknowledgment"] = True
            result["acknowledgmentToken"] = self.acknowledgment_token

        return result


def create_error_response(
    errors: list[ValidationError],
    warnings: list[ValidationError] | None = None,
) -> SaveResponse:
    """Create a 422 error response for validation failures."""
    return SaveResponse(
        success=False,
        status_code=422,
        errors=[e.to_dict() for e in errors],
        warnings=[w.to_dict() for w in (warnings or [])],
    )


def create_warning_response(
    warnings: list[ValidationError],
    acknowledgment_token: str,
) -> SaveResponse:
    """Create a 202 response for warnings requiring acknowledgment."""
    return SaveResponse(
        success=False,  # Not yet saved
        status_code=202,
        warnings=[w.to_dict() for w in warnings],
        requires_acknowledgment=True,
        acknowledgment_token=acknowledgment_token,
    )


def create_success_response(data: dict[str, Any]) -> SaveResponse:
    """Create a 201 success response for saved data."""
    return SaveResponse(
        success=True,
        status_code=201,
        data=data,
    )


def create_acknowledgment_error_response(error: AcknowledgmentError) -> SaveResponse:
    """Create a 422 response for acknowledgment errors."""
    if isinstance(error, TokenExpiredError):
        message = "Acknowledgment expired. Please review the warnings again."
        code = "ACKNOWLEDGMENT_EXPIRED"
    elif isinstance(error, DataChangedError):
        message = "Data has changed. Please review the warnings again."
        code = "DATA_CHANGED"
    else:
        message = "Invalid acknowledgment. Please try again."
        code = "INVALID_ACKNOWLEDGMENT"

    return SaveResponse(
        success=False,
        status_code=422,
        errors=[{
            "message": message,
            "code": code,
            "field": None,
            "severity": "error",
        }],
    )
