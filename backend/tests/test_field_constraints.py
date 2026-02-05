"""Tests for field constraint validators (Layer 0)."""

import pytest

from metaforge.metadata.loader import FieldDefinition, ValidationRules
from metaforge.validation.types import Operation, ValidationContext
from metaforge.validation.validators.field_constraints import (
    EMAIL_PATTERN,
    PHONE_PATTERN,
    URL_PATTERN,
    UUID_PATTERN,
    FieldConstraintValidator,
    generate_field_validators,
)


# =============================================================================
# Mock QueryService
# =============================================================================


class MockQueryService:
    """Mock query service for testing."""

    async def query(self, entity, filter, tenant_id=None):
        return []

    async def exists(self, entity, filter, tenant_id=None):
        return False

    async def count(self, entity, filter, tenant_id=None):
        return 0


@pytest.fixture
def query_service():
    return MockQueryService()


def make_field(
    name: str = "testField",
    field_type: str = "text",
    display_name: str = "Test Field",
    required: bool = False,
    min_val: float | None = None,
    max_val: float | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    pattern: str | None = None,
    options: list | None = None,
) -> FieldDefinition:
    """Helper to create a FieldDefinition for testing."""
    return FieldDefinition(
        name=name,
        type=field_type,
        display_name=display_name,
        validation=ValidationRules(
            required=required,
            min=min_val,
            max=max_val,
            min_length=min_length,
            max_length=max_length,
            pattern=pattern,
        ),
        options=options,
    )


def make_ctx(record: dict, operation: Operation = Operation.CREATE) -> ValidationContext:
    """Helper to create a ValidationContext for testing."""
    return ValidationContext(
        entity_name="TestEntity",
        record=record,
        operation=operation,
        user_context=None,
        original_record=None,
    )


# =============================================================================
# Pattern Tests
# =============================================================================


class TestPatterns:
    """Test the regex patterns used for type validation."""

    def test_email_valid(self):
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@example.org",
            "user123@test.io",
        ]
        for email in valid_emails:
            assert EMAIL_PATTERN.match(email), f"{email} should be valid"

    def test_email_invalid(self):
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user@.com",
            "user name@example.com",
        ]
        for email in invalid_emails:
            assert not EMAIL_PATTERN.match(email), f"{email} should be invalid"

    def test_phone_valid(self):
        valid_phones = [
            "123-456-7890",
            "(123) 456-7890",
            "+1 123 456 7890",
            "1234567890",
            "+44 20 7946 0958",
        ]
        for phone in valid_phones:
            assert PHONE_PATTERN.match(phone), f"{phone} should be valid"

    def test_url_valid(self):
        valid_urls = [
            "https://example.com",
            "http://test.org/path",
            "https://sub.domain.com/path?query=1",
            "http://localhost:8080",
        ]
        for url in valid_urls:
            assert URL_PATTERN.match(url), f"{url} should be valid"

    def test_url_invalid(self):
        invalid_urls = [
            "not-a-url",
            "ftp://example.com",
            "//missing-protocol.com",
            "example.com",
        ]
        for url in invalid_urls:
            assert not URL_PATTERN.match(url), f"{url} should be invalid"

    def test_uuid_valid(self):
        valid_uuids = [
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            "F47AC10B-58CC-4372-A567-0E02B2C3D479",
        ]
        for uuid in valid_uuids:
            assert UUID_PATTERN.match(uuid), f"{uuid} should be valid"

    def test_uuid_invalid(self):
        invalid_uuids = [
            "not-a-uuid",
            "550e8400-e29b-41d4-a716",
            "550e8400e29b41d4a716446655440000",
        ]
        for uuid in invalid_uuids:
            assert not UUID_PATTERN.match(uuid), f"{uuid} should be invalid"


# =============================================================================
# Required Validation Tests
# =============================================================================


class TestRequiredValidation:
    """Test required field validation."""

    @pytest.mark.asyncio
    async def test_required_field_missing(self, query_service):
        field = make_field(required=True)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "REQUIRED"
        assert errors[0].field == "testField"

    @pytest.mark.asyncio
    async def test_required_field_null(self, query_service):
        field = make_field(required=True)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": None})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "REQUIRED"

    @pytest.mark.asyncio
    async def test_required_field_empty_string(self, query_service):
        field = make_field(required=True)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": ""})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "REQUIRED"

    @pytest.mark.asyncio
    async def test_required_field_whitespace(self, query_service):
        field = make_field(required=True)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "   "})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "REQUIRED"

    @pytest.mark.asyncio
    async def test_required_field_present(self, query_service):
        field = make_field(required=True)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "value"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_optional_field_missing(self, query_service):
        field = make_field(required=False)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0


# =============================================================================
# Type Format Validation Tests
# =============================================================================


class TestTypeFormatValidation:
    """Test type-specific format validation."""

    @pytest.mark.asyncio
    async def test_email_valid(self, query_service):
        field = make_field(field_type="email")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "test@example.com"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_email_invalid(self, query_service):
        field = make_field(field_type="email")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "not-an-email"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "INVALID_EMAIL"

    @pytest.mark.asyncio
    async def test_phone_valid(self, query_service):
        field = make_field(field_type="phone")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "123-456-7890"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_phone_invalid(self, query_service):
        field = make_field(field_type="phone")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "not-a-phone"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "INVALID_PHONE"

    @pytest.mark.asyncio
    async def test_url_valid(self, query_service):
        field = make_field(field_type="url")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "https://example.com"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_url_invalid(self, query_service):
        field = make_field(field_type="url")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "not-a-url"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "INVALID_URL"

    @pytest.mark.asyncio
    async def test_date_valid(self, query_service):
        field = make_field(field_type="date")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "2024-01-15"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_date_invalid(self, query_service):
        field = make_field(field_type="date")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "01/15/2024"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "INVALID_DATE"


# =============================================================================
# Numeric Bounds Validation Tests
# =============================================================================


class TestNumericBoundsValidation:
    """Test min/max numeric bounds validation."""

    @pytest.mark.asyncio
    async def test_min_value_valid(self, query_service):
        field = make_field(field_type="number", min_val=0)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": 5})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_min_value_invalid(self, query_service):
        field = make_field(field_type="number", min_val=0)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": -5})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "MIN_VALUE"

    @pytest.mark.asyncio
    async def test_max_value_valid(self, query_service):
        field = make_field(field_type="number", max_val=100)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": 50})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_max_value_invalid(self, query_service):
        field = make_field(field_type="number", max_val=100)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": 150})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "MAX_VALUE"

    @pytest.mark.asyncio
    async def test_bounds_both_valid(self, query_service):
        field = make_field(field_type="number", min_val=0, max_val=100)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": 50})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_bounds_both_invalid(self, query_service):
        field = make_field(field_type="number", min_val=10, max_val=100)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": 5})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "MIN_VALUE"


# =============================================================================
# String Length Validation Tests
# =============================================================================


class TestStringLengthValidation:
    """Test min/max string length validation."""

    @pytest.mark.asyncio
    async def test_min_length_valid(self, query_service):
        field = make_field(min_length=3)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "hello"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_min_length_invalid(self, query_service):
        field = make_field(min_length=3)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "hi"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "MIN_LENGTH"

    @pytest.mark.asyncio
    async def test_max_length_valid(self, query_service):
        field = make_field(max_length=10)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "hello"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_max_length_invalid(self, query_service):
        field = make_field(max_length=10)
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "this is too long"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "MAX_LENGTH"


# =============================================================================
# Pattern Validation Tests
# =============================================================================


class TestPatternValidation:
    """Test custom regex pattern validation."""

    @pytest.mark.asyncio
    async def test_pattern_valid(self, query_service):
        field = make_field(pattern=r"^[A-Z]{2}\d{4}$")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "AB1234"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_pattern_invalid(self, query_service):
        field = make_field(pattern=r"^[A-Z]{2}\d{4}$")
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "invalid"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "PATTERN_MISMATCH"


# =============================================================================
# Picklist Validation Tests
# =============================================================================


class TestPicklistValidation:
    """Test picklist option validation."""

    @pytest.mark.asyncio
    async def test_picklist_valid_option(self, query_service):
        field = make_field(
            field_type="picklist",
            options=[
                {"value": "opt1", "label": "Option 1"},
                {"value": "opt2", "label": "Option 2"},
            ],
        )
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "opt1"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_picklist_invalid_option(self, query_service):
        field = make_field(
            field_type="picklist",
            options=[
                {"value": "opt1", "label": "Option 1"},
                {"value": "opt2", "label": "Option 2"},
            ],
        )
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": "invalid"})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "INVALID_OPTION"

    @pytest.mark.asyncio
    async def test_multi_picklist_valid_options(self, query_service):
        field = make_field(
            field_type="multi_picklist",
            options=[
                {"value": "opt1", "label": "Option 1"},
                {"value": "opt2", "label": "Option 2"},
                {"value": "opt3", "label": "Option 3"},
            ],
        )
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": ["opt1", "opt3"]})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_multi_picklist_some_invalid(self, query_service):
        field = make_field(
            field_type="multi_picklist",
            options=[
                {"value": "opt1", "label": "Option 1"},
                {"value": "opt2", "label": "Option 2"},
            ],
        )
        validator = FieldConstraintValidator(field)

        ctx = make_ctx({"testField": ["opt1", "invalid"]})
        errors = await validator.validate(ctx, query_service)

        assert len(errors) == 1
        assert errors[0].code == "INVALID_OPTION"


# =============================================================================
# Generator Tests
# =============================================================================


class TestValidatorGenerator:
    """Test the field validator generator."""

    def test_generates_for_required_field(self):
        fields = [
            make_field(name="required_field", required=True),
            make_field(name="optional_field", required=False),
        ]

        validators = generate_field_validators(fields)

        # Should only generate validator for required field
        assert len(validators) == 1
        assert validators[0].field.name == "required_field"

    def test_generates_for_type_fields(self):
        fields = [
            make_field(name="email_field", field_type="email"),
            make_field(name="text_field", field_type="text"),  # No format check needed
            make_field(name="url_field", field_type="url"),
        ]

        validators = generate_field_validators(fields)

        # Should generate for email and url, not text
        assert len(validators) == 2
        names = {v.field.name for v in validators}
        assert names == {"email_field", "url_field"}

    def test_generates_for_bounds(self):
        fields = [
            make_field(name="bounded", field_type="number", min_val=0, max_val=100),
            make_field(name="unbounded", field_type="number"),
        ]

        validators = generate_field_validators(fields)

        # Should only generate for bounded field
        assert len(validators) == 1
        assert validators[0].field.name == "bounded"

    def test_generates_for_pattern(self):
        fields = [
            make_field(name="patterned", pattern=r"^\d{5}$"),
            make_field(name="no_pattern"),
        ]

        validators = generate_field_validators(fields)

        assert len(validators) == 1
        assert validators[0].field.name == "patterned"

    def test_generates_for_picklist(self):
        fields = [
            make_field(
                name="status",
                field_type="picklist",
                options=[{"value": "a"}, {"value": "b"}],
            ),
            make_field(name="text_field", field_type="text"),
        ]

        validators = generate_field_validators(fields)

        assert len(validators) == 1
        assert validators[0].field.name == "status"
