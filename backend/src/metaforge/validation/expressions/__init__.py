"""Expression DSL for MetaForge validation and defaulting.

This module provides:
- FunctionRegistry: Registry for expression functions
- Lexer: Tokenizes expression strings
- Parser: Produces AST from tokens
- Evaluator: Evaluates AST against a context
"""

from metaforge.validation.expressions.evaluator import (
    EvaluationContext,
    EvaluationError,
    Evaluator,
    evaluate,
    evaluate_bool,
)
from metaforge.validation.expressions.functions import (
    FunctionCategory,
    FunctionDefinition,
    FunctionParameter,
    FunctionRegistry,
)
from metaforge.validation.expressions.lexer import Lexer, LexerError, Token, TokenType
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
    Parser,
    UnaryOp,
    parse,
)

__all__ = [
    # Evaluator
    "EvaluationContext",
    "EvaluationError",
    "Evaluator",
    "evaluate",
    "evaluate_bool",
    # Functions
    "FunctionCategory",
    "FunctionDefinition",
    "FunctionParameter",
    "FunctionRegistry",
    # Lexer
    "Lexer",
    "LexerError",
    "Token",
    "TokenType",
    # Parser
    "ASTNode",
    "ArrayLiteral",
    "BinaryOp",
    "FunctionCall",
    "Identifier",
    "IndexAccess",
    "Literal",
    "MemberAccess",
    "ObjectLiteral",
    "ParseError",
    "Parser",
    "UnaryOp",
    "parse",
]
