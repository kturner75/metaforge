"""Field-level constraint validators (Layer 0).

These validators are automatically generated from field metadata to enforce:
- required: Field must have a non-empty value
- min/max: Numeric bounds
- minLength/maxLength: String length bounds
- pattern: Regex pattern matching
- Type-specific formats: email, phone, url, etc.
"""

import re
from dataclasses import dataclass
from typing import Any

from metaforge.metadata.loader import FieldDefinition, ValidationRules
from metaforge.validation.types import (
    Operation,
    QueryService,
    Severity,
    ValidationContext,
    ValidationError,
    Validator,
)


# =============================================================================
# Type-Specific Format Patterns
# =============================================================================

# Email: Basic RFC 5322 compliant pattern
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)

# Phone: Flexible pattern supporting international formats
PHONE_PATTERN = re.compile(
    r"^[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,9}$"
)

# URL: Basic URL pattern
URL_PATTERN = re.compile(
    r"^https?://[^\s/$.?#].[^\s]*$",
    re.IGNORECASE
)

# UUID pattern
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE
)


# =============================================================================
# Field Constraint Validator
# =============================================================================


@dataclass
class FieldConstraintValidator:
    """Validates a single field against its metadata constraints.

    This validator handles all Layer 0 validation:
    - Required check
    - Type format validation (email, phone, url)
    - Numeric min/max bounds
    - String length bounds
    - Custom regex pattern
    """

    field: FieldDefinition

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        """Validate field constraints."""
        errors: list[ValidationError] = []

        field_name = self.field.name
        value = ctx.record.get(field_name)
        rules = self.field.validation

        # Skip validation for auto-populated and read-only fields on create
        # (they get their values from the system)
        if self.field.auto and ctx.operation == Operation.CREATE:
            return errors

        # Required check
        if rules.required:
            if self._is_empty(value):
                errors.append(ValidationError(
                    message=f"{self.field.display_name} is required",
                    code="REQUIRED",
                    field=field_name,
                    severity=Severity.ERROR,
                ))
                # Don't continue validation if required field is empty
                return errors

        # Skip remaining validation if value is empty (optional field)
        if self._is_empty(value):
            return errors

        # Type-specific format validation
        type_error = self._validate_type_format(value)
        if type_error:
            errors.append(ValidationError(
                message=type_error,
                code=f"INVALID_{self.field.type.upper()}",
                field=field_name,
                severity=Severity.ERROR,
            ))
            return errors  # Don't continue if type is invalid

        # Numeric bounds (for number, currency, percent types)
        if self.field.type in ("number", "currency", "percent"):
            bound_errors = self._validate_numeric_bounds(value, rules)
            errors.extend(bound_errors)

        # String length bounds (for string-like types)
        if self.field.type in ("text", "name", "description", "string"):
            length_errors = self._validate_string_length(value, rules)
            errors.extend(length_errors)

        # Custom pattern validation
        if rules.pattern:
            pattern_error = self._validate_pattern(value, rules.pattern)
            if pattern_error:
                errors.append(pattern_error)

        # Picklist value validation
        if self.field.type in ("picklist", "multi_picklist"):
            picklist_errors = self._validate_picklist(value)
            errors.extend(picklist_errors)

        return errors

    def _is_empty(self, value: Any) -> bool:
        """Check if a value is considered empty."""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        if isinstance(value, (list, dict)) and len(value) == 0:
            return True
        return False

    def _validate_type_format(self, value: Any) -> str | None:
        """Validate value against type-specific format. Returns error message or None."""
        field_type = self.field.type

        if field_type == "email":
            if isinstance(value, str) and not EMAIL_PATTERN.match(value):
                return f"{self.field.display_name} must be a valid email address"

        elif field_type == "phone":
            if isinstance(value, str) and not PHONE_PATTERN.match(value):
                return f"{self.field.display_name} must be a valid phone number"

        elif field_type == "url":
            if isinstance(value, str) and not URL_PATTERN.match(value):
                return f"{self.field.display_name} must be a valid URL"

        elif field_type == "uuid":
            if isinstance(value, str) and not UUID_PATTERN.match(value):
                return f"{self.field.display_name} must be a valid UUID"

        elif field_type in ("number", "currency", "percent"):
            if not isinstance(value, (int, float)) and value is not None:
                # Try to parse string as number
                if isinstance(value, str):
                    try:
                        float(value)
                    except ValueError:
                        return f"{self.field.display_name} must be a number"

        elif field_type == "checkbox":
            if not isinstance(value, bool) and value not in (0, 1, "true", "false"):
                return f"{self.field.display_name} must be a boolean"

        elif field_type == "date":
            if isinstance(value, str):
                # Basic ISO date format check
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                    return f"{self.field.display_name} must be a valid date (YYYY-MM-DD)"

        elif field_type == "datetime":
            if isinstance(value, str):
                # Basic ISO datetime format check
                if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
                    return f"{self.field.display_name} must be a valid datetime"

        return None

    def _validate_numeric_bounds(
        self, value: Any, rules: ValidationRules
    ) -> list[ValidationError]:
        """Validate numeric min/max bounds."""
        errors = []

        # Convert to number if string
        num_value = value
        if isinstance(value, str):
            try:
                num_value = float(value)
            except ValueError:
                return errors  # Type validation will catch this

        if rules.min is not None and num_value < rules.min:
            errors.append(ValidationError(
                message=f"{self.field.display_name} must be at least {rules.min}",
                code="MIN_VALUE",
                field=self.field.name,
                severity=Severity.ERROR,
            ))

        if rules.max is not None and num_value > rules.max:
            errors.append(ValidationError(
                message=f"{self.field.display_name} must be at most {rules.max}",
                code="MAX_VALUE",
                field=self.field.name,
                severity=Severity.ERROR,
            ))

        return errors

    def _validate_string_length(
        self, value: Any, rules: ValidationRules
    ) -> list[ValidationError]:
        """Validate string length bounds."""
        errors = []

        if not isinstance(value, str):
            return errors

        length = len(value)

        if rules.min_length is not None and length < rules.min_length:
            errors.append(ValidationError(
                message=f"{self.field.display_name} must be at least {rules.min_length} characters",
                code="MIN_LENGTH",
                field=self.field.name,
                severity=Severity.ERROR,
            ))

        if rules.max_length is not None and length > rules.max_length:
            errors.append(ValidationError(
                message=f"{self.field.display_name} must be at most {rules.max_length} characters",
                code="MAX_LENGTH",
                field=self.field.name,
                severity=Severity.ERROR,
            ))

        return errors

    def _validate_pattern(self, value: Any, pattern: str) -> ValidationError | None:
        """Validate value against custom regex pattern."""
        if not isinstance(value, str):
            return None

        try:
            if not re.match(pattern, value):
                return ValidationError(
                    message=f"{self.field.display_name} format is invalid",
                    code="PATTERN_MISMATCH",
                    field=self.field.name,
                    severity=Severity.ERROR,
                )
        except re.error:
            # Invalid regex pattern in metadata - log this but don't fail
            return None

        return None

    def _validate_picklist(self, value: Any) -> list[ValidationError]:
        """Validate picklist value is one of the allowed options."""
        errors = []

        if not self.field.options:
            return errors  # No options defined, skip validation

        valid_values = {opt.get("value") for opt in self.field.options}

        if self.field.type == "multi_picklist":
            # Multi-select: value should be a list
            if isinstance(value, list):
                for v in value:
                    if v not in valid_values:
                        errors.append(ValidationError(
                            message=f"'{v}' is not a valid option for {self.field.display_name}",
                            code="INVALID_OPTION",
                            field=self.field.name,
                            severity=Severity.ERROR,
                        ))
            elif value not in valid_values:
                errors.append(ValidationError(
                    message=f"'{value}' is not a valid option for {self.field.display_name}",
                    code="INVALID_OPTION",
                    field=self.field.name,
                    severity=Severity.ERROR,
                ))
        else:
            # Single select
            if value not in valid_values:
                errors.append(ValidationError(
                    message=f"'{value}' is not a valid option for {self.field.display_name}",
                    code="INVALID_OPTION",
                    field=self.field.name,
                    severity=Severity.ERROR,
                ))

        return errors


# =============================================================================
# Field Validator Generator
# =============================================================================


def generate_field_validators(
    fields: list[FieldDefinition],
) -> list[FieldConstraintValidator]:
    """Generate field constraint validators from field definitions.

    Creates a validator for each field that has any constraints:
    - Required flag
    - Type that needs format validation (email, phone, url, etc.)
    - Numeric bounds (min/max)
    - String length bounds (minLength/maxLength)
    - Custom pattern
    - Picklist options

    Args:
        fields: List of field definitions from entity metadata

    Returns:
        List of FieldConstraintValidator instances
    """
    validators = []

    # Types that always need format validation
    format_types = {"email", "phone", "url", "uuid", "date", "datetime"}

    for field in fields:
        rules = field.validation

        # Skip fields that have no constraints
        needs_validation = (
            rules.required
            or rules.min is not None
            or rules.max is not None
            or rules.min_length is not None
            or rules.max_length is not None
            or rules.pattern is not None
            or field.type in format_types
            or field.type in ("picklist", "multi_picklist")
        )

        if needs_validation:
            validators.append(FieldConstraintValidator(field=field))

    return validators
