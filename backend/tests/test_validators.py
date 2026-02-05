"""Tests for canned validators.

Tests cover all validators:
- dateRange
- unique
- expression
- fieldComparison
- conditionalRequired
- immutable
- referenceExists
- noActiveChildren
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from metaforge.validation.types import (
    Operation,
    Severity,
    UserContext,
    ValidationContext,
    ValidatorDefinition,
)
from metaforge.validation.registry import ValidatorRegistry
from metaforge.validation.validators.canned import (
    register_canned_validators,
    DateRangeValidator,
    DateRangeParams,
    UniqueValidator,
    UniqueParams,
    ExpressionValidator,
    FieldComparisonValidator,
    ConditionalRequiredValidator,
    ImmutableValidator,
    NoActiveChildrenValidator,
)
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


def make_context(
    record: dict,
    operation: Operation = Operation.CREATE,
    original: dict | None = None,
    entity_name: str = "TestEntity",
    tenant_id: str | None = "tenant-1",
) -> ValidationContext:
    """Helper to create validation context."""
    user_context = UserContext(tenant_id=tenant_id) if tenant_id else None
    return ValidationContext(
        entity_name=entity_name,
        record=record,
        operation=operation,
        original_record=original,
        user_context=user_context,
    )


# =============================================================================
# DateRange Validator Tests
# =============================================================================


class TestDateRangeValidator:
    """Tests for the dateRange validator."""

    @pytest.mark.asyncio
    async def test_valid_date_range(self, mock_query):
        validator = DateRangeValidator(
            params=DateRangeParams(
                start_field="startDate",
                end_field="endDate",
                allow_equal=False,
            ),
            message="End date must be after start date",
            code="INVALID_DATE_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({
            "startDate": date(2024, 1, 1),
            "endDate": date(2024, 12, 31),
        })

        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_invalid_date_range(self, mock_query):
        validator = DateRangeValidator(
            params=DateRangeParams(
                start_field="startDate",
                end_field="endDate",
                allow_equal=False,
            ),
            message="End date must be after start date",
            code="INVALID_DATE_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({
            "startDate": date(2024, 12, 31),
            "endDate": date(2024, 1, 1),
        })

        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].code == "INVALID_DATE_RANGE"
        assert errors[0].field == "endDate"

    @pytest.mark.asyncio
    async def test_equal_dates_not_allowed(self, mock_query):
        validator = DateRangeValidator(
            params=DateRangeParams(
                start_field="startDate",
                end_field="endDate",
                allow_equal=False,
            ),
            message="End date must be after start date",
            code="INVALID_DATE_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({
            "startDate": date(2024, 6, 15),
            "endDate": date(2024, 6, 15),
        })

        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_equal_dates_allowed(self, mock_query):
        validator = DateRangeValidator(
            params=DateRangeParams(
                start_field="startDate",
                end_field="endDate",
                allow_equal=True,
            ),
            message="End date must be after start date",
            code="INVALID_DATE_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({
            "startDate": date(2024, 6, 15),
            "endDate": date(2024, 6, 15),
        })

        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_null_dates_skipped(self, mock_query):
        validator = DateRangeValidator(
            params=DateRangeParams(
                start_field="startDate",
                end_field="endDate",
            ),
            message="End date must be after start date",
            code="INVALID_DATE_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({
            "startDate": date(2024, 1, 1),
            "endDate": None,
        })

        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_factory_creates_validator(self, mock_query):
        definition = ValidatorDefinition.from_dict({
            "type": "dateRange",
            "params": {
                "startField": "effectiveDate",
                "endField": "expirationDate",
                "allowEqual": True,
            },
            "message": "Expiration must be on or after effective date",
            "code": "INVALID_CONTRACT_DATES",
        })

        validator = ValidatorRegistry.create(definition)
        assert isinstance(validator, DateRangeValidator)


# =============================================================================
# Unique Validator Tests
# =============================================================================


class TestUniqueValidator:
    """Tests for the unique validator."""

    @pytest.mark.asyncio
    async def test_unique_value(self, mock_query):
        mock_query.exists.return_value = False

        validator = UniqueValidator(
            params=UniqueParams(fields=["email"], scope="tenant"),
            message="Email already exists",
            code="DUPLICATE_EMAIL",
            severity=Severity.ERROR,
        )

        ctx = make_context({"email": "test@example.com"})
        errors = await validator.validate(ctx, mock_query)
        assert errors == []
        mock_query.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_value(self, mock_query):
        mock_query.exists.return_value = True

        validator = UniqueValidator(
            params=UniqueParams(fields=["email"], scope="tenant"),
            message="Email already exists",
            code="DUPLICATE_EMAIL",
            severity=Severity.ERROR,
        )

        ctx = make_context({"email": "test@example.com"})
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].code == "DUPLICATE_EMAIL"

    @pytest.mark.asyncio
    async def test_null_value_skipped(self, mock_query):
        validator = UniqueValidator(
            params=UniqueParams(fields=["email"], scope="tenant"),
            message="Email already exists",
            code="DUPLICATE_EMAIL",
            severity=Severity.ERROR,
        )

        ctx = make_context({"email": None})
        errors = await validator.validate(ctx, mock_query)
        assert errors == []
        mock_query.exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_excludes_current_record(self, mock_query):
        mock_query.exists.return_value = False

        validator = UniqueValidator(
            params=UniqueParams(fields=["email"], scope="tenant"),
            message="Email already exists",
            code="DUPLICATE_EMAIL",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"id": "record-123", "email": "test@example.com"},
            operation=Operation.UPDATE,
        )
        errors = await validator.validate(ctx, mock_query)

        # Verify the query excludes the current record
        call_args = mock_query.exists.call_args
        filter_arg = call_args[0][1]  # Second positional argument
        assert any(
            c.get("field") == "id" and c.get("op") == "neq"
            for c in filter_arg.get("and", [])
        )


# =============================================================================
# Expression Validator Tests
# =============================================================================


class TestExpressionValidator:
    """Tests for the expression validator."""

    @pytest.mark.asyncio
    async def test_valid_expression(self, mock_query):
        validator = ExpressionValidator(
            rule='status == "active"',
            message="Status must be active",
            code="INVALID_STATUS",
            severity=Severity.ERROR,
        )

        ctx = make_context({"status": "active"})
        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_invalid_expression(self, mock_query):
        validator = ExpressionValidator(
            rule='status == "active"',
            message="Status must be active",
            code="INVALID_STATUS",
            severity=Severity.ERROR,
        )

        ctx = make_context({"status": "inactive"})
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_complex_expression(self, mock_query):
        validator = ExpressionValidator(
            rule='discountPercent <= 50 && (status == "draft" || !isEmpty(approvedBy))',
            message="Discount validation failed",
            code="DISCOUNT_ERROR",
            severity=Severity.ERROR,
        )

        ctx = make_context({
            "discountPercent": 25,
            "status": "approved",
            "approvedBy": "admin",
        })
        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_expression_with_original(self, mock_query):
        validator = ExpressionValidator(
            rule='status != "active" || original.status == "active"',
            message="Cannot change to active from non-active status",
            code="INVALID_TRANSITION",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"status": "active"},
            operation=Operation.UPDATE,
            original={"status": "draft"},
        )
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_expression_with_warning_severity(self, mock_query):
        validator = ExpressionValidator(
            rule="discountPercent <= 25",
            message="Discount exceeds recommended maximum",
            code="HIGH_DISCOUNT",
            severity=Severity.WARNING,
        )

        ctx = make_context({"discountPercent": 30})
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].severity == Severity.WARNING


# =============================================================================
# Field Comparison Validator Tests
# =============================================================================


class TestFieldComparisonValidator:
    """Tests for the fieldComparison validator."""

    @pytest.mark.asyncio
    async def test_lte_comparison_valid(self, mock_query):
        validator = FieldComparisonValidator(
            left="minQuantity",
            operator="lte",
            right="maxQuantity",
            message="Min must not exceed max",
            code="INVALID_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({"minQuantity": 5, "maxQuantity": 10})
        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_lte_comparison_invalid(self, mock_query):
        validator = FieldComparisonValidator(
            left="minQuantity",
            operator="lte",
            right="maxQuantity",
            message="Min must not exceed max",
            code="INVALID_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({"minQuantity": 15, "maxQuantity": 10})
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].code == "INVALID_RANGE"

    @pytest.mark.asyncio
    async def test_null_values_skipped(self, mock_query):
        validator = FieldComparisonValidator(
            left="minQuantity",
            operator="lte",
            right="maxQuantity",
            message="Min must not exceed max",
            code="INVALID_RANGE",
            severity=Severity.ERROR,
        )

        ctx = make_context({"minQuantity": 5, "maxQuantity": None})
        errors = await validator.validate(ctx, mock_query)
        assert errors == []


# =============================================================================
# Conditional Required Validator Tests
# =============================================================================


class TestConditionalRequiredValidator:
    """Tests for the conditionalRequired validator."""

    @pytest.mark.asyncio
    async def test_required_when_condition_met_and_missing(self, mock_query):
        validator = ConditionalRequiredValidator(
            field="approvedBy",
            when='status == "approved"',
            message="Approver required for approved status",
            code="APPROVER_REQUIRED",
            severity=Severity.ERROR,
        )

        ctx = make_context({"status": "approved", "approvedBy": None})
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].code == "APPROVER_REQUIRED"

    @pytest.mark.asyncio
    async def test_required_when_condition_met_and_present(self, mock_query):
        validator = ConditionalRequiredValidator(
            field="approvedBy",
            when='status == "approved"',
            message="Approver required for approved status",
            code="APPROVER_REQUIRED",
            severity=Severity.ERROR,
        )

        ctx = make_context({"status": "approved", "approvedBy": "admin"})
        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_not_required_when_condition_not_met(self, mock_query):
        validator = ConditionalRequiredValidator(
            field="approvedBy",
            when='status == "approved"',
            message="Approver required for approved status",
            code="APPROVER_REQUIRED",
            severity=Severity.ERROR,
        )

        ctx = make_context({"status": "draft", "approvedBy": None})
        errors = await validator.validate(ctx, mock_query)
        assert errors == []


# =============================================================================
# Immutable Validator Tests
# =============================================================================


class TestImmutableValidator:
    """Tests for the immutable validator."""

    @pytest.mark.asyncio
    async def test_immutable_field_changed(self, mock_query):
        validator = ImmutableValidator(
            fields=["contractNumber"],
            when=None,
            message="{field} cannot be changed",
            code="FIELD_IMMUTABLE",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"contractNumber": "CNT-002"},
            operation=Operation.UPDATE,
            original={"contractNumber": "CNT-001"},
        )
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].code == "FIELD_IMMUTABLE"
        assert errors[0].field == "contractNumber"

    @pytest.mark.asyncio
    async def test_immutable_field_unchanged(self, mock_query):
        validator = ImmutableValidator(
            fields=["contractNumber"],
            when=None,
            message="{field} cannot be changed",
            code="FIELD_IMMUTABLE",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"contractNumber": "CNT-001", "name": "Updated Name"},
            operation=Operation.UPDATE,
            original={"contractNumber": "CNT-001", "name": "Original Name"},
        )
        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_immutable_on_create_skipped(self, mock_query):
        validator = ImmutableValidator(
            fields=["contractNumber"],
            when=None,
            message="{field} cannot be changed",
            code="FIELD_IMMUTABLE",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"contractNumber": "CNT-001"},
            operation=Operation.CREATE,
        )
        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_immutable_with_condition(self, mock_query):
        validator = ImmutableValidator(
            fields=["contractNumber"],
            when='original.status == "finalized"',
            message="{field} cannot be changed after finalization",
            code="FIELD_IMMUTABLE",
            severity=Severity.ERROR,
        )

        # Original is finalized, should enforce immutability
        ctx = make_context(
            {"contractNumber": "CNT-002", "status": "finalized"},
            operation=Operation.UPDATE,
            original={"contractNumber": "CNT-001", "status": "finalized"},
        )
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1

        # Original is draft, should not enforce immutability
        ctx2 = make_context(
            {"contractNumber": "CNT-002", "status": "draft"},
            operation=Operation.UPDATE,
            original={"contractNumber": "CNT-001", "status": "draft"},
        )
        errors2 = await validator.validate(ctx2, mock_query)
        assert errors2 == []


# =============================================================================
# NoActiveChildren Validator Tests
# =============================================================================


class TestNoActiveChildrenValidator:
    """Tests for the noActiveChildren validator."""

    @pytest.mark.asyncio
    async def test_has_children_blocks_delete(self, mock_query):
        mock_query.exists.return_value = True

        validator = NoActiveChildrenValidator(
            child_entity="Contract",
            foreign_key="customerId",
            filter_expr=None,
            message="Cannot delete: has related contracts",
            code="HAS_CONTRACTS",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"id": "customer-123"},
            operation=Operation.DELETE,
        )
        errors = await validator.validate(ctx, mock_query)
        assert len(errors) == 1
        assert errors[0].code == "HAS_CONTRACTS"

    @pytest.mark.asyncio
    async def test_no_children_allows_delete(self, mock_query):
        mock_query.exists.return_value = False

        validator = NoActiveChildrenValidator(
            child_entity="Contract",
            foreign_key="customerId",
            filter_expr=None,
            message="Cannot delete: has related contracts",
            code="HAS_CONTRACTS",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"id": "customer-123"},
            operation=Operation.DELETE,
        )
        errors = await validator.validate(ctx, mock_query)
        assert errors == []

    @pytest.mark.asyncio
    async def test_skipped_on_non_delete(self, mock_query):
        validator = NoActiveChildrenValidator(
            child_entity="Contract",
            foreign_key="customerId",
            filter_expr=None,
            message="Cannot delete: has related contracts",
            code="HAS_CONTRACTS",
            severity=Severity.ERROR,
        )

        ctx = make_context(
            {"id": "customer-123"},
            operation=Operation.UPDATE,
        )
        errors = await validator.validate(ctx, mock_query)
        assert errors == []
        mock_query.exists.assert_not_called()


# =============================================================================
# Registry Tests
# =============================================================================


class TestValidatorRegistry:
    """Tests for validator registration and creation."""

    def test_all_canned_validators_registered(self):
        registered = ValidatorRegistry.list_registered()
        expected = [
            "dateRange",
            "unique",
            "expression",
            "fieldComparison",
            "conditionalRequired",
            "immutable",
            "referenceExists",
            "noActiveChildren",
        ]
        for name in expected:
            assert name in registered, f"{name} not registered"

    def test_create_from_definition(self):
        definition = ValidatorDefinition.from_dict({
            "type": "expression",
            "params": {"rule": "count > 0"},
            "message": "Count must be positive",
            "code": "INVALID_COUNT",
            "severity": "warning",
        })

        validator = ValidatorRegistry.create(definition)
        assert isinstance(validator, ExpressionValidator)
        assert validator.severity == Severity.WARNING

    def test_unknown_validator_raises_error(self):
        with pytest.raises(ValueError) as exc_info:
            ValidatorRegistry.create(
                ValidatorDefinition(type="nonexistent", params={})
            )
        assert "nonexistent" in str(exc_info.value)
