"""Function registry for the MetaForge expression DSL.

Functions are callable from expressions (e.g., `len(name) > 0`, `now()`).
Each function is registered with metadata for documentation and client-side
evaluation support.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class FunctionCategory(Enum):
    """Categories for organizing functions in documentation."""

    STRING = "string"
    DATE = "date"
    MATH = "math"
    COLLECTION = "collection"
    LOGIC = "logic"
    QUERY = "query"  # Server-only, requires database access


@dataclass
class FunctionParameter:
    """Definition of a function parameter.

    Attributes:
        name: Parameter name
        type: Expected type ("string", "number", "date", "any", "array", etc.)
        description: Human-readable description
        required: Whether this parameter is required
        default: Default value if not provided
        variadic: If True, this parameter accepts multiple values
    """

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    variadic: bool = False


@dataclass
class FunctionDefinition:
    """Complete definition of an expression function.

    Attributes:
        name: Function name as used in expressions
        description: Human-readable description
        category: Category for documentation organization
        parameters: List of parameter definitions
        return_type: Type of the return value
        client_evaluable: Whether this function can be evaluated in the browser
        examples: Example expressions using this function
        implementation: The actual Python callable (None for query functions)
    """

    name: str
    description: str
    category: FunctionCategory
    parameters: list[FunctionParameter]
    return_type: str
    client_evaluable: bool
    examples: list[str] = field(default_factory=list)
    implementation: Callable[..., Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Export for API documentation endpoint."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "variadic": p.variadic,
                }
                for p in self.parameters
            ],
            "returnType": self.return_type,
            "clientEvaluable": self.client_evaluable,
            "examples": self.examples,
        }


class FunctionRegistry:
    """Registry for expression functions.

    Functions are registered with full metadata including:
    - Parameter definitions
    - Documentation
    - Client evaluability
    - The actual implementation

    Example:
        FunctionRegistry.register(FunctionDefinition(
            name="len",
            description="Returns length of string or array",
            ...
        ))

        func = FunctionRegistry.get("len")
        result = func.implementation("hello")  # Returns 5
    """

    _functions: dict[str, FunctionDefinition] = {}

    @classmethod
    def register(cls, func_def: FunctionDefinition) -> None:
        """Register a function definition.

        Args:
            func_def: Complete function definition with implementation
        """
        cls._functions[func_def.name] = func_def

    @classmethod
    def get(cls, name: str) -> FunctionDefinition:
        """Get a function definition by name.

        Args:
            name: Function name

        Returns:
            The function definition

        Raises:
            ValueError: If function is not registered
        """
        if name not in cls._functions:
            raise ValueError(f"Unknown function: {name}")
        return cls._functions[name]

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a function is registered."""
        return name in cls._functions

    @classmethod
    def call(cls, name: str, *args: Any, **kwargs: Any) -> Any:
        """Call a registered function.

        Args:
            name: Function name
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            ValueError: If function not registered or has no implementation
        """
        func_def = cls.get(name)
        if func_def.implementation is None:
            raise ValueError(
                f"Function '{name}' has no implementation. "
                "Query functions require a QueryService context."
            )
        return func_def.implementation(*args, **kwargs)

    @classmethod
    def list_all(cls) -> list[FunctionDefinition]:
        """List all registered functions."""
        return list(cls._functions.values())

    @classmethod
    def list_client_evaluable(cls) -> list[FunctionDefinition]:
        """List functions that can be evaluated client-side."""
        return [f for f in cls._functions.values() if f.client_evaluable]

    @classmethod
    def list_by_category(cls, category: FunctionCategory) -> list[FunctionDefinition]:
        """List functions in a specific category."""
        return [f for f in cls._functions.values() if f.category == category]

    @classmethod
    def export_documentation(cls) -> dict[str, Any]:
        """Export full registry for documentation or API endpoint.

        Returns:
            Dict with all function definitions organized by category
        """
        by_category: dict[str, list[dict[str, Any]]] = {}
        for func_def in cls._functions.values():
            category = func_def.category.value
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(func_def.to_dict())

        return {
            "functions": {name: f.to_dict() for name, f in cls._functions.items()},
            "byCategory": by_category,
            "clientEvaluable": [
                f.name for f in cls._functions.values() if f.client_evaluable
            ],
        }

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations. Primarily for testing."""
        cls._functions.clear()
