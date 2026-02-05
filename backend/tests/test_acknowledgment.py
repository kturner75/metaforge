"""Tests for warning acknowledgment flow."""

import pytest
import time
from unittest.mock import patch

from metaforge.validation.types import Severity, ValidationError
from metaforge.validation.acknowledgment import (
    AcknowledgmentError,
    DataChangedError,
    SaveResponse,
    TokenExpiredError,
    TokenInvalidError,
    WarningAcknowledgmentService,
    create_error_response,
    create_success_response,
    create_warning_response,
    create_acknowledgment_error_response,
)


@pytest.fixture
def service():
    """Create acknowledgment service with test secret."""
    return WarningAcknowledgmentService(
        secret_key="test-secret-key-for-testing",
        ttl_seconds=300,
    )


@pytest.fixture
def sample_warnings():
    """Sample warning errors."""
    return [
        ValidationError(
            message="Discount exceeds recommended maximum",
            code="HIGH_DISCOUNT",
            field="discountPercent",
            severity=Severity.WARNING,
        ),
        ValidationError(
            message="Unusual order quantity",
            code="HIGH_QUANTITY",
            field="quantity",
            severity=Severity.WARNING,
        ),
    ]


# =============================================================================
# Token Generation Tests
# =============================================================================


class TestTokenGeneration:
    """Tests for token generation."""

    def test_generates_token(self, service, sample_warnings):
        token = service.generate_token(
            entity="Order",
            record={"id": "123", "discountPercent": 50, "quantity": 1000},
            warnings=sample_warnings,
        )

        assert token is not None
        assert len(token.split(".")) == 3

    def test_same_inputs_generate_same_token(self, service, sample_warnings):
        record = {"id": "123", "discountPercent": 50}

        token1 = service.generate_token("Order", record, sample_warnings)
        token2 = service.generate_token("Order", record, sample_warnings)

        # Same content hash (first two parts), different only if time changes
        parts1 = token1.split(".")
        parts2 = token2.split(".")
        assert parts1[1] == parts2[1]  # Content hash should match

    def test_different_data_generates_different_token(self, service, sample_warnings):
        token1 = service.generate_token(
            "Order",
            {"id": "123", "discountPercent": 50},
            sample_warnings,
        )
        token2 = service.generate_token(
            "Order",
            {"id": "123", "discountPercent": 60},  # Different discount
            sample_warnings,
        )

        parts1 = token1.split(".")
        parts2 = token2.split(".")
        assert parts1[1] != parts2[1]  # Content hash should differ

    def test_different_warnings_generates_different_token(self, service):
        record = {"id": "123"}

        token1 = service.generate_token(
            "Order",
            record,
            [ValidationError("Warning 1", "CODE_1", severity=Severity.WARNING)],
        )
        token2 = service.generate_token(
            "Order",
            record,
            [ValidationError("Warning 2", "CODE_2", severity=Severity.WARNING)],
        )

        parts1 = token1.split(".")
        parts2 = token2.split(".")
        assert parts1[1] != parts2[1]


# =============================================================================
# Token Verification Tests
# =============================================================================


class TestTokenVerification:
    """Tests for token verification."""

    def test_valid_token_verifies(self, service, sample_warnings):
        record = {"id": "123", "discountPercent": 50}
        token = service.generate_token("Order", record, sample_warnings)

        result = service.verify_token(token, "Order", record, sample_warnings)

        assert result is True

    def test_expired_token_raises_error(self, service, sample_warnings):
        record = {"id": "123"}

        # Create service with very short TTL
        short_ttl_service = WarningAcknowledgmentService(
            secret_key="test-secret",
            ttl_seconds=1,
        )
        token = short_ttl_service.generate_token("Order", record, sample_warnings)

        # Wait for expiration
        time.sleep(1.5)

        with pytest.raises(TokenExpiredError):
            short_ttl_service.verify_token(token, "Order", record, sample_warnings)

    def test_tampered_token_raises_error(self, service, sample_warnings):
        record = {"id": "123"}
        token = service.generate_token("Order", record, sample_warnings)

        # Tamper with the token
        parts = token.split(".")
        parts[2] = "tampered_signature"
        tampered_token = ".".join(parts)

        with pytest.raises(TokenInvalidError):
            service.verify_token(tampered_token, "Order", record, sample_warnings)

    def test_malformed_token_raises_error(self, service, sample_warnings):
        with pytest.raises(TokenInvalidError):
            service.verify_token("not.a.valid.token.format", "Order", {}, [])

        with pytest.raises(TokenInvalidError):
            service.verify_token("invalid", "Order", {}, [])

    def test_changed_data_raises_error(self, service, sample_warnings):
        original_record = {"id": "123", "discountPercent": 50}
        token = service.generate_token("Order", original_record, sample_warnings)

        # Try to verify with different data
        changed_record = {"id": "123", "discountPercent": 60}

        with pytest.raises(DataChangedError):
            service.verify_token(token, "Order", changed_record, sample_warnings)

    def test_changed_warnings_raises_error(self, service):
        record = {"id": "123"}
        original_warnings = [
            ValidationError("Warning 1", "CODE_1", severity=Severity.WARNING)
        ]
        token = service.generate_token("Order", record, original_warnings)

        # Try to verify with different warnings
        new_warnings = [
            ValidationError("Warning 2", "CODE_2", severity=Severity.WARNING)
        ]

        with pytest.raises(DataChangedError):
            service.verify_token(token, "Order", record, new_warnings)

    def test_different_entity_raises_error(self, service, sample_warnings):
        record = {"id": "123"}
        token = service.generate_token("Order", record, sample_warnings)

        with pytest.raises(DataChangedError):
            service.verify_token(token, "Invoice", record, sample_warnings)


# =============================================================================
# Service Configuration Tests
# =============================================================================


class TestServiceConfiguration:
    """Tests for service configuration."""

    def test_requires_secret_key(self):
        with pytest.raises(ValueError):
            WarningAcknowledgmentService(secret_key="")

        with pytest.raises(ValueError):
            WarningAcknowledgmentService(secret_key=None)

    def test_custom_ttl(self, sample_warnings):
        service = WarningAcknowledgmentService(
            secret_key="test",
            ttl_seconds=60,
        )

        token = service.generate_token("Order", {}, sample_warnings)
        parts = token.split(".")
        expires_at = int(parts[0])

        # Should expire in approximately 60 seconds
        expected_expiry = int(time.time()) + 60
        assert abs(expires_at - expected_expiry) <= 1


# =============================================================================
# Response Helper Tests
# =============================================================================


class TestResponseHelpers:
    """Tests for HTTP response helpers."""

    def test_error_response(self):
        errors = [
            ValidationError("Error 1", "ERR_1", "field1", Severity.ERROR),
            ValidationError("Error 2", "ERR_2", "field2", Severity.ERROR),
        ]
        warnings = [
            ValidationError("Warning 1", "WARN_1", "field3", Severity.WARNING),
        ]

        response = create_error_response(errors, warnings)

        assert response.success is False
        assert response.status_code == 422
        assert len(response.errors) == 2
        assert len(response.warnings) == 1

    def test_warning_response(self):
        warnings = [
            ValidationError("Warning 1", "WARN_1", severity=Severity.WARNING),
        ]

        response = create_warning_response(warnings, "token-123")

        assert response.success is False
        assert response.status_code == 202
        assert response.requires_acknowledgment is True
        assert response.acknowledgment_token == "token-123"
        assert len(response.warnings) == 1

    def test_success_response(self):
        data = {"id": "123", "name": "Test"}

        response = create_success_response(data)

        assert response.success is True
        assert response.status_code == 201
        assert response.data == data

    def test_acknowledgment_error_responses(self):
        expired_response = create_acknowledgment_error_response(
            TokenExpiredError("Token expired")
        )
        assert expired_response.status_code == 422
        assert "expired" in expired_response.errors[0]["message"].lower()
        assert expired_response.errors[0]["code"] == "ACKNOWLEDGMENT_EXPIRED"

        changed_response = create_acknowledgment_error_response(
            DataChangedError("Data changed")
        )
        assert "changed" in changed_response.errors[0]["message"].lower()
        assert changed_response.errors[0]["code"] == "DATA_CHANGED"

        invalid_response = create_acknowledgment_error_response(
            TokenInvalidError("Invalid token")
        )
        assert invalid_response.errors[0]["code"] == "INVALID_ACKNOWLEDGMENT"

    def test_response_to_dict(self):
        response = SaveResponse(
            success=False,
            status_code=202,
            warnings=[{"message": "Test", "code": "TEST"}],
            requires_acknowledgment=True,
            acknowledgment_token="abc123",
        )

        result = response.to_dict()

        assert result["success"] is False
        assert result["requiresAcknowledgment"] is True
        assert result["acknowledgmentToken"] == "abc123"
        assert len(result["warnings"]) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestAcknowledgmentIntegration:
    """Integration tests for the full acknowledgment flow."""

    def test_full_acknowledgment_flow(self, service, sample_warnings):
        """Test the complete flow: generate token, verify, succeed."""
        entity = "Order"
        record = {
            "id": "order-123",
            "customerId": "cust-456",
            "discountPercent": 50,
            "quantity": 1000,
        }

        # Step 1: Generate token when warnings are found
        token = service.generate_token(entity, record, sample_warnings)
        assert token is not None

        # Step 2: Client would show warnings to user, user confirms

        # Step 3: Verify token on re-submission
        is_valid = service.verify_token(token, entity, record, sample_warnings)
        assert is_valid is True

        # Step 4: Proceed with save (not shown here)

    def test_resubmit_with_modified_data_fails(self, service, sample_warnings):
        """Test that modifying data after acknowledgment fails."""
        entity = "Order"
        original_record = {
            "id": "order-123",
            "discountPercent": 50,
        }

        # Generate token for original data
        token = service.generate_token(entity, original_record, sample_warnings)

        # User modifies data (perhaps trying to sneak in a higher discount)
        modified_record = {
            "id": "order-123",
            "discountPercent": 75,  # Changed!
        }

        # Verification should fail
        with pytest.raises(DataChangedError):
            service.verify_token(token, entity, modified_record, sample_warnings)

    def test_resubmit_after_new_warnings_fails(self, service):
        """Test that new warnings after acknowledgment fails."""
        entity = "Order"
        record = {"id": "order-123", "discountPercent": 50}
        original_warnings = [
            ValidationError("Original warning", "ORIG", severity=Severity.WARNING)
        ]

        # Generate token for original warnings
        token = service.generate_token(entity, record, original_warnings)

        # Re-validation produces different warnings
        new_warnings = [
            ValidationError("Original warning", "ORIG", severity=Severity.WARNING),
            ValidationError("New warning", "NEW", severity=Severity.WARNING),
        ]

        # Verification should fail because warnings changed
        with pytest.raises(DataChangedError):
            service.verify_token(token, entity, record, new_warnings)
