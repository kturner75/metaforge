"""Find the record fields an expression reads (ADR-0015).

Hosts use this to run a rule only when one of its inputs changed, or to order
conditional requirements, without walking the AST themselves.
"""

from __future__ import annotations

from collections.abc import Iterable

from metaforge.validation.expressions.parser import (
    ArrayLiteral,
    ASTNode,
    BinaryOp,
    FunctionCall,
    Identifier,
    IndexAccess,
    Literal,
    MemberAccess,
    ObjectLiteral,
    UnaryOp,
    parse,
)

# Identifiers the evaluator resolves to whole records, not fields.
_RECORD_ROOTS = frozenset({"record", "original"})

# Variables DefaultingService puts in scope (``context.userId``, ``context.tenantId``).
CONTEXT_VARIABLES: tuple[str, ...] = ("context",)


def referenced_fields(
    expression: str | ASTNode,
    *,
    variables: Iterable[str] = CONTEXT_VARIABLES,
) -> set[str]:
    """Return the names of the record fields an expression reads.

    - ``status == "active"`` reads ``status``.
    - ``record.status`` and ``original.status`` read ``status``; the evaluator
      treats both roots as records, so a change to ``status`` matters either way.
    - Function names are not fields: ``len(name) > 3`` reads ``name``.
    - Object-literal keys are not fields: ``exists("Contract", {"parentId": id})``
      reads ``id``.
    - Names in ``variables`` are left out, because the evaluator resolves them
      before the record. The default is ``("context",)``, so
      ``context.tenantId`` reads no field; pass your own to add more.

    Only the top-level field name is returned: ``address.city`` reads ``address``.
    Raises ``ParseError`` or ``LexerError`` for an expression that does not parse.
    """
    node = parse(expression) if isinstance(expression, str) else expression
    found: set[str] = set()
    _walk(node, found, frozenset(variables))
    return found


def _walk(node: ASTNode, found: set[str], variables: frozenset[str]) -> None:
    if isinstance(node, Identifier):
        if node.name not in _RECORD_ROOTS and node.name not in variables:
            found.add(node.name)
    elif isinstance(node, MemberAccess):
        if isinstance(node.object, Identifier) and node.object.name in _RECORD_ROOTS:
            found.add(node.member)
        else:
            _walk(node.object, found, variables)
    elif isinstance(node, IndexAccess):
        _walk(node.object, found, variables)
        _walk(node.index, found, variables)
    elif isinstance(node, BinaryOp):
        _walk(node.left, found, variables)
        _walk(node.right, found, variables)
    elif isinstance(node, UnaryOp):
        _walk(node.operand, found, variables)
    elif isinstance(node, FunctionCall):
        for arg in node.arguments:
            _walk(arg, found, variables)
    elif isinstance(node, ArrayLiteral):
        for element in node.elements:
            _walk(element, found, variables)
    elif isinstance(node, ObjectLiteral):
        for value in node.pairs.values():
            _walk(value, found, variables)
    elif isinstance(node, Literal):
        pass
    else:  # pragma: no cover - a new node type must be handled above
        raise TypeError(f"Unknown expression node: {type(node).__name__}")
