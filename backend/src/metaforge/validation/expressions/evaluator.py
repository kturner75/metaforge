"""Evaluator for the MetaForge expression DSL.

Walks the AST and computes the result against an evaluation context
containing record data, original values, and registered functions.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from metaforge.validation.expressions.functions import FunctionRegistry
from metaforge.validation.expressions.parser import (
    ASTNode,
    ArrayLiteral,
    BinaryOp,
    FunctionCall,
    Identifier,
    IndexAccess,
    Literal,
    MemberAccess,
    ObjectLiteral,
    ParseError,
    UnaryOp,
    parse,
)


class EvaluationError(Exception):
    """Error during expression evaluation."""
    pass


@dataclass
class EvaluationContext:
    """Context for expression evaluation.

    Attributes:
        record: The current record being validated/processed
        original: The original record (for updates), or None for creates
        variables: Additional variables available in expressions
        query_service: Service for query functions (exists, count, lookup)
    """

    record: dict[str, Any]
    original: dict[str, Any] | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    query_service: Any = None  # QueryService protocol, but avoiding import


class Evaluator:
    """Evaluates expression AST against a context.

    Usage:
        ctx = EvaluationContext(record={"status": "active", "count": 5})
        evaluator = Evaluator(ctx)
        result = evaluator.evaluate(ast)
    """

    def __init__(self, context: EvaluationContext):
        self.context = context

    def evaluate(self, node: ASTNode) -> Any:
        """Evaluate an AST node and return the result."""
        method_name = f"_eval_{type(node).__name__.lower()}"
        method = getattr(self, method_name, None)

        if method is None:
            raise EvaluationError(f"Unknown node type: {type(node).__name__}")

        return method(node)

    # -------------------------------------------------------------------------
    # Node type evaluators
    # -------------------------------------------------------------------------

    def _eval_literal(self, node: Literal) -> Any:
        """Evaluate a literal value."""
        return node.value

    def _eval_identifier(self, node: Identifier) -> Any:
        """Evaluate an identifier (field reference)."""
        name = node.name

        # Check special prefixes
        if name == "original":
            return self.context.original or {}
        if name == "record":
            return self.context.record

        # Check variables first
        if name in self.context.variables:
            return self.context.variables[name]

        # Then check record
        if name in self.context.record:
            return self.context.record[name]

        # Field doesn't exist - return None rather than error
        return None

    def _eval_memberaccess(self, node: MemberAccess) -> Any:
        """Evaluate member access (a.b)."""
        obj = self.evaluate(node.object)

        if obj is None:
            return None

        if isinstance(obj, dict):
            return obj.get(node.member)

        # Try attribute access for objects
        if hasattr(obj, node.member):
            return getattr(obj, node.member)

        return None

    def _eval_indexaccess(self, node: IndexAccess) -> Any:
        """Evaluate index access (a[b])."""
        obj = self.evaluate(node.object)
        index = self.evaluate(node.index)

        if obj is None:
            return None

        try:
            if isinstance(obj, dict):
                return obj.get(index)
            if isinstance(obj, (list, tuple, str)):
                if isinstance(index, int):
                    if 0 <= index < len(obj):
                        return obj[index]
                    return None
                return None
        except (TypeError, IndexError):
            return None

        return None

    def _eval_binaryop(self, node: BinaryOp) -> Any:
        """Evaluate a binary operation."""
        op = node.operator

        # Short-circuit evaluation for logical operators
        if op == "&&":
            left = self.evaluate(node.left)
            if not self._to_bool(left):
                return False
            return self._to_bool(self.evaluate(node.right))

        if op == "||":
            left = self.evaluate(node.left)
            if self._to_bool(left):
                return True
            return self._to_bool(self.evaluate(node.right))

        # Evaluate both operands for other operators
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        # Comparison operators
        if op == "==":
            return self._equals(left, right)
        if op == "!=":
            return not self._equals(left, right)
        if op == "<":
            return self._compare(left, right) < 0
        if op == "<=":
            return self._compare(left, right) <= 0
        if op == ">":
            return self._compare(left, right) > 0
        if op == ">=":
            return self._compare(left, right) >= 0

        # Membership operators
        if op == "in":
            return self._in(left, right)
        if op == "not in":
            return not self._in(left, right)

        # Arithmetic operators
        if op == "+":
            return self._add(left, right)
        if op == "-":
            return self._subtract(left, right)
        if op == "*":
            return self._multiply(left, right)
        if op == "/":
            return self._divide(left, right)
        if op == "%":
            return self._modulo(left, right)

        raise EvaluationError(f"Unknown operator: {op}")

    def _eval_unaryop(self, node: UnaryOp) -> Any:
        """Evaluate a unary operation."""
        operand = self.evaluate(node.operand)

        if node.operator == "!":
            return not self._to_bool(operand)

        if node.operator == "-":
            if operand is None:
                return None
            if isinstance(operand, (int, float, Decimal)):
                return -operand
            raise EvaluationError(f"Cannot negate non-numeric value: {operand}")

        raise EvaluationError(f"Unknown unary operator: {node.operator}")

    def _eval_functioncall(self, node: FunctionCall) -> Any:
        """Evaluate a function call."""
        func_name = node.name

        # Check if function is registered
        if not FunctionRegistry.is_registered(func_name):
            raise EvaluationError(f"Unknown function: {func_name}")

        func_def = FunctionRegistry.get(func_name)

        # Evaluate arguments
        args = [self.evaluate(arg) for arg in node.arguments]

        # Query functions need special handling
        if func_def.implementation is None:
            return self._call_query_function(func_name, args)

        # Call the function
        try:
            return func_def.implementation(*args)
        except Exception as e:
            raise EvaluationError(f"Error calling {func_name}: {e}")

    def _call_query_function(self, name: str, args: list[Any]) -> Any:
        """Call a query function (exists, count, lookup)."""
        if self.context.query_service is None:
            raise EvaluationError(
                f"Query function '{name}' requires a QueryService but none was provided"
            )

        # This would be async in the actual implementation
        # For now, we'll raise an error indicating it needs async handling
        raise EvaluationError(
            f"Query function '{name}' must be called asynchronously. "
            "Use evaluate_async() instead."
        )

    def _eval_arrayliteral(self, node: ArrayLiteral) -> list[Any]:
        """Evaluate an array literal."""
        return [self.evaluate(elem) for elem in node.elements]

    def _eval_objectliteral(self, node: ObjectLiteral) -> dict[str, Any]:
        """Evaluate an object literal."""
        return {key: self.evaluate(value) for key, value in node.pairs.items()}

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _to_bool(self, value: Any) -> bool:
        """Convert a value to boolean."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float, Decimal)):
            return value != 0
        if isinstance(value, str):
            return len(value) > 0
        if isinstance(value, (list, tuple, dict)):
            return len(value) > 0
        return True

    def _equals(self, left: Any, right: Any) -> bool:
        """Check equality with type coercion."""
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False

        # Numeric comparison
        if isinstance(left, (int, float, Decimal)) and isinstance(
            right, (int, float, Decimal)
        ):
            return float(left) == float(right)

        # Date comparison
        if isinstance(left, (date, datetime)) and isinstance(right, (date, datetime)):
            # Convert datetime to date for comparison if needed
            if isinstance(left, datetime) and isinstance(right, date) and not isinstance(right, datetime):
                left = left.date()
            elif isinstance(right, datetime) and isinstance(left, date) and not isinstance(left, datetime):
                right = right.date()
            return left == right

        return left == right

    def _compare(self, left: Any, right: Any) -> int:
        """Compare two values, returning -1, 0, or 1."""
        if left is None or right is None:
            # None comparisons: None < any non-None value
            if left is None and right is None:
                return 0
            if left is None:
                return -1
            return 1

        # Numeric comparison
        if isinstance(left, (int, float, Decimal)) and isinstance(
            right, (int, float, Decimal)
        ):
            diff = float(left) - float(right)
            if diff < 0:
                return -1
            if diff > 0:
                return 1
            return 0

        # Date comparison
        if isinstance(left, (date, datetime)) and isinstance(right, (date, datetime)):
            if left < right:
                return -1
            if left > right:
                return 1
            return 0

        # String comparison
        if isinstance(left, str) and isinstance(right, str):
            if left < right:
                return -1
            if left > right:
                return 1
            return 0

        raise EvaluationError(f"Cannot compare {type(left).__name__} and {type(right).__name__}")

    def _in(self, item: Any, collection: Any) -> bool:
        """Check if item is in collection."""
        if collection is None:
            return False

        if isinstance(collection, str):
            if item is None:
                return False
            return str(item) in collection

        if isinstance(collection, (list, tuple)):
            return item in collection

        if isinstance(collection, dict):
            return item in collection

        raise EvaluationError(f"'in' operator requires collection, got {type(collection).__name__}")

    def _add(self, left: Any, right: Any) -> Any:
        """Add two values."""
        if left is None or right is None:
            return None

        # String concatenation
        if isinstance(left, str) or isinstance(right, str):
            return str(left) + str(right)

        # Numeric addition
        if isinstance(left, (int, float, Decimal)) and isinstance(
            right, (int, float, Decimal)
        ):
            return left + right

        raise EvaluationError(f"Cannot add {type(left).__name__} and {type(right).__name__}")

    def _subtract(self, left: Any, right: Any) -> Any:
        """Subtract two values."""
        if left is None or right is None:
            return None

        if isinstance(left, (int, float, Decimal)) and isinstance(
            right, (int, float, Decimal)
        ):
            return left - right

        raise EvaluationError(
            f"Cannot subtract {type(right).__name__} from {type(left).__name__}"
        )

    def _multiply(self, left: Any, right: Any) -> Any:
        """Multiply two values."""
        if left is None or right is None:
            return None

        if isinstance(left, (int, float, Decimal)) and isinstance(
            right, (int, float, Decimal)
        ):
            return left * right

        raise EvaluationError(
            f"Cannot multiply {type(left).__name__} and {type(right).__name__}"
        )

    def _divide(self, left: Any, right: Any) -> Any:
        """Divide two values."""
        if left is None or right is None:
            return None

        if isinstance(left, (int, float, Decimal)) and isinstance(
            right, (int, float, Decimal)
        ):
            if right == 0:
                raise EvaluationError("Division by zero")
            return left / right

        raise EvaluationError(
            f"Cannot divide {type(left).__name__} by {type(right).__name__}"
        )

    def _modulo(self, left: Any, right: Any) -> Any:
        """Modulo operation."""
        if left is None or right is None:
            return None

        if isinstance(left, (int, float, Decimal)) and isinstance(
            right, (int, float, Decimal)
        ):
            if right == 0:
                raise EvaluationError("Modulo by zero")
            return left % right

        raise EvaluationError(
            f"Cannot modulo {type(left).__name__} by {type(right).__name__}"
        )


# -----------------------------------------------------------------------------
# Convenience functions
# -----------------------------------------------------------------------------


def evaluate(
    expression: str,
    record: dict[str, Any],
    original: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> Any:
    """Evaluate an expression string against a record.

    This is the main entry point for expression evaluation.

    Args:
        expression: The expression string to evaluate
        record: The current record data
        original: Original record data (for updates)
        variables: Additional variables to make available

    Returns:
        The result of evaluating the expression

    Example:
        result = evaluate(
            'status == "active" && count > 0',
            {"status": "active", "count": 5}
        )
        # result = True
    """
    ast = parse(expression)
    ctx = EvaluationContext(
        record=record,
        original=original,
        variables=variables or {},
    )
    evaluator = Evaluator(ctx)
    return evaluator.evaluate(ast)


def evaluate_bool(
    expression: str,
    record: dict[str, Any],
    original: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> bool:
    """Evaluate an expression and return boolean result.

    Convenience wrapper that ensures a boolean result.
    """
    result = evaluate(expression, record, original, variables)

    if result is None:
        return False
    if isinstance(result, bool):
        return result
    if isinstance(result, (int, float, Decimal)):
        return result != 0
    if isinstance(result, str):
        return len(result) > 0
    if isinstance(result, (list, tuple, dict)):
        return len(result) > 0
    return True
