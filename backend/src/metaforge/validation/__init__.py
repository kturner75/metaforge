"""MetaForge validation system.

This module provides a three-layer validation architecture:
- Layer 0: Field-level rules (required, min, max, pattern)
- Layer 1: Canned validators (dateRange, unique, expression)
- Layer 2: Application validators (custom, coded)
- Layer 3: Configured validators (tenant-scoped, stored in database)

Usage:
    from metaforge.validation import (
        register_all_builtins,
        register_canned_validators,
        ValidationService,
        DefaultingService,
        EntityLifecycle,
    )

    # At application startup
    register_all_builtins()
    register_canned_validators()
"""

from metaforge.validation.acknowledgment import (
    AcknowledgmentError,
    DataChangedError,
    SaveResponse,
    TokenExpiredError,
    TokenInvalidError,
    WarningAcknowledgmentService,
    create_acknowledgment_error_response,
    create_error_response,
    create_success_response,
    create_warning_response,
)
from metaforge.validation.expressions import (
    EvaluationContext,
    EvaluationError,
    evaluate,
    evaluate_bool,
    FunctionRegistry,
)
from metaforge.validation.expressions.builtins import register_all_builtins
from metaforge.validation.registry import (
    BaseValidator,
    ConfiguredValidator,
    ValidatorRegistry,
)
from metaforge.validation.services import (
    DefaultDefinition,
    DefaultingService,
    DefaultPolicy,
    EntityLifecycle,
    LifecycleResult,
    MessageInterpolator,
    ValidationService,
)
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
from metaforge.validation.validators import register_canned_validators

__all__ = [
    # Types
    "Operation",
    "QueryService",
    "Severity",
    "UserContext",
    "ValidationContext",
    "ValidationError",
    "ValidationResult",
    "Validator",
    "ValidatorDefinition",
    # Registry
    "BaseValidator",
    "ConfiguredValidator",
    "ValidatorRegistry",
    # Expressions
    "EvaluationContext",
    "EvaluationError",
    "evaluate",
    "evaluate_bool",
    "FunctionRegistry",
    # Services
    "DefaultDefinition",
    "DefaultingService",
    "DefaultPolicy",
    "EntityLifecycle",
    "LifecycleResult",
    "MessageInterpolator",
    "ValidationService",
    # Acknowledgment
    "AcknowledgmentError",
    "DataChangedError",
    "SaveResponse",
    "TokenExpiredError",
    "TokenInvalidError",
    "WarningAcknowledgmentService",
    "create_acknowledgment_error_response",
    "create_error_response",
    "create_success_response",
    "create_warning_response",
    # Setup
    "register_all_builtins",
    "register_canned_validators",
]
