"""Validation and defaulting services for MetaForge.

This module provides the main services that orchestrate the entity lifecycle:
1. DefaultingService: Applies defaults in order (static, computed, auto)
2. ValidationService: Runs all validators across all layers
3. MessageInterpolator: Formats error messages with field values
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

from metaforge.validation.expressions import evaluate, evaluate_bool
from metaforge.validation.registry import ValidatorRegistry
from metaforge.validation.types import (
    Operation,
    QueryService,
    Severity,
    UserContext,
    ValidationContext,
    ValidationError,
    ValidationResult,
    Validator,
    ValidatorDefinition,
)


# =============================================================================
# Defaulting Types
# =============================================================================


class DefaultPolicy(Enum):
    """Policy for when to apply a default value."""

    DEFAULT = "default"  # Only apply when value is null or empty
    OVERWRITE = "overwrite"  # Always apply, replacing existing value


@dataclass
class DefaultDefinition:
    """Definition of a default rule from metadata.

    Attributes:
        field: The field to apply the default to
        value: Static value (if no expression)
        expression: Expression to compute the value
        policy: When to apply (default or overwrite)
        when: Optional condition expression
        on: Operations this default applies to
    """

    field: str
    value: Any = None
    expression: str | None = None
    policy: DefaultPolicy = DefaultPolicy.DEFAULT
    when: str | None = None
    on: list[Operation] = field(
        default_factory=lambda: [Operation.CREATE, Operation.UPDATE]
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DefaultDefinition":
        """Create DefaultDefinition from YAML/JSON dict."""
        operations = data.get("on", ["create", "update"])
        if isinstance(operations, str):
            operations = [operations]

        return cls(
            field=data.get("field", ""),
            value=data.get("value"),
            expression=data.get("expression"),
            policy=DefaultPolicy(data.get("policy", "default")),
            when=data.get("when"),
            on=[Operation(op) for op in operations],
        )


# =============================================================================
# Defaulting Service
# =============================================================================


class DefaultingService:
    """Service for applying defaults to records.

    Defaults are applied in declared order because they may depend on
    values computed by earlier defaults.

    Auto-populated fields (createdAt, updatedAt, etc.) are handled separately
    from user-defined defaults.
    """

    def __init__(self, user_context: UserContext | None = None):
        self.user_context = user_context

    def apply_defaults(
        self,
        record: dict[str, Any],
        defaults: list[DefaultDefinition],
        operation: Operation,
        original: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply defaults to a record.

        Args:
            record: The record to apply defaults to
            defaults: List of default definitions (in order)
            operation: The current operation (CREATE, UPDATE)
            original: Original record for updates

        Returns:
            Record with defaults applied
        """
        result = dict(record)

        for default_def in defaults:
            # Check if this default applies to this operation
            if operation not in default_def.on:
                continue

            # Check condition if present
            if default_def.when:
                try:
                    if not evaluate_bool(default_def.when, result, original):
                        continue
                except Exception:
                    # If condition can't be evaluated, skip this default
                    continue

            # Check policy
            current_value = result.get(default_def.field)
            if default_def.policy == DefaultPolicy.DEFAULT:
                if not self._is_empty(current_value):
                    continue  # Value exists, don't overwrite

            # Compute the default value
            if default_def.expression:
                try:
                    computed_value = evaluate(
                        default_def.expression,
                        result,
                        original,
                        variables=self._get_context_variables(),
                    )
                    result[default_def.field] = computed_value
                except Exception:
                    # If expression fails, skip this default
                    pass
            elif default_def.value is not None:
                result[default_def.field] = default_def.value

        return result

    def apply_auto_fields(
        self,
        record: dict[str, Any],
        operation: Operation,
        auto_fields: dict[str, str],
    ) -> dict[str, Any]:
        """Apply auto-populated fields (createdAt, updatedAt, etc.).

        Args:
            record: The record to apply auto fields to
            operation: The current operation
            auto_fields: Dict of field_name -> auto_type (e.g., {"createdAt": "now"})

        Returns:
            Record with auto fields applied
        """
        result = dict(record)
        now = datetime.now(timezone.utc).isoformat()

        for field_name, auto_type in auto_fields.items():
            # Skip if field already has a value (idempotent for acknowledgment flow)
            if field_name in result and result[field_name] is not None:
                continue

            if auto_type == "now":
                # Only set on create; updatedAt is handled separately in persistence
                if field_name == "createdAt" and operation == Operation.CREATE:
                    result[field_name] = now
                elif field_name == "updatedAt":
                    result[field_name] = now

            elif auto_type == "context.userId":
                if self.user_context and self.user_context.user_id:
                    if field_name == "createdBy" and operation == Operation.CREATE:
                        result[field_name] = self.user_context.user_id
                    elif field_name == "updatedBy":
                        result[field_name] = self.user_context.user_id

            elif auto_type == "context.tenantId":
                if self.user_context and self.user_context.tenant_id:
                    if operation == Operation.CREATE:
                        result[field_name] = self.user_context.tenant_id

        return result

    def _is_empty(self, value: Any) -> bool:
        """Check if a value is considered empty for defaulting purposes."""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        return False

    def _get_context_variables(self) -> dict[str, Any]:
        """Get variables from user context for expression evaluation."""
        variables: dict[str, Any] = {}
        if self.user_context:
            variables["context"] = {
                "userId": self.user_context.user_id,
                "tenantId": self.user_context.tenant_id,
                "roles": self.user_context.roles,
            }
        return variables


# =============================================================================
# Validation Service
# =============================================================================


class ValidationService:
    """Service for running validation across all layers.

    Validates records by running validators from all layers:
    - Layer 0: Field-level rules (required, min, max, etc.) - TODO
    - Layer 1: Canned validators from metadata
    - Layer 2: Application validators from metadata
    - Layer 3: Configured validators from database

    All validators run in parallel and all errors are collected.
    """

    def __init__(
        self,
        query_service: QueryService,
        configured_validator_loader: Callable[[str, str | None], list[ValidatorDefinition]] | None = None,
    ):
        self.query_service = query_service
        self.configured_validator_loader = configured_validator_loader

    async def validate(
        self,
        ctx: ValidationContext,
        validators: list[ValidatorDefinition],
        field_validators: list[Any] | None = None,
    ) -> ValidationResult:
        """Validate a record against all validators.

        Args:
            ctx: Validation context with record, operation, user info
            validators: Validator definitions from entity metadata
            field_validators: Field constraint validators (Layer 0)

        Returns:
            ValidationResult with all errors and warnings
        """
        all_errors: list[ValidationError] = []

        # Layer 0: Field-level rules (required, format, bounds, pattern)
        if field_validators:
            field_tasks = [v.validate(ctx, self.query_service) for v in field_validators]
            field_results = await asyncio.gather(*field_tasks, return_exceptions=True)

            for result in field_results:
                if isinstance(result, Exception):
                    all_errors.append(
                        ValidationError(
                            message=f"Field validator error: {result}",
                            code="FIELD_VALIDATOR_ERROR",
                            severity=Severity.ERROR,
                        )
                    )
                else:
                    all_errors.extend(result)

        # Layer 1 & 2: Metadata validators
        metadata_validators = self._create_validators(validators, ctx.operation)

        # Layer 3: Configured validators (from database)
        configured_validators: list[Validator] = []
        if self.configured_validator_loader and ctx.user_context:
            tenant_id = ctx.user_context.tenant_id
            configured_defs = self.configured_validator_loader(ctx.entity_name, tenant_id)
            configured_validators = self._create_validators(configured_defs, ctx.operation)

        # Run all validators in parallel
        all_validators = metadata_validators + configured_validators
        if all_validators:
            tasks = [v.validate(ctx, self.query_service) for v in all_validators]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    all_errors.append(
                        ValidationError(
                            message=f"Validator error: {result}",
                            code="VALIDATOR_ERROR",
                            severity=Severity.ERROR,
                        )
                    )
                else:
                    all_errors.extend(result)

        # Separate errors and warnings
        errors = [e for e in all_errors if e.severity == Severity.ERROR]
        warnings = [e for e in all_errors if e.severity == Severity.WARNING]

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _create_validators(
        self,
        definitions: list[ValidatorDefinition],
        operation: Operation,
    ) -> list[Validator]:
        """Create validator instances from definitions.

        Filters to only validators that apply to the current operation.
        """
        validators: list[Validator] = []

        for definition in definitions:
            # Check if validator applies to this operation
            if operation not in definition.on:
                continue

            try:
                validator = ValidatorRegistry.create(definition)
                validators.append(validator)
            except ValueError as e:
                # Unknown validator type - log and skip
                # In production, this should be caught at metadata validation time
                pass

        return validators


# =============================================================================
# Message Interpolator
# =============================================================================


class MessageInterpolator:
    """Interpolates field values into error messages.

    Supports:
    - {fieldName} or {fieldName:value} - Formatted/presented value
    - {fieldName:raw} - Raw stored value
    - {fieldName:label} - Field's display label
    - {original.fieldName} - Original value (for updates)
    """

    # Pattern: {[original.]fieldName[:modifier]}
    PATTERN = re.compile(
        r"\{(?P<prefix>original\.)?(?P<field>\w+)(?::(?P<modifier>value|raw|label))?\}"
    )

    def __init__(
        self,
        field_labels: dict[str, str] | None = None,
        field_options: dict[str, list[dict[str, str]]] | None = None,
        locale: str = "en-US",
    ):
        """Initialize the interpolator.

        Args:
            field_labels: Dict of field_name -> display label
            field_options: Dict of field_name -> list of {value, label} for picklists
            locale: Locale for formatting
        """
        self.field_labels = field_labels or {}
        self.field_options = field_options or {}
        self.locale = locale

    def interpolate(
        self,
        template: str,
        record: dict[str, Any],
        original: dict[str, Any] | None = None,
    ) -> str:
        """Interpolate field values into a message template.

        Args:
            template: Message template with {field} placeholders
            record: Current record values
            original: Original record values (for updates)

        Returns:
            Message with placeholders replaced
        """

        def replace(match: re.Match) -> str:
            prefix = match.group("prefix")
            field_name = match.group("field")
            modifier = match.group("modifier") or "value"

            # Determine source (current or original)
            source = original if prefix else record
            if source is None:
                return ""

            value = source.get(field_name)

            if modifier == "label":
                return self._get_label(field_name)
            elif modifier == "raw":
                return str(value) if value is not None else ""
            else:  # "value" - formatted presentation
                return self._format_value(field_name, value)

        return self.PATTERN.sub(replace, template)

    def _get_label(self, field_name: str) -> str:
        """Get display label for a field."""
        if field_name in self.field_labels:
            return self.field_labels[field_name]
        # Convert camelCase to Title Case
        return self._to_title_case(field_name)

    def _format_value(self, field_name: str, value: Any) -> str:
        """Format a value for display."""
        if value is None:
            return ""

        # Check for picklist options
        if field_name in self.field_options:
            for option in self.field_options[field_name]:
                if option.get("value") == value:
                    return option.get("label", str(value))

        # Format by type
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, datetime):
            return value.strftime("%B %d, %Y %I:%M %p")
        if isinstance(value, date):
            return value.strftime("%B %d, %Y")
        if isinstance(value, Decimal):
            return f"${value:,.2f}"  # Simplified currency formatting
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)

        return str(value)

    def _to_title_case(self, name: str) -> str:
        """Convert camelCase to Title Case."""
        result = re.sub(r"([A-Z])", r" \1", name)
        return result.strip().title()


# =============================================================================
# Entity Lifecycle Coordinator
# =============================================================================


@dataclass
class LifecycleResult:
    """Result of the entity lifecycle (defaults + validation)."""

    record: dict[str, Any]  # Record with defaults applied
    validation: ValidationResult
    acknowledged_warnings: bool = False


class EntityLifecycle:
    """Coordinates the entity save lifecycle.

    Lifecycle:
    1. Apply defaults (in order)
    2. Apply auto fields
    3. Validate (all layers in parallel)
    4. Handle warnings (require acknowledgment)
    5. Persist (if valid)
    """

    def __init__(
        self,
        defaulting_service: DefaultingService,
        validation_service: ValidationService,
        message_interpolator: MessageInterpolator | None = None,
    ):
        self.defaulting_service = defaulting_service
        self.validation_service = validation_service
        self.message_interpolator = message_interpolator or MessageInterpolator()

    async def prepare(
        self,
        record: dict[str, Any],
        operation: Operation,
        entity_name: str,
        defaults: list[DefaultDefinition],
        auto_fields: dict[str, str],
        validators: list[ValidatorDefinition],
        original: dict[str, Any] | None = None,
        user_context: UserContext | None = None,
        field_validators: list[Any] | None = None,
    ) -> LifecycleResult:
        """Prepare a record for persistence.

        Applies defaults and validates, but does not persist.

        Args:
            record: The record data
            operation: CREATE, UPDATE, or DELETE
            entity_name: Name of the entity
            defaults: Default definitions from metadata
            auto_fields: Auto-populated field definitions
            validators: Validator definitions from metadata
            original: Original record (for updates)
            user_context: User context (tenant, user, roles)
            field_validators: Field constraint validators (Layer 0)

        Returns:
            LifecycleResult with prepared record and validation result
        """
        # Phase 1: Apply defaults
        self.defaulting_service.user_context = user_context
        prepared_record = self.defaulting_service.apply_defaults(
            record, defaults, operation, original
        )

        # Phase 1b: Apply auto fields
        prepared_record = self.defaulting_service.apply_auto_fields(
            prepared_record, operation, auto_fields
        )

        # Phase 2: Validate
        ctx = ValidationContext(
            entity_name=entity_name,
            record=prepared_record,
            operation=operation,
            user_context=user_context,
            original_record=original,
        )

        validation_result = await self.validation_service.validate(
            ctx, validators, field_validators
        )

        # Interpolate error messages
        validation_result = self._interpolate_messages(
            validation_result, prepared_record, original
        )

        return LifecycleResult(
            record=prepared_record,
            validation=validation_result,
        )

    def _interpolate_messages(
        self,
        result: ValidationResult,
        record: dict[str, Any],
        original: dict[str, Any] | None,
    ) -> ValidationResult:
        """Interpolate field values into error messages."""
        interpolated_errors = [
            ValidationError(
                message=self.message_interpolator.interpolate(e.message, record, original),
                code=e.code,
                field=e.field,
                severity=e.severity,
            )
            for e in result.errors
        ]

        interpolated_warnings = [
            ValidationError(
                message=self.message_interpolator.interpolate(w.message, record, original),
                code=w.code,
                field=w.field,
                severity=w.severity,
            )
            for w in result.warnings
        ]

        return ValidationResult(
            valid=result.valid,
            errors=interpolated_errors,
            warnings=interpolated_warnings,
            acknowledgment_token=result.acknowledgment_token,
        )
