"""Parser for the MetaForge expression DSL.

Converts a stream of tokens into an Abstract Syntax Tree (AST).
Uses recursive descent parsing with operator precedence.

Operator Precedence (lowest to highest):
1. || (or)
2. && (and)
3. == != < <= > >= in not_in
4. + -
5. * / %
6. ! (not) - (unary)
7. . (member access) () (function call) [] (index)
"""

from dataclasses import dataclass
from typing import Any

from metaforge.validation.expressions.lexer import Lexer, LexerError, Token, TokenType


# -----------------------------------------------------------------------------
# AST Node Types
# -----------------------------------------------------------------------------


@dataclass
class ASTNode:
    """Base class for AST nodes."""
    pass


@dataclass
class Literal(ASTNode):
    """A literal value (number, string, boolean, null)."""
    value: Any


@dataclass
class Identifier(ASTNode):
    """A field or variable reference."""
    name: str


@dataclass
class MemberAccess(ASTNode):
    """Dot notation member access (e.g., original.status, customer.name)."""
    object: ASTNode
    member: str


@dataclass
class IndexAccess(ASTNode):
    """Bracket notation index access (e.g., items[0], data["key"])."""
    object: ASTNode
    index: ASTNode


@dataclass
class BinaryOp(ASTNode):
    """Binary operation (e.g., a + b, x == y)."""
    operator: str
    left: ASTNode
    right: ASTNode


@dataclass
class UnaryOp(ASTNode):
    """Unary operation (e.g., !x, -y)."""
    operator: str
    operand: ASTNode


@dataclass
class FunctionCall(ASTNode):
    """Function call (e.g., len(name), concat(a, b))."""
    name: str
    arguments: list[ASTNode]


@dataclass
class ArrayLiteral(ASTNode):
    """Array literal (e.g., [1, 2, 3], ["a", "b"])."""
    elements: list[ASTNode]


@dataclass
class ObjectLiteral(ASTNode):
    """Object literal (e.g., {"key": value})."""
    pairs: dict[str, ASTNode]


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------


class ParseError(Exception):
    """Error during parsing."""

    def __init__(self, message: str, token: Token):
        self.token = token
        super().__init__(f"{message} at position {token.position}")


class Parser:
    """Recursive descent parser for the expression DSL.

    Usage:
        parser = Parser('status == "active" && count > 0')
        ast = parser.parse()
    """

    def __init__(self, source: str):
        self.source = source
        self.lexer = Lexer(source)
        self.tokens = self.lexer.tokenize()
        self.position = 0

    def parse(self) -> ASTNode:
        """Parse the expression and return the AST root."""
        if not self.tokens or self.tokens[0].type == TokenType.EOF:
            raise ParseError("Empty expression", Token(TokenType.EOF, None, 0))

        ast = self._parse_or()

        if not self._is_at_end():
            raise ParseError(
                f"Unexpected token '{self._current().value}'",
                self._current(),
            )

        return ast

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _current(self) -> Token:
        """Get current token."""
        if self.position >= len(self.tokens):
            return Token(TokenType.EOF, None, len(self.source))
        return self.tokens[self.position]

    def _peek(self, offset: int = 0) -> Token:
        """Peek at a token without consuming it."""
        pos = self.position + offset
        if pos >= len(self.tokens):
            return Token(TokenType.EOF, None, len(self.source))
        return self.tokens[pos]

    def _is_at_end(self) -> bool:
        """Check if we've consumed all tokens."""
        return self._current().type == TokenType.EOF

    def _advance(self) -> Token:
        """Consume and return current token."""
        token = self._current()
        self.position += 1
        return token

    def _match(self, *types: TokenType) -> bool:
        """Check if current token matches any of the given types."""
        return self._current().type in types

    def _consume(self, token_type: TokenType, message: str) -> Token:
        """Consume a token of the expected type, or raise error."""
        if self._current().type == token_type:
            return self._advance()
        raise ParseError(message, self._current())

    # -------------------------------------------------------------------------
    # Parsing methods (in order of precedence, lowest to highest)
    # -------------------------------------------------------------------------

    def _parse_or(self) -> ASTNode:
        """Parse OR expression (lowest precedence)."""
        left = self._parse_and()

        while self._match(TokenType.OR):
            self._advance()
            right = self._parse_and()
            left = BinaryOp("||", left, right)

        return left

    def _parse_and(self) -> ASTNode:
        """Parse AND expression."""
        left = self._parse_comparison()

        while self._match(TokenType.AND):
            self._advance()
            right = self._parse_comparison()
            left = BinaryOp("&&", left, right)

        return left

    def _parse_comparison(self) -> ASTNode:
        """Parse comparison expression (==, !=, <, <=, >, >=, in, not in)."""
        left = self._parse_additive()

        comparison_ops = {
            TokenType.EQ: "==",
            TokenType.NEQ: "!=",
            TokenType.LT: "<",
            TokenType.LTE: "<=",
            TokenType.GT: ">",
            TokenType.GTE: ">=",
            TokenType.IN: "in",
            TokenType.NOT_IN: "not in",
        }

        while self._current().type in comparison_ops:
            op_token = self._advance()
            op = comparison_ops[op_token.type]
            right = self._parse_additive()
            left = BinaryOp(op, left, right)

        return left

    def _parse_additive(self) -> ASTNode:
        """Parse additive expression (+, -)."""
        left = self._parse_multiplicative()

        while self._match(TokenType.PLUS, TokenType.MINUS):
            op = "+" if self._current().type == TokenType.PLUS else "-"
            self._advance()
            right = self._parse_multiplicative()
            left = BinaryOp(op, left, right)

        return left

    def _parse_multiplicative(self) -> ASTNode:
        """Parse multiplicative expression (*, /, %)."""
        left = self._parse_unary()

        while self._match(TokenType.MULTIPLY, TokenType.DIVIDE, TokenType.MODULO):
            if self._current().type == TokenType.MULTIPLY:
                op = "*"
            elif self._current().type == TokenType.DIVIDE:
                op = "/"
            else:
                op = "%"
            self._advance()
            right = self._parse_unary()
            left = BinaryOp(op, left, right)

        return left

    def _parse_unary(self) -> ASTNode:
        """Parse unary expression (!, not, -)."""
        if self._match(TokenType.NOT):
            self._advance()
            operand = self._parse_unary()
            return UnaryOp("!", operand)

        if self._match(TokenType.MINUS):
            self._advance()
            operand = self._parse_unary()
            return UnaryOp("-", operand)

        return self._parse_postfix()

    def _parse_postfix(self) -> ASTNode:
        """Parse postfix expressions (member access, index, function call)."""
        expr = self._parse_primary()

        while True:
            if self._match(TokenType.DOT):
                self._advance()
                member_token = self._consume(
                    TokenType.IDENTIFIER, "Expected identifier after '.'"
                )
                expr = MemberAccess(expr, str(member_token.value))

            elif self._match(TokenType.LBRACKET):
                self._advance()
                index = self._parse_or()
                self._consume(TokenType.RBRACKET, "Expected ']' after index")
                expr = IndexAccess(expr, index)

            elif self._match(TokenType.LPAREN) and isinstance(expr, Identifier):
                # Function call
                expr = self._parse_function_call(expr.name)

            else:
                break

        return expr

    def _parse_primary(self) -> ASTNode:
        """Parse primary expression (literals, identifiers, grouped expressions)."""
        token = self._current()

        # Literals
        if token.type == TokenType.NUMBER:
            self._advance()
            return Literal(token.value)

        if token.type == TokenType.STRING:
            self._advance()
            return Literal(token.value)

        if token.type == TokenType.BOOLEAN:
            self._advance()
            return Literal(token.value)

        if token.type == TokenType.NULL:
            self._advance()
            return Literal(None)

        # Identifier (field reference or function name)
        if token.type == TokenType.IDENTIFIER:
            self._advance()
            # Check if it's a function call
            if self._match(TokenType.LPAREN):
                return self._parse_function_call(str(token.value))
            return Identifier(str(token.value))

        # Grouped expression
        if token.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_or()
            self._consume(TokenType.RPAREN, "Expected ')' after expression")
            return expr

        # Array literal
        if token.type == TokenType.LBRACKET:
            return self._parse_array_literal()

        # Object literal
        if token.type == TokenType.LBRACE:
            return self._parse_object_literal()

        raise ParseError(f"Unexpected token '{token.value}'", token)

    def _parse_function_call(self, name: str) -> FunctionCall:
        """Parse a function call (arguments in parentheses)."""
        self._consume(TokenType.LPAREN, "Expected '(' after function name")

        arguments: list[ASTNode] = []

        if not self._match(TokenType.RPAREN):
            arguments.append(self._parse_or())

            while self._match(TokenType.COMMA):
                self._advance()
                arguments.append(self._parse_or())

        self._consume(TokenType.RPAREN, "Expected ')' after arguments")

        return FunctionCall(name, arguments)

    def _parse_array_literal(self) -> ArrayLiteral:
        """Parse an array literal [a, b, c]."""
        self._consume(TokenType.LBRACKET, "Expected '['")

        elements: list[ASTNode] = []

        if not self._match(TokenType.RBRACKET):
            elements.append(self._parse_or())

            while self._match(TokenType.COMMA):
                self._advance()
                elements.append(self._parse_or())

        self._consume(TokenType.RBRACKET, "Expected ']' after array elements")

        return ArrayLiteral(elements)

    def _parse_object_literal(self) -> ObjectLiteral:
        """Parse an object literal {"key": value}."""
        self._consume(TokenType.LBRACE, "Expected '{'")

        pairs: dict[str, ASTNode] = {}

        if not self._match(TokenType.RBRACE):
            key, value = self._parse_object_pair()
            pairs[key] = value

            while self._match(TokenType.COMMA):
                self._advance()
                key, value = self._parse_object_pair()
                pairs[key] = value

        self._consume(TokenType.RBRACE, "Expected '}' after object")

        return ObjectLiteral(pairs)

    def _parse_object_pair(self) -> tuple[str, ASTNode]:
        """Parse a key-value pair in an object literal."""
        # Key can be string or identifier
        if self._match(TokenType.STRING):
            key = str(self._advance().value)
        elif self._match(TokenType.IDENTIFIER):
            key = str(self._advance().value)
        else:
            raise ParseError("Expected string or identifier as object key", self._current())

        self._consume(TokenType.COLON, "Expected ':' after object key")

        value = self._parse_or()

        return key, value


def parse(source: str) -> ASTNode:
    """Convenience function to parse an expression string.

    Args:
        source: The expression string

    Returns:
        The AST root node
    """
    return Parser(source).parse()
