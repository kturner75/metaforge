"""Tests for the MetaForge expression DSL.

Tests cover:
- Lexer: Tokenization of expression strings
- Parser: AST generation from tokens
- Evaluator: Expression evaluation against records
- Built-in functions: All registered functions
"""

import pytest
from datetime import date, datetime, timezone

from metaforge.validation.expressions import (
    Lexer,
    LexerError,
    Token,
    TokenType,
    Parser,
    ParseError,
    parse,
    evaluate,
    evaluate_bool,
    EvaluationContext,
    Evaluator,
    EvaluationError,
    FunctionRegistry,
    Literal,
    Identifier,
    BinaryOp,
    UnaryOp,
    FunctionCall,
    MemberAccess,
    ArrayLiteral,
)
from metaforge.validation.expressions.builtins import register_all_builtins


# Register built-in functions for tests
@pytest.fixture(autouse=True)
def setup_functions():
    """Register built-in functions before each test."""
    FunctionRegistry.clear()
    register_all_builtins()
    yield
    FunctionRegistry.clear()


# =============================================================================
# Lexer Tests
# =============================================================================


class TestLexer:
    """Tests for the expression lexer."""

    def test_tokenize_numbers(self):
        lexer = Lexer("42 3.14 0 100")
        tokens = lexer.tokenize()

        assert tokens[0] == Token(TokenType.NUMBER, 42, 0, 1, 1)
        assert tokens[1] == Token(TokenType.NUMBER, 3.14, 3, 1, 4)
        assert tokens[2] == Token(TokenType.NUMBER, 0, 8, 1, 9)
        assert tokens[3] == Token(TokenType.NUMBER, 100, 10, 1, 11)

    def test_tokenize_strings(self):
        lexer = Lexer('"hello" \'world\'')
        tokens = lexer.tokenize()

        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello"
        assert tokens[1].type == TokenType.STRING
        assert tokens[1].value == "world"

    def test_tokenize_string_escapes(self):
        lexer = Lexer(r'"hello\nworld" "tab\there"')
        tokens = lexer.tokenize()

        assert tokens[0].value == "hello\nworld"
        assert tokens[1].value == "tab\there"

    def test_tokenize_booleans(self):
        lexer = Lexer("true false TRUE False")
        tokens = lexer.tokenize()

        assert tokens[0] == Token(TokenType.BOOLEAN, True, 0, 1, 1)
        assert tokens[1] == Token(TokenType.BOOLEAN, False, 5, 1, 6)
        assert tokens[2] == Token(TokenType.BOOLEAN, True, 11, 1, 12)
        assert tokens[3] == Token(TokenType.BOOLEAN, False, 16, 1, 17)

    def test_tokenize_null(self):
        lexer = Lexer("null NULL")
        tokens = lexer.tokenize()

        assert tokens[0].type == TokenType.NULL
        assert tokens[0].value is None

    def test_tokenize_identifiers(self):
        lexer = Lexer("status firstName _private var123")
        tokens = lexer.tokenize()

        assert tokens[0] == Token(TokenType.IDENTIFIER, "status", 0, 1, 1)
        assert tokens[1] == Token(TokenType.IDENTIFIER, "firstName", 7, 1, 8)
        assert tokens[2] == Token(TokenType.IDENTIFIER, "_private", 17, 1, 18)
        assert tokens[3] == Token(TokenType.IDENTIFIER, "var123", 26, 1, 27)

    def test_tokenize_comparison_operators(self):
        lexer = Lexer("== != < <= > >=")
        tokens = lexer.tokenize()

        types = [t.type for t in tokens[:-1]]  # Exclude EOF
        assert types == [
            TokenType.EQ,
            TokenType.NEQ,
            TokenType.LT,
            TokenType.LTE,
            TokenType.GT,
            TokenType.GTE,
        ]

    def test_tokenize_logical_operators(self):
        lexer = Lexer("&& || ! and or not")
        tokens = lexer.tokenize()

        types = [t.type for t in tokens[:-1]]
        assert types == [
            TokenType.AND,
            TokenType.OR,
            TokenType.NOT,
            TokenType.AND,
            TokenType.OR,
            TokenType.NOT,
        ]

    def test_tokenize_arithmetic_operators(self):
        lexer = Lexer("+ - * / %")
        tokens = lexer.tokenize()

        types = [t.type for t in tokens[:-1]]
        assert types == [
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.MULTIPLY,
            TokenType.DIVIDE,
            TokenType.MODULO,
        ]

    def test_tokenize_membership_operators(self):
        lexer = Lexer("in not in")
        tokens = lexer.tokenize()

        assert tokens[0].type == TokenType.IN
        assert tokens[1].type == TokenType.NOT_IN

    def test_tokenize_punctuation(self):
        lexer = Lexer("( ) [ ] { } , . :")
        tokens = lexer.tokenize()

        types = [t.type for t in tokens[:-1]]
        assert types == [
            TokenType.LPAREN,
            TokenType.RPAREN,
            TokenType.LBRACKET,
            TokenType.RBRACKET,
            TokenType.LBRACE,
            TokenType.RBRACE,
            TokenType.COMMA,
            TokenType.DOT,
            TokenType.COLON,
        ]

    def test_tokenize_complex_expression(self):
        lexer = Lexer('status == "active" && count > 0')
        tokens = lexer.tokenize()

        types = [t.type for t in tokens[:-1]]
        assert types == [
            TokenType.IDENTIFIER,  # status
            TokenType.EQ,          # ==
            TokenType.STRING,      # "active"
            TokenType.AND,         # &&
            TokenType.IDENTIFIER,  # count
            TokenType.GT,          # >
            TokenType.NUMBER,      # 0
        ]

    def test_lexer_error_on_invalid_character(self):
        lexer = Lexer("status @ value")
        with pytest.raises(LexerError) as exc_info:
            lexer.tokenize()
        assert "@" in str(exc_info.value)


# =============================================================================
# Parser Tests
# =============================================================================


class TestParser:
    """Tests for the expression parser."""

    def test_parse_literal_number(self):
        ast = parse("42")
        assert isinstance(ast, Literal)
        assert ast.value == 42

    def test_parse_literal_string(self):
        ast = parse('"hello"')
        assert isinstance(ast, Literal)
        assert ast.value == "hello"

    def test_parse_literal_boolean(self):
        ast = parse("true")
        assert isinstance(ast, Literal)
        assert ast.value is True

    def test_parse_literal_null(self):
        ast = parse("null")
        assert isinstance(ast, Literal)
        assert ast.value is None

    def test_parse_identifier(self):
        ast = parse("status")
        assert isinstance(ast, Identifier)
        assert ast.name == "status"

    def test_parse_member_access(self):
        ast = parse("original.status")
        assert isinstance(ast, MemberAccess)
        assert isinstance(ast.object, Identifier)
        assert ast.object.name == "original"
        assert ast.member == "status"

    def test_parse_chained_member_access(self):
        ast = parse("customer.address.city")
        assert isinstance(ast, MemberAccess)
        assert ast.member == "city"
        assert isinstance(ast.object, MemberAccess)
        assert ast.object.member == "address"

    def test_parse_comparison(self):
        ast = parse("x == 5")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "=="
        assert isinstance(ast.left, Identifier)
        assert isinstance(ast.right, Literal)

    def test_parse_logical_and(self):
        ast = parse("a && b")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "&&"

    def test_parse_logical_or(self):
        ast = parse("a || b")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "||"

    def test_parse_unary_not(self):
        ast = parse("!active")
        assert isinstance(ast, UnaryOp)
        assert ast.operator == "!"
        assert isinstance(ast.operand, Identifier)

    def test_parse_unary_negative(self):
        ast = parse("-5")
        assert isinstance(ast, UnaryOp)
        assert ast.operator == "-"

    def test_parse_function_call_no_args(self):
        ast = parse("now()")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "now"
        assert ast.arguments == []

    def test_parse_function_call_with_args(self):
        ast = parse("concat(a, b, c)")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "concat"
        assert len(ast.arguments) == 3

    def test_parse_array_literal(self):
        ast = parse('["a", "b", "c"]')
        assert isinstance(ast, ArrayLiteral)
        assert len(ast.elements) == 3

    def test_parse_grouped_expression(self):
        ast = parse("(a + b) * c")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "*"
        assert isinstance(ast.left, BinaryOp)
        assert ast.left.operator == "+"

    def test_parse_operator_precedence(self):
        # Multiplication should bind tighter than addition
        ast = parse("a + b * c")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "+"
        assert isinstance(ast.right, BinaryOp)
        assert ast.right.operator == "*"

    def test_parse_in_operator(self):
        ast = parse('status in ["active", "pending"]')
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "in"

    def test_parse_not_in_operator(self):
        ast = parse('status not in ["deleted", "archived"]')
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "not in"

    def test_parse_complex_expression(self):
        ast = parse('status == "active" && (count > 0 || priority == "high")')
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "&&"

    def test_parse_error_on_invalid_syntax(self):
        with pytest.raises(ParseError):
            parse("status ==")

    def test_parse_error_on_empty_expression(self):
        with pytest.raises(ParseError):
            parse("")


# =============================================================================
# Evaluator Tests
# =============================================================================


class TestEvaluator:
    """Tests for expression evaluation."""

    def test_evaluate_literal(self):
        assert evaluate("42", {}) == 42
        assert evaluate('"hello"', {}) == "hello"
        assert evaluate("true", {}) is True
        assert evaluate("null", {}) is None

    def test_evaluate_field_reference(self):
        record = {"status": "active", "count": 5}
        assert evaluate("status", record) == "active"
        assert evaluate("count", record) == 5

    def test_evaluate_missing_field_returns_none(self):
        assert evaluate("missing", {}) is None

    def test_evaluate_original_reference(self):
        record = {"status": "inactive"}
        original = {"status": "active"}
        assert evaluate("original.status", record, original) == "active"

    def test_evaluate_comparison_equal(self):
        record = {"status": "active"}
        assert evaluate('status == "active"', record) is True
        assert evaluate('status == "inactive"', record) is False

    def test_evaluate_comparison_not_equal(self):
        record = {"count": 5}
        assert evaluate("count != 5", record) is False
        assert evaluate("count != 10", record) is True

    def test_evaluate_comparison_less_than(self):
        record = {"count": 5}
        assert evaluate("count < 10", record) is True
        assert evaluate("count < 5", record) is False

    def test_evaluate_comparison_greater_than(self):
        record = {"count": 5}
        assert evaluate("count > 3", record) is True
        assert evaluate("count > 5", record) is False

    def test_evaluate_logical_and(self):
        record = {"a": True, "b": True, "c": False}
        assert evaluate("a && b", record) is True
        assert evaluate("a && c", record) is False

    def test_evaluate_logical_or(self):
        record = {"a": True, "b": False, "c": False}
        assert evaluate("a || b", record) is True
        assert evaluate("b || c", record) is False

    def test_evaluate_logical_not(self):
        record = {"active": True}
        assert evaluate("!active", record) is False
        assert evaluate("!missing", record) is True  # missing is None, !None is True

    def test_evaluate_short_circuit_and(self):
        # If left is false, right should not be evaluated
        record = {"flag": False}
        # This would error if right was evaluated (missing function)
        assert evaluate("flag && nonexistent()", record) is False

    def test_evaluate_short_circuit_or(self):
        record = {"flag": True}
        assert evaluate("flag || nonexistent()", record) is True

    def test_evaluate_arithmetic(self):
        record = {"a": 10, "b": 3}
        assert evaluate("a + b", record) == 13
        assert evaluate("a - b", record) == 7
        assert evaluate("a * b", record) == 30
        assert evaluate("a / b", record) == pytest.approx(3.333, rel=0.01)
        assert evaluate("a % b", record) == 1

    def test_evaluate_string_concatenation(self):
        record = {"first": "John", "last": "Doe"}
        assert evaluate('first + " " + last', record) == "John Doe"

    def test_evaluate_in_operator(self):
        record = {"status": "active"}
        assert evaluate('status in ["active", "pending"]', record) is True
        assert evaluate('status in ["deleted", "archived"]', record) is False

    def test_evaluate_not_in_operator(self):
        record = {"status": "active"}
        assert evaluate('status not in ["deleted", "archived"]', record) is True
        assert evaluate('status not in ["active", "pending"]', record) is False

    def test_evaluate_member_access(self):
        record = {"customer": {"name": "Acme", "tier": "gold"}}
        assert evaluate("customer.name", record) == "Acme"
        assert evaluate("customer.tier", record) == "gold"

    def test_evaluate_array_literal(self):
        result = evaluate("[1, 2, 3]", {})
        assert result == [1, 2, 3]

    def test_evaluate_complex_expression(self):
        record = {
            "status": "active",
            "count": 5,
            "priority": "high",
        }
        expr = 'status == "active" && (count > 0 || priority == "high")'
        assert evaluate(expr, record) is True

    def test_evaluate_null_comparisons(self):
        record = {"value": None}
        assert evaluate("value == null", record) is True
        assert evaluate("value != null", record) is False
        assert evaluate("missing == null", record) is True

    def test_evaluate_division_by_zero(self):
        with pytest.raises(EvaluationError) as exc_info:
            evaluate("10 / 0", {})
        assert "Division by zero" in str(exc_info.value)


class TestEvaluateBool:
    """Tests for evaluate_bool convenience function."""

    def test_evaluate_bool_from_boolean(self):
        assert evaluate_bool("true", {}) is True
        assert evaluate_bool("false", {}) is False

    def test_evaluate_bool_from_number(self):
        assert evaluate_bool("5", {}) is True
        assert evaluate_bool("0", {}) is False

    def test_evaluate_bool_from_string(self):
        assert evaluate_bool('"hello"', {}) is True
        assert evaluate_bool('""', {}) is False

    def test_evaluate_bool_from_null(self):
        assert evaluate_bool("null", {}) is False


# =============================================================================
# Built-in Function Tests
# =============================================================================


class TestStringFunctions:
    """Tests for string functions."""

    def test_len_string(self):
        assert evaluate('len("hello")', {}) == 5

    def test_len_array(self):
        assert evaluate("len([1, 2, 3])", {}) == 3

    def test_len_null(self):
        assert evaluate("len(null)", {}) == 0

    def test_isEmpty_null(self):
        assert evaluate("isEmpty(null)", {}) is True

    def test_isEmpty_empty_string(self):
        assert evaluate('isEmpty("")', {}) is True
        assert evaluate('isEmpty("  ")', {}) is True  # Whitespace only

    def test_isEmpty_non_empty(self):
        assert evaluate('isEmpty("hello")', {}) is False

    def test_concat(self):
        record = {"first": "John", "last": "Doe"}
        assert evaluate('concat(first, " ", last)', record) == "John Doe"

    def test_concat_with_null(self):
        record = {"first": "John", "middle": None, "last": "Doe"}
        assert evaluate("concat(first, middle, last)", record) == "JohnDoe"

    def test_trim(self):
        assert evaluate('trim("  hello  ")', {}) == "hello"

    def test_upper(self):
        assert evaluate('upper("hello")', {}) == "HELLO"

    def test_lower(self):
        assert evaluate('lower("HELLO")', {}) == "hello"

    def test_matches(self):
        record = {"email": "test@example.com"}
        assert evaluate('matches(email, ".*@example\\.com$")', record) is True
        assert evaluate('matches(email, ".*@other\\.com$")', record) is False

    def test_startsWith(self):
        record = {"sku": "PRD-12345"}
        assert evaluate('startsWith(sku, "PRD-")', record) is True
        assert evaluate('startsWith(sku, "INV-")', record) is False

    def test_endsWith(self):
        record = {"email": "user@company.com"}
        assert evaluate('endsWith(email, "@company.com")', record) is True


class TestDateFunctions:
    """Tests for date functions."""

    def test_now_returns_datetime(self):
        result = evaluate("now()", {})
        assert isinstance(result, datetime)

    def test_today_returns_date(self):
        result = evaluate("today()", {})
        assert isinstance(result, date)

    def test_daysBetween(self):
        record = {
            "start": date(2024, 1, 1),
            "end": date(2024, 1, 31),
        }
        assert evaluate("daysBetween(start, end)", record) == 30

    def test_daysBetween_with_null(self):
        record = {"start": date(2024, 1, 1), "end": None}
        assert evaluate("daysBetween(start, end)", record) is None

    def test_addDays(self):
        record = {"d": date(2024, 1, 15)}
        result = evaluate("addDays(d, 10)", record)
        assert result == date(2024, 1, 25)

    def test_addDays_negative(self):
        record = {"d": date(2024, 1, 15)}
        result = evaluate("addDays(d, -10)", record)
        assert result == date(2024, 1, 5)

    def test_year(self):
        record = {"d": date(2024, 6, 15)}
        assert evaluate("year(d)", record) == 2024

    def test_month(self):
        record = {"d": date(2024, 6, 15)}
        assert evaluate("month(d)", record) == 6

    def test_day(self):
        record = {"d": date(2024, 6, 15)}
        assert evaluate("day(d)", record) == 15


class TestMathFunctions:
    """Tests for math functions."""

    def test_abs(self):
        assert evaluate("abs(-5)", {}) == 5
        assert evaluate("abs(5)", {}) == 5

    def test_round(self):
        assert evaluate("round(3.7)", {}) == 4
        assert evaluate("round(3.14159, 2)", {}) == pytest.approx(3.14)

    def test_floor(self):
        assert evaluate("floor(3.7)", {}) == 3
        assert evaluate("floor(3.2)", {}) == 3

    def test_ceil(self):
        assert evaluate("ceil(3.2)", {}) == 4
        assert evaluate("ceil(3.7)", {}) == 4

    def test_min(self):
        assert evaluate("min(5, 3, 8, 1)", {}) == 1

    def test_max(self):
        assert evaluate("max(5, 3, 8, 1)", {}) == 8


class TestCollectionFunctions:
    """Tests for collection functions."""

    def test_contains_array(self):
        record = {"tags": ["urgent", "important"]}
        assert evaluate('contains(tags, "urgent")', record) is True
        assert evaluate('contains(tags, "normal")', record) is False

    def test_contains_string(self):
        record = {"email": "test@example.com"}
        assert evaluate('contains(email, "@")', record) is True

    def test_size(self):
        record = {"items": [1, 2, 3]}
        assert evaluate("size(items)", record) == 3

    def test_first(self):
        record = {"items": ["a", "b", "c"]}
        assert evaluate("first(items)", record) == "a"

    def test_last(self):
        record = {"items": ["a", "b", "c"]}
        assert evaluate("last(items)", record) == "c"


class TestLogicFunctions:
    """Tests for logic functions."""

    def test_coalesce(self):
        record = {"a": None, "b": None, "c": "value"}
        assert evaluate("coalesce(a, b, c)", record) == "value"

    def test_coalesce_all_null(self):
        record = {"a": None, "b": None}
        assert evaluate("coalesce(a, b)", record) is None

    def test_if_true(self):
        record = {"premium": True}
        assert evaluate('if(premium, "gold", "standard")', record) == "gold"

    def test_if_false(self):
        record = {"premium": False}
        assert evaluate('if(premium, "gold", "standard")', record) == "standard"


# =============================================================================
# Integration Tests
# =============================================================================


class TestExpressionIntegration:
    """Integration tests for complex expression scenarios."""

    def test_validation_rule_date_range(self):
        """Test a typical date range validation expression."""
        record = {
            "effectiveDate": date(2024, 1, 1),
            "expirationDate": date(2024, 12, 31),
        }
        expr = "expirationDate > effectiveDate"
        assert evaluate_bool(expr, record) is True

    def test_validation_rule_conditional_required(self):
        """Test a conditional required field validation."""
        record = {"status": "approved", "approvedBy": "admin"}
        expr = 'status != "approved" || !isEmpty(approvedBy)'
        assert evaluate_bool(expr, record) is True

        record_invalid = {"status": "approved", "approvedBy": None}
        assert evaluate_bool(expr, record_invalid) is False

    def test_validation_rule_status_transition(self):
        """Test a status transition validation."""
        record = {"status": "active"}
        original = {"status": "terminated"}

        # Can't go from terminated back to active
        expr = 'status != "active" || original.status != "terminated"'
        assert evaluate_bool(expr, record, original) is False

    def test_defaulting_expression(self):
        """Test a defaulting expression for computed fields."""
        record = {"firstName": "John", "lastName": "Doe"}
        expr = 'concat(firstName, " ", lastName)'
        assert evaluate(expr, record) == "John Doe"

    def test_complex_business_rule(self):
        """Test a complex business rule expression."""
        record = {
            "orderTotal": 1500,
            "customerTier": "gold",
            "discountPercent": 15,
        }

        # Gold customers can have up to 20% discount, others up to 10%
        expr = '''
            (customerTier == "gold" && discountPercent <= 20) ||
            (customerTier != "gold" && discountPercent <= 10)
        '''
        assert evaluate_bool(expr, record) is True

        # Platinum customer with 15% discount should fail under "others" rule
        record["customerTier"] = "silver"
        assert evaluate_bool(expr, record) is False
