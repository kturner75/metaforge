"""Tests for validation and defaulting services."""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from metaforge.validation.types import (
    Operation,
    Severity,
    UserContext,
    ValidationContext,
    ValidationError,
    ValidationResult,
    ValidatorDefinition,
)
from metaforge.validation.services import (
    DefaultDefinition,
    DefaultingService,
    DefaultPolicy,
    EntityLifecycle,
    MessageInterpolator,
    ValidationService,
)
from metaforge.validation.registry import ValidatorRegistry
from metaforge.validation.validators.canned import register_canned_validators
from metaforge.validation.expressions.builtins import register_all_builtins
from metaforge.validation.expressions import FunctionRegistry


@pytest.fixture(autouse=True)
def setup_registries():
    """Register validators and functions before each test."""
    ValidatorRegistry.clear()
    FunctionRegistry.clear()
    register_canned_validators()
    register_all_builtins()
    yield
    ValidatorRegistry.clear()
    FunctionRegistry.clear()


@pytest.fixture
def mock_query():
    """Create a mock QueryService."""
    query = AsyncMock()
    query.exists = AsyncMock(return_value=False)
    query.count = AsyncMock(return_value=0)
    query.query = AsyncMock(return_value=[])
    return query


# =============================================================================
# Defaulting Service Tests
# =============================================================================


class TestDefaultingService:
    """Tests for the DefaultingService."""

    def test_static_default_when_null(self):
        service = DefaultingService()
        defaults = [
            DefaultDefinition(field="status", value="draft"),
        ]

        result = service.apply_defaults(
            {"name": "Test"},
            defaults,
            Operation.CREATE,
        )

        assert result["status"] == "draft"

    def test_static_default_not_applied_when_value_exists(self):
        service = DefaultingService()
        defaults = [
            DefaultDefinition(field="status", value="draft"),
        ]

        result = service.apply_defaults(
            {"name": "Test", "status": "active"},
            defaults,
            Operation.CREATE,
        )

        assert result["status"] == "active"

    def test_overwrite_policy_replaces_value(self):
        service = DefaultingService()
        defaults = [
            DefaultDefinition(
                field="status",
                value="updated",
                policy=DefaultPolicy.OVERWRITE,
            ),
        ]

        result = service.apply_defaults(
            {"status": "original"},
            defaults,
            Operation.UPDATE,
        )

        assert result["status"] == "updated"

    def test_expression_default(self):
        service = DefaultingService()
        defaults = [
            DefaultDefinition(
                field="fullName",
                expression='concat(firstName, " ", lastName)',
                policy=DefaultPolicy.OVERWRITE,
            ),
        ]

        result = service.apply_defaults(
            {"firstName": "John", "lastName": "Doe"},
            defaults,
            Operation.CREATE,
        )

        assert result["fullName"] == "John Doe"

    def test_conditional_default(self):
        service = DefaultingService()
        defaults = [
            DefaultDefinition(
                field="priority",
                value="high",
                when='customerTier == "enterprise"',
            ),
        ]

        # Condition met
        result1 = service.apply_defaults(
            {"customerTier": "enterprise"},
            defaults,
            Operation.CREATE,
        )
        assert result1["priority"] == "high"

        # Condition not met
        result2 = service.apply_defaults(
            {"customerTier": "standard"},
            defaults,
            Operation.CREATE,
        )
        assert "priority" not in result2 or result2.get("priority") is None

    def test_defaults_applied_in_order(self):
        """Test that defaults are applied sequentially and can compound."""
        service = DefaultingService()
        defaults = [
            DefaultDefinition(
                field="regionCode",
                value="US",
            ),
            DefaultDefinition(
                field="locationCode",
                expression='concat(regionCode, "-", "001")',
                policy=DefaultPolicy.OVERWRITE,
            ),
        ]

        result = service.apply_defaults({}, defaults, Operation.CREATE)

        assert result["regionCode"] == "US"
        assert result["locationCode"] == "US-001"

    def test_operation_filtering(self):
        service = DefaultingService()
        defaults = [
            DefaultDefinition(
                field="status",
                value="draft",
                on=[Operation.CREATE],
            ),
        ]

        # Applied on create
        result1 = service.apply_defaults({}, defaults, Operation.CREATE)
        assert result1["status"] == "draft"

        # Not applied on update
        result2 = service.apply_defaults({}, defaults, Operation.UPDATE)
        assert "status" not in result2

    def test_auto_fields_created_at(self):
        service = DefaultingService()
        auto_fields = {"createdAt": "now", "updatedAt": "now"}

        result = service.apply_auto_fields(
            {"name": "Test"},
            Operation.CREATE,
            auto_fields,
        )

        assert "createdAt" in result
        assert "updatedAt" in result
        # Auto fields return ISO strings for JSON serialization
        assert isinstance(result["createdAt"], str)
        assert "T" in result["createdAt"]  # ISO format

    def test_auto_fields_created_at_not_updated(self):
        service = DefaultingService()
        auto_fields = {"createdAt": "now", "updatedAt": "now"}
        original_time = "2024-01-01T00:00:00+00:00"

        result = service.apply_auto_fields(
            {"name": "Test", "createdAt": original_time},
            Operation.UPDATE,
            auto_fields,
        )

        # createdAt should not be updated on UPDATE (already has value)
        assert result["createdAt"] == original_time
        # updatedAt should be set (was not already set)
        assert "updatedAt" in result

    def test_auto_fields_user_context(self):
        service = DefaultingService(
            user_context=UserContext(
                user_id="user-123",
                tenant_id="tenant-456",
            )
        )
        auto_fields = {
            "createdBy": "context.userId",
            "tenantId": "context.tenantId",
        }

        result = service.apply_auto_fields({}, Operation.CREATE, auto_fields)

        assert result["createdBy"] == "user-123"
        assert result["tenantId"] == "tenant-456"


# =============================================================================
# Validation Service Tests
# =============================================================================


class TestValidationService:
    """Tests for the ValidationService."""

    @pytest.mark.asyncio
    async def test_validates_with_no_validators(self, mock_query):
        service = ValidationService(mock_query)
        ctx = ValidationContext(
            entity_name="Test",
            record={"name": "Test"},
            operation=Operation.CREATE,
        )

        result = await service.validate(ctx, [])

        assert result.valid is True
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_collects_all_errors(self, mock_query):
        service = ValidationService(mock_query)
        validators = [
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "false"},
                "message": "Error 1",
                "code": "ERROR_1",
            }),
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "false"},
                "message": "Error 2",
                "code": "ERROR_2",
            }),
        ]

        ctx = ValidationContext(
            entity_name="Test",
            record={},
            operation=Operation.CREATE,
        )

        result = await service.validate(ctx, validators)

        assert result.valid is False
        assert len(result.errors) == 2
        codes = {e.code for e in result.errors}
        assert "ERROR_1" in codes
        assert "ERROR_2" in codes

    @pytest.mark.asyncio
    async def test_separates_errors_and_warnings(self, mock_query):
        service = ValidationService(mock_query)
        validators = [
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "false"},
                "message": "This is an error",
                "code": "ERROR",
                "severity": "error",
            }),
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "false"},
                "message": "This is a warning",
                "code": "WARNING",
                "severity": "warning",
            }),
        ]

        ctx = ValidationContext(
            entity_name="Test",
            record={},
            operation=Operation.CREATE,
        )

        result = await service.validate(ctx, validators)

        assert result.valid is False  # Has errors
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.errors[0].code == "ERROR"
        assert result.warnings[0].code == "WARNING"

    @pytest.mark.asyncio
    async def test_warnings_only_is_valid(self, mock_query):
        service = ValidationService(mock_query)
        validators = [
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "false"},
                "message": "This is a warning",
                "code": "WARNING",
                "severity": "warning",
            }),
        ]

        ctx = ValidationContext(
            entity_name="Test",
            record={},
            operation=Operation.CREATE,
        )

        result = await service.validate(ctx, validators)

        assert result.valid is True  # No errors, only warnings
        assert len(result.warnings) == 1

    @pytest.mark.asyncio
    async def test_filters_by_operation(self, mock_query):
        service = ValidationService(mock_query)
        validators = [
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "false"},
                "message": "Create only",
                "code": "CREATE_ONLY",
                "on": ["create"],
            }),
        ]

        # Should run on create
        ctx_create = ValidationContext(
            entity_name="Test",
            record={},
            operation=Operation.CREATE,
        )
        result_create = await service.validate(ctx_create, validators)
        assert len(result_create.errors) == 1

        # Should not run on update
        ctx_update = ValidationContext(
            entity_name="Test",
            record={},
            operation=Operation.UPDATE,
        )
        result_update = await service.validate(ctx_update, validators)
        assert len(result_update.errors) == 0


# =============================================================================
# Message Interpolator Tests
# =============================================================================


class TestMessageInterpolator:
    """Tests for the MessageInterpolator."""

    def test_interpolate_field_value(self):
        interpolator = MessageInterpolator()
        record = {"name": "John", "count": 5}

        result = interpolator.interpolate(
            "Name is {name}, count is {count}",
            record,
        )

        assert result == "Name is John, count is 5"

    def test_interpolate_original_value(self):
        interpolator = MessageInterpolator()
        record = {"status": "inactive"}
        original = {"status": "active"}

        result = interpolator.interpolate(
            "Changed from {original.status} to {status}",
            record,
            original,
        )

        assert result == "Changed from active to inactive"

    def test_interpolate_field_label(self):
        interpolator = MessageInterpolator(
            field_labels={"firstName": "First Name"}
        )
        record = {"firstName": "John"}

        result = interpolator.interpolate(
            "{firstName:label} is required",
            record,
        )

        assert result == "First Name is required"

    def test_interpolate_raw_value(self):
        interpolator = MessageInterpolator(
            field_options={"status": [{"value": "active", "label": "Active"}]}
        )
        record = {"status": "active"}

        # Formatted value shows label
        result1 = interpolator.interpolate("{status}", record)
        assert result1 == "Active"

        # Raw value shows stored value
        result2 = interpolator.interpolate("{status:raw}", record)
        assert result2 == "active"

    def test_interpolate_picklist_label(self):
        interpolator = MessageInterpolator(
            field_options={
                "status": [
                    {"value": "active", "label": "Active"},
                    {"value": "inactive", "label": "Inactive"},
                ]
            }
        )
        record = {"status": "active"}

        result = interpolator.interpolate(
            "Status is {status}",
            record,
        )

        assert result == "Status is Active"

    def test_interpolate_date_formatting(self):
        interpolator = MessageInterpolator()
        record = {"dueDate": date(2024, 12, 25)}

        result = interpolator.interpolate(
            "Due date is {dueDate}",
            record,
        )

        assert "December 25, 2024" in result

    def test_interpolate_missing_field(self):
        interpolator = MessageInterpolator()
        record = {}

        result = interpolator.interpolate(
            "Value is {missing}",
            record,
        )

        assert result == "Value is "

    def test_camel_case_to_title_case(self):
        interpolator = MessageInterpolator()
        record = {"firstName": "John"}

        result = interpolator.interpolate(
            "{firstName:label}",
            record,
        )

        assert result == "First Name"


# =============================================================================
# Entity Lifecycle Tests
# =============================================================================


class TestEntityLifecycle:
    """Tests for the EntityLifecycle coordinator."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, mock_query):
        defaulting = DefaultingService()
        validation = ValidationService(mock_query)
        interpolator = MessageInterpolator(
            field_labels={"status": "Status"}
        )
        lifecycle = EntityLifecycle(defaulting, validation, interpolator)

        defaults = [
            DefaultDefinition(field="status", value="draft"),
        ]
        auto_fields = {"createdAt": "now"}
        validators = [
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "len(name) > 0"},
                "message": "Name is required",
                "code": "NAME_REQUIRED",
            }),
        ]

        result = await lifecycle.prepare(
            record={"name": "Test"},
            operation=Operation.CREATE,
            entity_name="Contract",
            defaults=defaults,
            auto_fields=auto_fields,
            validators=validators,
        )

        # Defaults applied
        assert result.record["status"] == "draft"
        assert "createdAt" in result.record

        # Validation passed
        assert result.validation.valid is True

    @pytest.mark.asyncio
    async def test_lifecycle_with_validation_errors(self, mock_query):
        defaulting = DefaultingService()
        validation = ValidationService(mock_query)
        lifecycle = EntityLifecycle(defaulting, validation)

        validators = [
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "false"},
                "message": "Always fails",
                "code": "ALWAYS_FAILS",
            }),
        ]

        result = await lifecycle.prepare(
            record={},
            operation=Operation.CREATE,
            entity_name="Test",
            defaults=[],
            auto_fields={},
            validators=validators,
        )

        assert result.validation.valid is False
        assert len(result.validation.errors) == 1

    @pytest.mark.asyncio
    async def test_lifecycle_interpolates_messages(self, mock_query):
        defaulting = DefaultingService()
        validation = ValidationService(mock_query)
        interpolator = MessageInterpolator(
            field_labels={"discountPercent": "Discount"}
        )
        lifecycle = EntityLifecycle(defaulting, validation, interpolator)

        validators = [
            ValidatorDefinition.from_dict({
                "type": "expression",
                "params": {"rule": "discountPercent <= 50"},
                "message": "{discountPercent:label} of {discountPercent}% exceeds maximum",
                "code": "DISCOUNT_TOO_HIGH",
            }),
        ]

        result = await lifecycle.prepare(
            record={"discountPercent": 75},
            operation=Operation.CREATE,
            entity_name="Order",
            defaults=[],
            auto_fields={},
            validators=validators,
        )

        assert "Discount of 75% exceeds maximum" in result.validation.errors[0].message
