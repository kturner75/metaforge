"""Built-in functions for the MetaForge expression DSL.

This module registers all built-in functions with the FunctionRegistry.
Import this module at application startup to register functions.

Categories:
- String: len, isEmpty, concat, trim, upper, lower, matches
- Date: now, today, daysBetween, addDays, format
- Math: abs, round, floor, ceil, min, max
- Collection: contains, size, first, last
- Logic: coalesce, if
- Query: exists, count (server-only, no implementation here)
"""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from metaforge.validation.expressions.functions import (
    FunctionCategory,
    FunctionDefinition,
    FunctionParameter,
    FunctionRegistry,
)


def register_all_builtins() -> None:
    """Register all built-in functions with the FunctionRegistry."""
    _register_string_functions()
    _register_date_functions()
    _register_math_functions()
    _register_collection_functions()
    _register_logic_functions()
    _register_query_functions()


# -----------------------------------------------------------------------------
# String Functions
# -----------------------------------------------------------------------------


def _len(value: Any) -> int:
    """Return length of string or array, 0 for None."""
    if value is None:
        return 0
    if isinstance(value, (str, list, tuple)):
        return len(value)
    return 0


def _is_empty(value: Any) -> bool:
    """Return True if value is None, empty string, or empty array."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def _concat(*args: Any) -> str:
    """Concatenate all arguments as strings, skipping None values."""
    return "".join(str(a) for a in args if a is not None)


def _trim(value: str | None) -> str:
    """Trim whitespace from both ends of a string."""
    if value is None:
        return ""
    return str(value).strip()


def _upper(value: str | None) -> str:
    """Convert string to uppercase."""
    if value is None:
        return ""
    return str(value).upper()


def _lower(value: str | None) -> str:
    """Convert string to lowercase."""
    if value is None:
        return ""
    return str(value).lower()


def _matches(value: str | None, pattern: str) -> bool:
    """Test if string matches regex pattern."""
    if value is None:
        return False
    try:
        return bool(re.match(pattern, str(value)))
    except re.error:
        return False


def _starts_with(value: str | None, prefix: str) -> bool:
    """Test if string starts with prefix."""
    if value is None:
        return False
    return str(value).startswith(prefix)


def _ends_with(value: str | None, suffix: str) -> bool:
    """Test if string ends with suffix."""
    if value is None:
        return False
    return str(value).endswith(suffix)


def _register_string_functions() -> None:
    FunctionRegistry.register(
        FunctionDefinition(
            name="len",
            description="Returns length of string or array",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "string|array", "The value to measure")
            ],
            return_type="number",
            client_evaluable=True,
            examples=[
                'len(description) <= 500',
                'len(tags) >= 1',
            ],
            implementation=_len,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="isEmpty",
            description="Returns true if value is null, empty string, or empty array",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "any", "The value to check")
            ],
            return_type="boolean",
            client_evaluable=True,
            examples=[
                'isEmpty(middleName)',
                '!isEmpty(approvedBy) || status == "draft"',
            ],
            implementation=_is_empty,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="concat",
            description="Concatenates all arguments as strings",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter(
                    "values", "string", "Strings to concatenate", variadic=True
                )
            ],
            return_type="string",
            client_evaluable=True,
            examples=[
                'concat(firstName, " ", lastName)',
                'concat(city, ", ", state, " ", zip)',
            ],
            implementation=_concat,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="trim",
            description="Removes whitespace from both ends of a string",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "string", "The string to trim")
            ],
            return_type="string",
            client_evaluable=True,
            examples=['trim(name) != ""'],
            implementation=_trim,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="upper",
            description="Converts string to uppercase",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "string", "The string to convert")
            ],
            return_type="string",
            client_evaluable=True,
            examples=['upper(countryCode) == "US"'],
            implementation=_upper,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="lower",
            description="Converts string to lowercase",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "string", "The string to convert")
            ],
            return_type="string",
            client_evaluable=True,
            examples=['lower(email)'],
            implementation=_lower,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="matches",
            description="Tests if string matches regex pattern",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "string", "The string to test"),
                FunctionParameter("pattern", "string", "Regex pattern"),
            ],
            return_type="boolean",
            client_evaluable=True,
            examples=[
                'matches(sku, "^[A-Z]{3}-[0-9]{4}$")',
                'matches(email, ".*@company\\.com$")',
            ],
            implementation=_matches,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="startsWith",
            description="Tests if string starts with prefix",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "string", "The string to test"),
                FunctionParameter("prefix", "string", "Prefix to check for"),
            ],
            return_type="boolean",
            client_evaluable=True,
            examples=['startsWith(sku, "PRD-")'],
            implementation=_starts_with,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="endsWith",
            description="Tests if string ends with suffix",
            category=FunctionCategory.STRING,
            parameters=[
                FunctionParameter("value", "string", "The string to test"),
                FunctionParameter("suffix", "string", "Suffix to check for"),
            ],
            return_type="boolean",
            client_evaluable=True,
            examples=['endsWith(email, "@company.com")'],
            implementation=_ends_with,
        )
    )


# -----------------------------------------------------------------------------
# Date Functions
# -----------------------------------------------------------------------------


def _now() -> datetime:
    """Return current datetime in UTC."""
    return datetime.now(timezone.utc)


def _today() -> date:
    """Return current date."""
    return date.today()


def _days_between(start: date | datetime | None, end: date | datetime | None) -> int | None:
    """Return number of days between two dates."""
    if start is None or end is None:
        return None

    # Convert datetime to date if needed
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()

    return (end - start).days


def _add_days(d: date | datetime | None, days: int) -> date | datetime | None:
    """Add days to a date."""
    if d is None:
        return None
    return d + timedelta(days=days)


def _year(d: date | datetime | None) -> int | None:
    """Extract year from date."""
    if d is None:
        return None
    return d.year


def _month(d: date | datetime | None) -> int | None:
    """Extract month from date (1-12)."""
    if d is None:
        return None
    return d.month


def _day(d: date | datetime | None) -> int | None:
    """Extract day of month from date (1-31)."""
    if d is None:
        return None
    return d.day


def _register_date_functions() -> None:
    FunctionRegistry.register(
        FunctionDefinition(
            name="now",
            description="Returns current datetime in UTC",
            category=FunctionCategory.DATE,
            parameters=[],
            return_type="datetime",
            client_evaluable=True,
            examples=[
                'expirationDate > now()',
                'daysBetween(createdAt, now()) <= 30',
            ],
            implementation=_now,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="today",
            description="Returns current date (no time component)",
            category=FunctionCategory.DATE,
            parameters=[],
            return_type="date",
            client_evaluable=True,
            examples=['effectiveDate >= today()'],
            implementation=_today,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="daysBetween",
            description="Returns number of days between two dates",
            category=FunctionCategory.DATE,
            parameters=[
                FunctionParameter("start", "date", "Start date"),
                FunctionParameter("end", "date", "End date"),
            ],
            return_type="number",
            client_evaluable=True,
            examples=[
                'daysBetween(effectiveDate, expirationDate) >= 30',
                'daysBetween(lastContactDate, now()) <= 90',
            ],
            implementation=_days_between,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="addDays",
            description="Adds days to a date (negative to subtract)",
            category=FunctionCategory.DATE,
            parameters=[
                FunctionParameter("date", "date", "The date"),
                FunctionParameter("days", "number", "Days to add"),
            ],
            return_type="date",
            client_evaluable=True,
            examples=[
                'expirationDate >= addDays(today(), 30)',
                'reminderDate == addDays(dueDate, -7)',
            ],
            implementation=_add_days,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="year",
            description="Extracts year from date",
            category=FunctionCategory.DATE,
            parameters=[
                FunctionParameter("date", "date", "The date")
            ],
            return_type="number",
            client_evaluable=True,
            examples=['year(contractDate) == year(now())'],
            implementation=_year,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="month",
            description="Extracts month from date (1-12)",
            category=FunctionCategory.DATE,
            parameters=[
                FunctionParameter("date", "date", "The date")
            ],
            return_type="number",
            client_evaluable=True,
            examples=['month(createdAt) == 12'],
            implementation=_month,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="day",
            description="Extracts day of month from date (1-31)",
            category=FunctionCategory.DATE,
            parameters=[
                FunctionParameter("date", "date", "The date")
            ],
            return_type="number",
            client_evaluable=True,
            examples=['day(dueDate) <= 15'],
            implementation=_day,
        )
    )


# -----------------------------------------------------------------------------
# Math Functions
# -----------------------------------------------------------------------------


def _abs(value: int | float | Decimal | None) -> int | float | Decimal | None:
    """Return absolute value."""
    if value is None:
        return None
    return abs(value)


def _round_num(value: float | Decimal | None, decimals: int = 0) -> float | Decimal | None:
    """Round to specified decimal places."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP)
    return round(value, decimals)


def _floor(value: float | None) -> int | None:
    """Round down to nearest integer."""
    if value is None:
        return None
    import math
    return math.floor(value)


def _ceil(value: float | None) -> int | None:
    """Round up to nearest integer."""
    if value is None:
        return None
    import math
    return math.ceil(value)


def _min_val(*args: Any) -> Any:
    """Return minimum value, ignoring None."""
    values = [a for a in args if a is not None]
    if not values:
        return None
    return min(values)


def _max_val(*args: Any) -> Any:
    """Return maximum value, ignoring None."""
    values = [a for a in args if a is not None]
    if not values:
        return None
    return max(values)


def _register_math_functions() -> None:
    FunctionRegistry.register(
        FunctionDefinition(
            name="abs",
            description="Returns absolute value",
            category=FunctionCategory.MATH,
            parameters=[
                FunctionParameter("value", "number", "The number")
            ],
            return_type="number",
            client_evaluable=True,
            examples=['abs(balance) < 1000'],
            implementation=_abs,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="round",
            description="Rounds to specified decimal places",
            category=FunctionCategory.MATH,
            parameters=[
                FunctionParameter("value", "number", "The number"),
                FunctionParameter(
                    "decimals", "number", "Decimal places", required=False, default=0
                ),
            ],
            return_type="number",
            client_evaluable=True,
            examples=[
                'round(total, 2) == total',
                'round(percentage) <= 100',
            ],
            implementation=_round_num,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="floor",
            description="Rounds down to nearest integer",
            category=FunctionCategory.MATH,
            parameters=[
                FunctionParameter("value", "number", "The number")
            ],
            return_type="number",
            client_evaluable=True,
            examples=['floor(rating) >= 3'],
            implementation=_floor,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="ceil",
            description="Rounds up to nearest integer",
            category=FunctionCategory.MATH,
            parameters=[
                FunctionParameter("value", "number", "The number")
            ],
            return_type="number",
            client_evaluable=True,
            examples=['ceil(quantity) <= maxQuantity'],
            implementation=_ceil,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="min",
            description="Returns minimum value",
            category=FunctionCategory.MATH,
            parameters=[
                FunctionParameter("values", "number", "Numbers to compare", variadic=True)
            ],
            return_type="number",
            client_evaluable=True,
            examples=['min(price, maxPrice) == price'],
            implementation=_min_val,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="max",
            description="Returns maximum value",
            category=FunctionCategory.MATH,
            parameters=[
                FunctionParameter("values", "number", "Numbers to compare", variadic=True)
            ],
            return_type="number",
            client_evaluable=True,
            examples=['max(minQuantity, 1) <= quantity'],
            implementation=_max_val,
        )
    )


# -----------------------------------------------------------------------------
# Collection Functions
# -----------------------------------------------------------------------------


def _contains(collection: list | str | None, item: Any) -> bool:
    """Check if collection contains item."""
    if collection is None:
        return False
    return item in collection


def _size(collection: list | tuple | dict | None) -> int:
    """Return size of collection."""
    if collection is None:
        return 0
    return len(collection)


def _first(collection: list | tuple | None) -> Any:
    """Return first element of collection."""
    if collection is None or len(collection) == 0:
        return None
    return collection[0]


def _last(collection: list | tuple | None) -> Any:
    """Return last element of collection."""
    if collection is None or len(collection) == 0:
        return None
    return collection[-1]


def _register_collection_functions() -> None:
    FunctionRegistry.register(
        FunctionDefinition(
            name="contains",
            description="Checks if collection contains item",
            category=FunctionCategory.COLLECTION,
            parameters=[
                FunctionParameter("collection", "array|string", "The collection"),
                FunctionParameter("item", "any", "Item to find"),
            ],
            return_type="boolean",
            client_evaluable=True,
            examples=[
                'contains(tags, "urgent")',
                'contains(email, "@")',
            ],
            implementation=_contains,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="size",
            description="Returns size of collection",
            category=FunctionCategory.COLLECTION,
            parameters=[
                FunctionParameter("collection", "array|object", "The collection")
            ],
            return_type="number",
            client_evaluable=True,
            examples=['size(lineItems) > 0'],
            implementation=_size,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="first",
            description="Returns first element of collection",
            category=FunctionCategory.COLLECTION,
            parameters=[
                FunctionParameter("collection", "array", "The collection")
            ],
            return_type="any",
            client_evaluable=True,
            examples=['first(sortedItems)'],
            implementation=_first,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="last",
            description="Returns last element of collection",
            category=FunctionCategory.COLLECTION,
            parameters=[
                FunctionParameter("collection", "array", "The collection")
            ],
            return_type="any",
            client_evaluable=True,
            examples=['last(sortedItems)'],
            implementation=_last,
        )
    )


# -----------------------------------------------------------------------------
# Logic Functions
# -----------------------------------------------------------------------------


def _coalesce(*args: Any) -> Any:
    """Return first non-null value."""
    for arg in args:
        if arg is not None:
            return arg
    return None


def _if_then(condition: bool, true_value: Any, false_value: Any = None) -> Any:
    """Return true_value if condition is true, else false_value."""
    return true_value if condition else false_value


def _register_logic_functions() -> None:
    FunctionRegistry.register(
        FunctionDefinition(
            name="coalesce",
            description="Returns first non-null value",
            category=FunctionCategory.LOGIC,
            parameters=[
                FunctionParameter("values", "any", "Values to check", variadic=True)
            ],
            return_type="any",
            client_evaluable=True,
            examples=[
                'coalesce(nickname, firstName, "Unknown")',
                'coalesce(overridePrice, standardPrice)',
            ],
            implementation=_coalesce,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="if",
            description="Returns true_value if condition is true, else false_value",
            category=FunctionCategory.LOGIC,
            parameters=[
                FunctionParameter("condition", "boolean", "The condition"),
                FunctionParameter("trueValue", "any", "Value if true"),
                FunctionParameter(
                    "falseValue", "any", "Value if false", required=False, default=None
                ),
            ],
            return_type="any",
            client_evaluable=True,
            examples=[
                'if(quantity > 100, "bulk", "standard")',
                'if(isPremium, discountedPrice, regularPrice)',
            ],
            implementation=_if_then,
        )
    )


# -----------------------------------------------------------------------------
# Query Functions (Server-only, no implementation)
# -----------------------------------------------------------------------------


def _register_query_functions() -> None:
    """Register query functions. These have no implementation as they require
    a QueryService context to be injected at evaluation time."""

    FunctionRegistry.register(
        FunctionDefinition(
            name="exists",
            description="Returns true if any record matches the filter",
            category=FunctionCategory.QUERY,
            parameters=[
                FunctionParameter("entity", "string", "Entity to query"),
                FunctionParameter("filter", "object", "Filter criteria"),
            ],
            return_type="boolean",
            client_evaluable=False,
            examples=[
                'exists("Contract", {"parentId": id, "status": "active"})',
                '!exists("Order", {"customerId": id, "status": "pending"})',
            ],
            implementation=None,  # Injected at runtime
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="count",
            description="Returns count of records matching filter",
            category=FunctionCategory.QUERY,
            parameters=[
                FunctionParameter("entity", "string", "Entity to query"),
                FunctionParameter("filter", "object", "Filter criteria"),
            ],
            return_type="number",
            client_evaluable=False,
            examples=[
                'count("LineItem", {"orderId": id}) <= 100',
                'count("Contact", {"companyId": id}) > 0',
            ],
            implementation=None,
        )
    )

    FunctionRegistry.register(
        FunctionDefinition(
            name="lookup",
            description="Looks up a value from a related record",
            category=FunctionCategory.QUERY,
            parameters=[
                FunctionParameter("entity", "string", "Entity to query"),
                FunctionParameter("field", "string", "Field to return"),
                FunctionParameter("filter", "object", "Filter to find record"),
            ],
            return_type="any",
            client_evaluable=False,
            examples=[
                'lookup("Customer", "creditLimit", {"id": customerId})',
                'lookup("Product", "price", {"sku": productSku})',
            ],
            implementation=None,
        )
    )
