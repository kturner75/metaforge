"""Lexer/tokenizer for the MetaForge expression DSL.

Converts expression strings into a stream of tokens for the parser.

Token types:
- Literals: NUMBER, STRING, BOOLEAN, NULL
- Identifiers: IDENTIFIER (field names, function names)
- Operators: comparison, logical, arithmetic
- Punctuation: LPAREN, RPAREN, LBRACKET, RBRACKET, COMMA, DOT
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


class TokenType(Enum):
    """Types of tokens in the expression language."""

    # Literals
    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    NULL = auto()

    # Identifiers
    IDENTIFIER = auto()

    # Comparison operators
    EQ = auto()          # ==
    NEQ = auto()         # !=
    LT = auto()          # <
    LTE = auto()         # <=
    GT = auto()          # >
    GTE = auto()         # >=

    # Logical operators
    AND = auto()         # && or and
    OR = auto()          # || or or
    NOT = auto()         # ! or not

    # Arithmetic operators
    PLUS = auto()        # +
    MINUS = auto()       # -
    MULTIPLY = auto()    # *
    DIVIDE = auto()      # /
    MODULO = auto()      # %

    # Membership operators
    IN = auto()          # in
    NOT_IN = auto()      # not in

    # Punctuation
    LPAREN = auto()      # (
    RPAREN = auto()      # )
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    LBRACE = auto()      # {
    RBRACE = auto()      # }
    COMMA = auto()       # ,
    DOT = auto()         # .
    COLON = auto()       # :

    # End of input
    EOF = auto()


@dataclass(frozen=True)
class Token:
    """A single token from the lexer.

    Attributes:
        type: The token type
        value: The token's value (number, string content, identifier name, etc.)
        position: Character position in the source string
        line: Line number (1-indexed)
        column: Column number (1-indexed)
    """

    type: TokenType
    value: str | int | float | bool | None
    position: int
    line: int = 1
    column: int = 1

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, pos={self.position})"


class LexerError(Exception):
    """Error during lexical analysis."""

    def __init__(self, message: str, position: int, line: int = 1, column: int = 1):
        self.position = position
        self.line = line
        self.column = column
        super().__init__(f"{message} at line {line}, column {column}")


# Token patterns (order matters - longer matches first)
TOKEN_PATTERNS = [
    # Whitespace (skip)
    (r"\s+", None),

    # Multi-character operators (before single character)
    (r"==", TokenType.EQ),
    (r"!=", TokenType.NEQ),
    (r"<=", TokenType.LTE),
    (r">=", TokenType.GTE),
    (r"&&", TokenType.AND),
    (r"\|\|", TokenType.OR),

    # Single character operators
    (r"<", TokenType.LT),
    (r">", TokenType.GT),
    (r"!", TokenType.NOT),
    (r"\+", TokenType.PLUS),
    (r"-", TokenType.MINUS),
    (r"\*", TokenType.MULTIPLY),
    (r"/", TokenType.DIVIDE),
    (r"%", TokenType.MODULO),

    # Punctuation
    (r"\(", TokenType.LPAREN),
    (r"\)", TokenType.RPAREN),
    (r"\[", TokenType.LBRACKET),
    (r"\]", TokenType.RBRACKET),
    (r"\{", TokenType.LBRACE),
    (r"\}", TokenType.RBRACE),
    (r",", TokenType.COMMA),
    (r"\.", TokenType.DOT),
    (r":", TokenType.COLON),

    # Numbers (integer and float)
    (r"\d+\.\d+", TokenType.NUMBER),
    (r"\d+", TokenType.NUMBER),

    # Strings (double or single quoted)
    (r'"([^"\\]|\\.)*"', TokenType.STRING),
    (r"'([^'\\]|\\.)*'", TokenType.STRING),

    # Keywords and identifiers (must come after operators)
    (r"[a-zA-Z_][a-zA-Z0-9_]*", TokenType.IDENTIFIER),
]

# Keywords that map to specific token types
KEYWORDS = {
    "true": (TokenType.BOOLEAN, True),
    "false": (TokenType.BOOLEAN, False),
    "null": (TokenType.NULL, None),
    "and": (TokenType.AND, "and"),
    "or": (TokenType.OR, "or"),
    "not": (TokenType.NOT, "not"),
    "in": (TokenType.IN, "in"),
}


class Lexer:
    """Tokenizer for the expression DSL.

    Usage:
        lexer = Lexer('status == "active" && count > 0')
        for token in lexer:
            print(token)
    """

    def __init__(self, source: str):
        self.source = source
        self.position = 0
        self.line = 1
        self.column = 1
        self._compiled_patterns = [
            (re.compile(pattern), token_type)
            for pattern, token_type in TOKEN_PATTERNS
        ]

    def __iter__(self) -> Iterator[Token]:
        """Iterate over all tokens in the source."""
        while True:
            token = self.next_token()
            yield token
            if token.type == TokenType.EOF:
                break

    def next_token(self) -> Token:
        """Get the next token from the source."""
        if self.position >= len(self.source):
            return Token(TokenType.EOF, None, self.position, self.line, self.column)

        for pattern, token_type in self._compiled_patterns:
            match = pattern.match(self.source, self.position)
            if match:
                value = match.group()
                start_pos = self.position
                start_line = self.line
                start_column = self.column

                # Update position
                self._advance(len(value))

                # Skip whitespace
                if token_type is None:
                    return self.next_token()

                # Process the token value
                token_value: str | int | float | bool | None = value

                if token_type == TokenType.NUMBER:
                    if "." in value:
                        token_value = float(value)
                    else:
                        token_value = int(value)

                elif token_type == TokenType.STRING:
                    # Remove quotes and unescape
                    token_value = self._unescape_string(value[1:-1])

                elif token_type == TokenType.IDENTIFIER:
                    # Check for keywords
                    lower_value = value.lower()
                    if lower_value in KEYWORDS:
                        keyword_type, keyword_value = KEYWORDS[lower_value]

                        # Handle "not in" as a special case
                        if lower_value == "not":
                            # Look ahead for "in"
                            saved_pos = self.position
                            saved_line = self.line
                            saved_col = self.column

                            # Skip whitespace
                            while (
                                self.position < len(self.source)
                                and self.source[self.position].isspace()
                            ):
                                self._advance(1)

                            # Check for "in"
                            if self.source[self.position:].lower().startswith("in"):
                                in_match = re.match(
                                    r"in\b", self.source[self.position:], re.IGNORECASE
                                )
                                if in_match:
                                    self._advance(2)
                                    return Token(
                                        TokenType.NOT_IN,
                                        "not in",
                                        start_pos,
                                        start_line,
                                        start_column,
                                    )

                            # Not "not in", restore position
                            self.position = saved_pos
                            self.line = saved_line
                            self.column = saved_col

                        return Token(
                            keyword_type, keyword_value, start_pos, start_line, start_column
                        )

                return Token(token_type, token_value, start_pos, start_line, start_column)

        # No pattern matched
        raise LexerError(
            f"Unexpected character '{self.source[self.position]}'",
            self.position,
            self.line,
            self.column,
        )

    def _advance(self, count: int) -> None:
        """Advance position by count characters, updating line/column."""
        for _ in range(count):
            if self.position < len(self.source):
                if self.source[self.position] == "\n":
                    self.line += 1
                    self.column = 1
                else:
                    self.column += 1
                self.position += 1

    def _unescape_string(self, s: str) -> str:
        """Process escape sequences in a string."""
        result = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                next_char = s[i + 1]
                if next_char == "n":
                    result.append("\n")
                elif next_char == "t":
                    result.append("\t")
                elif next_char == "r":
                    result.append("\r")
                elif next_char == "\\":
                    result.append("\\")
                elif next_char == '"':
                    result.append('"')
                elif next_char == "'":
                    result.append("'")
                else:
                    result.append(next_char)
                i += 2
            else:
                result.append(s[i])
                i += 1
        return "".join(result)

    def tokenize(self) -> list[Token]:
        """Tokenize the entire source and return list of tokens."""
        return list(self)
