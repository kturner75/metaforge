"""Validator registry for MetaForge.

Provides registration and lookup for:
- Canned validators (shipped with framework)
- Custom validators (application-specific, explicitly registered)
"""

from typing import Any, Callable

from metaforge.validation.types import (
    QueryService,
    ValidationContext,
    ValidationError,
    Validator,
    ValidatorDefinition,
)


class ValidatorRegistry:
    """Registry for validator types.

    Validators must be explicitly registered before they can be used.
    This applies to both canned validators (registered by the framework)
    and custom validators (registered by the application at startup).

    Example:
        # Register a custom validator
        ValidatorRegistry.register("myapp.OrderValidator", OrderValidator)

        # Later, resolve from metadata
        validator = ValidatorRegistry.get("myapp.OrderValidator")
    """

    _validators: dict[str, type[Validator]] = {}
    _factories: dict[str, Callable[[ValidatorDefinition], Validator]] = {}

    @classmethod
    def register(cls, name: str, validator_class: type[Validator]) -> None:
        """Register a validator class by name.

        Idempotent - re-registering the same name is a no-op.

        Args:
            name: Unique identifier for the validator (e.g., "dateRange", "myapp.CustomValidator")
            validator_class: Class implementing the Validator protocol
        """
        if name in cls._validators:
            return  # Already registered, no-op
        cls._validators[name] = validator_class

    @classmethod
    def register_factory(
        cls,
        name: str,
        factory: Callable[[ValidatorDefinition], Validator],
    ) -> None:
        """Register a factory function that creates validators from definitions.

        Idempotent - re-registering the same name is a no-op.

        Use this for validators that need to be configured from metadata params.

        Args:
            name: Unique identifier for the validator type
            factory: Function that takes ValidatorDefinition and returns Validator
        """
        if name in cls._factories:
            return  # Already registered, no-op
        cls._factories[name] = factory

    @classmethod
    def get(cls, name: str) -> type[Validator]:
        """Get a registered validator class by name.

        Args:
            name: The validator name

        Returns:
            The validator class

        Raises:
            ValueError: If validator is not registered
        """
        if name not in cls._validators:
            raise ValueError(
                f"Validator '{name}' is not registered. "
                "Custom validators must be explicitly registered at application startup."
            )
        return cls._validators[name]

    @classmethod
    def create(cls, definition: ValidatorDefinition) -> Validator:
        """Create a validator instance from a definition.

        First checks for a factory, then falls back to instantiating the class.

        Args:
            definition: The validator definition from metadata

        Returns:
            A configured Validator instance
        """
        validator_type = definition.type

        # Check for factory first (parameterized validators)
        if validator_type in cls._factories:
            return cls._factories[validator_type](definition)

        # Fall back to class instantiation
        if validator_type in cls._validators:
            validator_class = cls._validators[validator_type]
            return validator_class()

        raise ValueError(
            f"Validator type '{validator_type}' is not registered. "
            "Available types: " + ", ".join(cls.list_registered())
        )

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a validator is registered."""
        return name in cls._validators or name in cls._factories

    @classmethod
    def list_registered(cls) -> list[str]:
        """List all registered validator names."""
        return sorted(set(cls._validators.keys()) | set(cls._factories.keys()))

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations. Primarily for testing."""
        cls._validators.clear()
        cls._factories.clear()


class BaseValidator:
    """Base class for validators with common functionality.

    Subclasses should override the `validate` method.
    """

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        """Validate the record. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement validate()")


class ConfiguredValidator(BaseValidator):
    """A validator configured from a ValidatorDefinition.

    This wrapper holds the definition metadata (message, code, severity, when)
    and delegates to an inner validator for the actual validation logic.
    """

    def __init__(self, definition: ValidatorDefinition, inner: Validator):
        self.definition = definition
        self.inner = inner

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        """Run the inner validator and apply definition metadata to errors."""
        # Check if this validator should run for this operation
        if ctx.operation not in self.definition.on:
            return []

        # TODO: Check "when" condition using expression evaluator
        # if self.definition.when:
        #     if not evaluate_expression(self.definition.when, ctx):
        #         return []

        # Run the inner validator
        errors = await self.inner.validate(ctx, query)

        # Apply definition metadata if not already set
        result = []
        for error in errors:
            result.append(
                ValidationError(
                    message=error.message or self.definition.message,
                    code=error.code or self.definition.code,
                    field=error.field,
                    severity=error.severity
                    if error.severity != Severity.ERROR
                    else self.definition.severity,
                )
            )
        return result


# Import Severity for the ConfiguredValidator
from metaforge.validation.types import Severity
