"""Coerce raw cell values to/from entity field types (MF-020).

The reader hands a (possibly transform-processed) value to :func:`coerce`, which
turns it into the Python value appropriate for the entity field's type. The
writer calls :func:`render` to turn a typed value back into a string for the
file. Both fail loudly with :class:`CoercionError` so the reader can attach the
cell's location.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from metaforge.core.types import get_field_type
from metaforge.layouts.types import CoercionError

# Field types whose storage is plain TEXT and that pass through as strings.
_NUMERIC_TYPES = {"number", "currency", "percent"}
_BOOL_TYPES = {"checkbox", "boolean"}

_TRUE_STRINGS = {"1", "true", "t", "yes", "y", "on"}
_FALSE_STRINGS = {"0", "false", "f", "no", "n", "off", ""}


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def coerce(value: Any, field_type: str, field_name: str) -> Any:
    """Coerce ``value`` into ``field_type``'s Python representation.

    An empty cell becomes ``None``. Raises :class:`CoercionError` when the value
    cannot be represented as the target type.
    """
    if _is_empty(value):
        return None

    if field_type in _NUMERIC_TYPES:
        if isinstance(value, bool):  # guard: bool is an int subclass
            raise CoercionError(
                "expected a number, got boolean",
                field=field_name,
                value=value,
                target_type=field_type,
            )
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except ValueError as exc:
            raise CoercionError(
                f"value {value!r} is not a valid number",
                field=field_name,
                value=value,
                target_type=field_type,
            ) from exc

    if field_type in _BOOL_TYPES:
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            return 1 if value != 0 else 0
        token = str(value).strip().lower()
        if token in _TRUE_STRINGS:
            return 1
        if token in _FALSE_STRINGS:
            return 0
        raise CoercionError(
            f"value {value!r} is not a valid boolean",
            field=field_name,
            value=value,
            target_type=field_type,
        )

    if field_type == "date":
        return _coerce_date(value, field_name, with_time=False)

    if field_type == "datetime":
        return _coerce_date(value, field_name, with_time=True)

    # All remaining types store as TEXT.
    return str(value)


def _coerce_date(value: Any, field_name: str, *, with_time: bool) -> str:
    if isinstance(value, datetime):
        return value.isoformat() if with_time else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    token = str(value).strip()
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError as exc:
        kind = "datetime" if with_time else "date"
        raise CoercionError(
            f"value {value!r} is not an ISO {kind}",
            field=field_name,
            value=value,
            target_type=kind,
        ) from exc
    return parsed.isoformat() if with_time else parsed.date().isoformat()


def render(value: Any, field_type: str, field_name: str) -> str:
    """Render a typed field value into a string for writing to a file."""
    if value is None:
        return ""

    if field_type in _NUMERIC_TYPES:
        if isinstance(value, bool):
            raise CoercionError(
                "cannot render boolean as a number",
                field=field_name,
                value=value,
                target_type=field_type,
            )
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return str(int(value)) if value.is_integer() else repr(value)
        return str(value)

    if field_type in _BOOL_TYPES:
        if isinstance(value, str):
            token = value.strip().lower()
            if token in _TRUE_STRINGS:
                return "1"
            if token in _FALSE_STRINGS:
                return "0"
            raise CoercionError(
                f"value {value!r} is not a valid boolean",
                field=field_name,
                value=value,
                target_type=field_type,
            )
        return "1" if value else "0"

    return str(value)


def coercion_target(field_type: str) -> str:
    """Report the coercion family for a field type (for docs/introspection)."""
    if field_type in _NUMERIC_TYPES:
        return "number"
    if field_type in _BOOL_TYPES:
        return "boolean"
    if field_type in ("date", "datetime"):
        return field_type
    # Fall back to the registry's storage hint for unknown types.
    get_field_type(field_type)  # validates it resolves (defaults to string)
    return "string"
