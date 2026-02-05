"""Core types for the MetaForge validation system.

This module defines the foundational types used across all validation layers:
- Layer 0: Field-level rules (required, min, max, pattern)
- Layer 1: Canned validators (dateRange, unique, etc.)
- Layer 2: Application validators (expression, custom)
- Layer 3: Configured validators (tenant-scoped, stored in database)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Severity(Enum):
    """Validation result severity.

    ERROR: Blocks the save operation
    WARNING: Allows save but requires explicit user acknowledgment
    """

    ERROR = "error"
    WARNING = "warning"


class Operation(Enum):
    """The type of operation being validated."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True)
class ValidationError:
    """A single validation error or warning.

    Attributes:
        message: Human-readable message (may contain interpolated field values)
        code: Machine-readable error code (e.g., "INVALID_DATE_RANGE")
        field: Field name this error relates to, or None for entity-level errors
        severity: ERROR blocks save, WARNING requires acknowledgment
    """

    message: str
    code: str
    field: str | None = None
    severity: Severity = Severity.ERROR

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "field": self.field,
            "severity": self.severity.value,
        }


@dataclass
class UserContext:
    """User context for validation, including tenant and identity information.

    Attributes:
        tenant_id: The tenant/client ID the user belongs to
        user_id: The authenticated user's ID
        roles: List of role names the user has
    """

    tenant_id: str | None = None
    user_id: str | None = None
    roles: list[str] = field(default_factory=list)


@dataclass
class ValidationContext:
    """Context passed to validators during validation.

    Attributes:
        entity_name: Name of the entity being validated
        record: The data being validated (with defaults already applied)
        operation: CREATE, UPDATE, or DELETE
        user_context: Tenant/user information (None for unauthenticated API calls)
        original_record: For UPDATE/DELETE, the existing record; None for CREATE
        entity_metadata: The full entity metadata including field definitions
    """

    entity_name: str
    record: dict[str, Any]
    operation: Operation
    user_context: UserContext | None = None
    original_record: dict[str, Any] | None = None
    entity_metadata: Any = None  # EntityModel, but avoiding circular import


class QueryService(Protocol):
    """Protocol for data access during validation.

    Validators that need to query the database (e.g., uniqueness checks,
    reference validation) receive this service as a dependency.
    """

    async def query(
        self,
        entity: str,
        filter: dict[str, Any],
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query records matching the filter.

        Args:
            entity: Entity name to query
            filter: Filter criteria
            tenant_id: Optional tenant scope (uses context tenant if not provided)

        Returns:
            List of matching records
        """
        ...

    async def exists(
        self,
        entity: str,
        filter: dict[str, Any],
        tenant_id: str | None = None,
    ) -> bool:
        """Check if any record matches the filter.

        Args:
            entity: Entity name to query
            filter: Filter criteria
            tenant_id: Optional tenant scope

        Returns:
            True if at least one record matches
        """
        ...

    async def count(
        self,
        entity: str,
        filter: dict[str, Any],
        tenant_id: str | None = None,
    ) -> int:
        """Count records matching the filter.

        Args:
            entity: Entity name to query
            filter: Filter criteria
            tenant_id: Optional tenant scope

        Returns:
            Number of matching records
        """
        ...


class Validator(Protocol):
    """Protocol that all validators must implement.

    Validators are stateless and receive all context via the validate method.
    They may be async to support database queries via QueryService.
    """

    async def validate(
        self,
        ctx: ValidationContext,
        query: QueryService,
    ) -> list[ValidationError]:
        """Validate the record in context.

        Args:
            ctx: Validation context with record, operation, user info
            query: Service for database queries (uniqueness, references, etc.)

        Returns:
            List of validation errors/warnings. Empty list means valid.
        """
        ...


@dataclass
class ValidatorDefinition:
    """Metadata definition for a validator (from YAML or database).

    This is the declarative representation; it gets resolved to an actual
    Validator instance at runtime.

    Attributes:
        type: Validator type ("dateRange", "unique", "expression", "custom")
        params: Type-specific parameters
        message: Error message template (supports interpolation)
        code: Machine-readable error code
        severity: ERROR or WARNING
        on: Operations this validator runs on (default: [CREATE, UPDATE])
        when: Optional condition expression (validator only runs if true)
    """

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    code: str = ""
    severity: Severity = Severity.ERROR
    on: list[Operation] = field(
        default_factory=lambda: [Operation.CREATE, Operation.UPDATE]
    )
    when: str | None = None  # Condition expression

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidatorDefinition":
        """Create ValidatorDefinition from YAML/JSON dict."""
        operations = data.get("on", ["create", "update"])
        if isinstance(operations, str):
            operations = [operations]

        return cls(
            type=data["type"],
            params=data.get("params", {}),
            message=data.get("message", ""),
            code=data.get("code", ""),
            severity=Severity(data.get("severity", "error")),
            on=[Operation(op) for op in operations],
            when=data.get("when"),
        )


@dataclass
class ValidationResult:
    """Result of validating a record.

    Attributes:
        valid: True if no errors (warnings don't affect this)
        errors: List of ERROR severity issues
        warnings: List of WARNING severity issues
        acknowledgment_token: If warnings present, token for acknowledgment flow
    """

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    acknowledgment_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }
        if self.acknowledgment_token:
            result["requiresAcknowledgment"] = True
            result["acknowledgmentToken"] = self.acknowledgment_token
        return result
