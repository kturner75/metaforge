"""Canned validators for MetaForge.

These are ready-to-use validators that ship with the framework.
They are declared in entity metadata and configured via parameters.

Available validators:
- dateRange: Validate start date is before end date
- unique: Validate field(s) are unique
- expression: Validate using an expression
- fieldComparison: Compare two fields
- conditionalRequired: Require field when condition is met
- immutable: Prevent field changes after create
- referenceExists: Validate foreign key exists
- referenceActive: Validate referenced record is active
- noActiveChildren: Validate no active children before delete
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from metaforge.validation.expressions import evaluate_bool
from metaforge.validation.registry import BaseValidator, ValidatorRegistry
from metaforge.validation.types import (
    Operation,
    QueryService,
    Severity,
    ValidationContext,
    ValidationError,
    ValidatorDefinition,
)


# =============================================================================
# Date Range Validator
# =============================================================================


@dataclass
class DateRangeParams:
    """Parameters for the dateRange validator."""

    start_field: str
    end_field: str
    allow_equal: bool = False


class DateRangeValidator(BaseValidator):
    """Validates that a start date is before an end date.

    Params:
        startField: Name of the start date field
        endField: Name of the end date field
        allowEqual: If true, start == end is valid (default: false)
    """

    def __init__(self, params: DateRangeParams, message: str, code: str, severity: Severity):
        self.params = params
        self.message = message
        self.code = code
        self.severity = severity

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        start_value = ctx.record.get(self.params.start_field)
        end_value = ctx.record.get(self.params.end_field)

        # If either is None, skip validation (use conditionalRequired for that)
        if start_value is None or end_value is None:
            return []

        # Convert datetime to date for comparison if needed
        if isinstance(start_value, datetime):
            start_value = start_value.date()
        if isinstance(end_value, datetime):
            end_value = end_value.date()

        # Check the relationship
        if self.params.allow_equal:
            if start_value > end_value:
                return [
                    ValidationError(
                        message=self.message,
                        code=self.code,
                        field=self.params.end_field,
                        severity=self.severity,
                    )
                ]
        else:
            if start_value >= end_value:
                return [
                    ValidationError(
                        message=self.message,
                        code=self.code,
                        field=self.params.end_field,
                        severity=self.severity,
                    )
                ]

        return []


def _date_range_factory(definition: ValidatorDefinition) -> DateRangeValidator:
    """Factory for creating DateRangeValidator from definition."""
    params = DateRangeParams(
        start_field=definition.params.get("startField", ""),
        end_field=definition.params.get("endField", ""),
        allow_equal=definition.params.get("allowEqual", False),
    )
    return DateRangeValidator(
        params=params,
        message=definition.message or f"{params.end_field} must be after {params.start_field}",
        code=definition.code or "INVALID_DATE_RANGE",
        severity=definition.severity,
    )


# =============================================================================
# Unique Validator
# =============================================================================


@dataclass
class UniqueParams:
    """Parameters for the unique validator."""

    fields: list[str]
    scope: str = "tenant"  # "tenant" or "global"


class UniqueValidator(BaseValidator):
    """Validates that field(s) are unique.

    Params:
        fields: List of field names to check for uniqueness
        scope: "tenant" (unique within tenant) or "global" (unique across all tenants)
    """

    def __init__(self, params: UniqueParams, message: str, code: str, severity: Severity):
        self.params = params
        self.message = message
        self.code = code
        self.severity = severity

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        # Build filter for duplicate check
        filter_conditions = []
        for field in self.params.fields:
            value = ctx.record.get(field)
            if value is None:
                # Can't check uniqueness on null values
                return []
            filter_conditions.append({"field": field, "op": "eq", "value": value})

        # Exclude current record on update
        if ctx.operation == Operation.UPDATE:
            # Get primary key field (assuming 'id' for now)
            record_id = ctx.record.get("id")
            if record_id:
                filter_conditions.append({"field": "id", "op": "neq", "value": record_id})

        # Determine tenant scope
        tenant_id = None
        if self.params.scope == "tenant" and ctx.user_context:
            tenant_id = ctx.user_context.tenant_id

        # Check for duplicates
        exists = await query.exists(
            ctx.entity_name,
            {"and": filter_conditions},
            tenant_id=tenant_id,
        )

        if exists:
            field_names = ", ".join(self.params.fields)
            return [
                ValidationError(
                    message=self.message,
                    code=self.code,
                    field=self.params.fields[0],  # Report on first field
                    severity=self.severity,
                )
            ]

        return []


def _unique_factory(definition: ValidatorDefinition) -> UniqueValidator:
    """Factory for creating UniqueValidator from definition."""
    fields = definition.params.get("fields", [])
    if isinstance(fields, str):
        fields = [fields]

    params = UniqueParams(
        fields=fields,
        scope=definition.params.get("scope", "tenant"),
    )
    return UniqueValidator(
        params=params,
        message=definition.message or f"{', '.join(fields)} already exists",
        code=definition.code or "DUPLICATE_VALUE",
        severity=definition.severity,
    )


# =============================================================================
# Expression Validator
# =============================================================================


class ExpressionValidator(BaseValidator):
    """Validates using an expression from the DSL.

    Params:
        rule: The expression to evaluate (must return truthy for valid)
    """

    def __init__(
        self,
        rule: str,
        message: str,
        code: str,
        severity: Severity,
        field: str | None = None,
    ):
        self.rule = rule
        self.message = message
        self.code = code
        self.severity = severity
        self.field = field

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        try:
            result = evaluate_bool(
                self.rule,
                ctx.record,
                ctx.original_record,
            )

            if not result:
                return [
                    ValidationError(
                        message=self.message,
                        code=self.code,
                        field=self.field,
                        severity=self.severity,
                    )
                ]

        except Exception as e:
            # Expression evaluation failed - treat as validation error
            return [
                ValidationError(
                    message=f"Expression evaluation failed: {e}",
                    code="EXPRESSION_ERROR",
                    field=self.field,
                    severity=Severity.ERROR,
                )
            ]

        return []


def _expression_factory(definition: ValidatorDefinition) -> ExpressionValidator:
    """Factory for creating ExpressionValidator from definition."""
    return ExpressionValidator(
        rule=definition.params.get("rule", "true"),
        message=definition.message or "Validation failed",
        code=definition.code or "EXPRESSION_VALIDATION_FAILED",
        severity=definition.severity,
        field=definition.params.get("field"),
    )


# =============================================================================
# Field Comparison Validator
# =============================================================================


class FieldComparisonValidator(BaseValidator):
    """Compares two fields using a specified operator.

    Params:
        left: Left field name
        operator: Comparison operator (eq, neq, lt, lte, gt, gte)
        right: Right field name
    """

    OPERATORS = {
        "eq": lambda a, b: a == b,
        "neq": lambda a, b: a != b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
    }

    def __init__(
        self,
        left: str,
        operator: str,
        right: str,
        message: str,
        code: str,
        severity: Severity,
    ):
        self.left = left
        self.operator = operator
        self.right = right
        self.message = message
        self.code = code
        self.severity = severity

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        left_value = ctx.record.get(self.left)
        right_value = ctx.record.get(self.right)

        # If either is None, skip validation
        if left_value is None or right_value is None:
            return []

        # Get comparison function
        compare_fn = self.OPERATORS.get(self.operator)
        if not compare_fn:
            return [
                ValidationError(
                    message=f"Unknown comparison operator: {self.operator}",
                    code="INVALID_OPERATOR",
                    severity=Severity.ERROR,
                )
            ]

        try:
            if not compare_fn(left_value, right_value):
                return [
                    ValidationError(
                        message=self.message,
                        code=self.code,
                        field=self.left,
                        severity=self.severity,
                    )
                ]
        except TypeError:
            return [
                ValidationError(
                    message=f"Cannot compare {type(left_value).__name__} and {type(right_value).__name__}",
                    code="TYPE_MISMATCH",
                    severity=Severity.ERROR,
                )
            ]

        return []


def _field_comparison_factory(definition: ValidatorDefinition) -> FieldComparisonValidator:
    """Factory for creating FieldComparisonValidator from definition."""
    return FieldComparisonValidator(
        left=definition.params.get("left", ""),
        operator=definition.params.get("operator", "eq"),
        right=definition.params.get("right", ""),
        message=definition.message or "Field comparison failed",
        code=definition.code or "FIELD_COMPARISON_FAILED",
        severity=definition.severity,
    )


# =============================================================================
# Conditional Required Validator
# =============================================================================


class ConditionalRequiredValidator(BaseValidator):
    """Requires a field when a condition is met.

    Params:
        field: The field that should be required
        when: Expression that determines when the field is required
    """

    def __init__(
        self,
        field: str,
        when: str,
        message: str,
        code: str,
        severity: Severity,
    ):
        self.field = field
        self.when = when
        self.message = message
        self.code = code
        self.severity = severity

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        # Check if condition is met
        try:
            condition_met = evaluate_bool(
                self.when,
                ctx.record,
                ctx.original_record,
            )
        except Exception:
            # If condition can't be evaluated, skip this validation
            return []

        if not condition_met:
            # Condition not met, field not required
            return []

        # Check if field has a value
        value = ctx.record.get(self.field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return [
                ValidationError(
                    message=self.message,
                    code=self.code,
                    field=self.field,
                    severity=self.severity,
                )
            ]

        return []


def _conditional_required_factory(
    definition: ValidatorDefinition,
) -> ConditionalRequiredValidator:
    """Factory for creating ConditionalRequiredValidator from definition."""
    field = definition.params.get("field", "")
    return ConditionalRequiredValidator(
        field=field,
        when=definition.params.get("when", "true"),
        message=definition.message or f"{field} is required",
        code=definition.code or "FIELD_REQUIRED",
        severity=definition.severity,
    )


# =============================================================================
# Immutable Validator
# =============================================================================


class ImmutableValidator(BaseValidator):
    """Prevents fields from being changed after create.

    Params:
        fields: List of field names that cannot be changed
        when: Optional expression for when immutability applies
    """

    def __init__(
        self,
        fields: list[str],
        when: str | None,
        message: str,
        code: str,
        severity: Severity,
    ):
        self.fields = fields
        self.when = when
        self.message = message
        self.code = code
        self.severity = severity

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        # Only applies to updates
        if ctx.operation != Operation.UPDATE:
            return []

        if ctx.original_record is None:
            return []

        # Check optional condition
        if self.when:
            try:
                condition_met = evaluate_bool(
                    self.when,
                    ctx.record,
                    ctx.original_record,
                )
                if not condition_met:
                    return []
            except Exception:
                return []

        # Check each immutable field
        errors = []
        for field in self.fields:
            original_value = ctx.original_record.get(field)
            new_value = ctx.record.get(field)

            if original_value != new_value:
                errors.append(
                    ValidationError(
                        message=self.message.format(field=field)
                        if "{field}" in self.message
                        else self.message,
                        code=self.code,
                        field=field,
                        severity=self.severity,
                    )
                )

        return errors


def _immutable_factory(definition: ValidatorDefinition) -> ImmutableValidator:
    """Factory for creating ImmutableValidator from definition."""
    fields = definition.params.get("fields", [])
    if isinstance(fields, str):
        fields = [fields]

    return ImmutableValidator(
        fields=fields,
        when=definition.params.get("when"),
        message=definition.message or "{field} cannot be changed",
        code=definition.code or "FIELD_IMMUTABLE",
        severity=definition.severity,
    )


# =============================================================================
# Reference Exists Validator
# =============================================================================


class ReferenceExistsValidator(BaseValidator):
    """Validates that a foreign key reference exists.

    Params:
        field: The field containing the foreign key
        entity: The referenced entity
        filter: Optional additional filter expression
    """

    def __init__(
        self,
        field: str,
        entity: str,
        filter_expr: str | None,
        message: str,
        code: str,
        severity: Severity,
    ):
        self.field = field
        self.entity = entity
        self.filter_expr = filter_expr
        self.message = message
        self.code = code
        self.severity = severity

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        value = ctx.record.get(self.field)

        # Skip if null (use required validation for that)
        if value is None:
            return []

        # Build filter
        filter_conditions: list[dict[str, Any]] = [
            {"field": "id", "op": "eq", "value": value}
        ]

        # TODO: Add support for filter_expr

        # Check if reference exists
        exists = await query.exists(
            self.entity,
            {"and": filter_conditions},
        )

        if not exists:
            return [
                ValidationError(
                    message=self.message,
                    code=self.code,
                    field=self.field,
                    severity=self.severity,
                )
            ]

        return []


def _reference_exists_factory(definition: ValidatorDefinition) -> ReferenceExistsValidator:
    """Factory for creating ReferenceExistsValidator from definition."""
    field = definition.params.get("field", "")
    entity = definition.params.get("entity", "")
    return ReferenceExistsValidator(
        field=field,
        entity=entity,
        filter_expr=definition.params.get("filter"),
        message=definition.message or f"Referenced {entity} not found",
        code=definition.code or "REFERENCE_NOT_FOUND",
        severity=definition.severity,
    )


# =============================================================================
# No Active Children Validator (for delete)
# =============================================================================


class NoActiveChildrenValidator(BaseValidator):
    """Validates no active children exist before delete.

    Params:
        childEntity: The child entity to check
        foreignKey: The field in child entity that references this entity
        filter: Optional additional filter (e.g., status filter)
    """

    def __init__(
        self,
        child_entity: str,
        foreign_key: str,
        filter_expr: str | None,
        message: str,
        code: str,
        severity: Severity,
    ):
        self.child_entity = child_entity
        self.foreign_key = foreign_key
        self.filter_expr = filter_expr
        self.message = message
        self.code = code
        self.severity = severity

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        # Only applies to deletes
        if ctx.operation != Operation.DELETE:
            return []

        record_id = ctx.record.get("id")
        if record_id is None:
            return []

        # Build filter
        filter_conditions: list[dict[str, Any]] = [
            {"field": self.foreign_key, "op": "eq", "value": record_id}
        ]

        # TODO: Add support for filter_expr (e.g., status != 'deleted')

        # Check if children exist
        exists = await query.exists(
            self.child_entity,
            {"and": filter_conditions},
        )

        if exists:
            return [
                ValidationError(
                    message=self.message,
                    code=self.code,
                    severity=self.severity,
                )
            ]

        return []


def _no_active_children_factory(
    definition: ValidatorDefinition,
) -> NoActiveChildrenValidator:
    """Factory for creating NoActiveChildrenValidator from definition."""
    child_entity = definition.params.get("childEntity", "")
    return NoActiveChildrenValidator(
        child_entity=child_entity,
        foreign_key=definition.params.get("foreignKey", ""),
        filter_expr=definition.params.get("filter"),
        message=definition.message or f"Cannot delete: has related {child_entity} records",
        code=definition.code or "HAS_ACTIVE_CHILDREN",
        severity=definition.severity,
    )


# =============================================================================
# Registration
# =============================================================================


def register_canned_validators() -> None:
    """Register all canned validators with the ValidatorRegistry."""
    ValidatorRegistry.register_factory("dateRange", _date_range_factory)
    ValidatorRegistry.register_factory("unique", _unique_factory)
    ValidatorRegistry.register_factory("expression", _expression_factory)
    ValidatorRegistry.register_factory("fieldComparison", _field_comparison_factory)
    ValidatorRegistry.register_factory("conditionalRequired", _conditional_required_factory)
    ValidatorRegistry.register_factory("immutable", _immutable_factory)
    ValidatorRegistry.register_factory("referenceExists", _reference_exists_factory)
    ValidatorRegistry.register_factory("noActiveChildren", _no_active_children_factory)
