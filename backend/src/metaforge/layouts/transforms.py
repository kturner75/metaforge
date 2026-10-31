"""Declarative, bidirectional transforms for file-layout mappings (MF-020).

Each transform knows how to go **both ways**:

- ``apply``  — read direction: a raw cell string → an intermediate value that is
  then coerced into the entity field's type.
- ``invert`` — write direction: a rendered field value → the cell string that
  belongs in the file.

Read pipeline:  ``raw_str → t1.apply → t2.apply → … → coerce``
Write pipeline: ``render → … → t2.invert → t1.invert → cell_str`` (reverse order)

Transforms that cannot be perfectly reversed (``trim``, ``upper``/``lower``)
invert as the identity and are documented as lossy. For richer cases a mapping
may instead use the ``expression`` / ``writeExpression`` escape hatch (handled by
the reader/writer, not here).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from metaforge.layouts.types import TransformError, TransformStep

# A transform callable takes (value, params) and returns the transformed value.
TransformFn = Callable[[Any, dict[str, Any]], Any]


@dataclass
class TransformSpec:
    """Registry entry: the two directions plus documentation metadata."""

    name: str
    description: str
    apply: TransformFn  # read direction
    invert: TransformFn  # write direction
    invertible: bool = True  # False when invert is lossy / identity
    params: list[dict[str, str]] = field(default_factory=list)


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


# ---------------------------------------------------------------------------
# trim
# ---------------------------------------------------------------------------


def _trim_apply(value: Any, params: dict[str, Any]) -> Any:
    chars = params.get("chars")
    s = _as_str(value)
    side = params.get("side", "both")
    if side == "left":
        return s.lstrip(chars)
    if side == "right":
        return s.rstrip(chars)
    return s.strip(chars)


def _identity(value: Any, params: dict[str, Any]) -> Any:
    return value


# ---------------------------------------------------------------------------
# pad (mainly for fixed-width writing)
# ---------------------------------------------------------------------------


def _pad_apply(value: Any, params: dict[str, Any]) -> Any:
    """Read: strip the pad character from the padded side."""
    s = _as_str(value)
    char = params.get("char", " ")
    side = params.get("side", "right")
    return s.lstrip(char) if side == "left" else s.rstrip(char)


def _pad_invert(value: Any, params: dict[str, Any]) -> Any:
    """Write: pad to ``width`` with ``char`` on ``side``."""
    s = _as_str(value)
    width = params.get("width")
    if width is None:
        raise TransformError("pad transform requires a 'width' parameter")
    char = params.get("char", " ")
    if len(char) != 1:
        raise TransformError("pad 'char' must be a single character")
    side = params.get("side", "right")
    if side == "left":
        return s.rjust(width, char)
    return s.ljust(width, char)


# ---------------------------------------------------------------------------
# dateFormat
# ---------------------------------------------------------------------------


def _date_apply(value: Any, params: dict[str, Any]) -> Any:
    """Read: parse using ``from`` and emit an ISO (date or datetime) string."""
    s = _as_str(value).strip()
    if s == "":
        return s
    fmt = params.get("from")
    if not fmt:
        raise TransformError("dateFormat transform requires a 'from' parameter")
    try:
        parsed = datetime.strptime(s, fmt)
    except ValueError as exc:
        raise TransformError(f"value {s!r} does not match date format {fmt!r}") from exc
    # Date-only formats carry no time component.
    if (
        parsed.hour == 0
        and parsed.minute == 0
        and parsed.second == 0
        and ("%H" not in fmt and "%I" not in fmt)
    ):
        return parsed.date().isoformat()
    return parsed.isoformat()


def _date_invert(value: Any, params: dict[str, Any]) -> Any:
    """Write: render an ISO date/datetime using ``to`` (defaults to ``from``)."""
    s = _as_str(value).strip()
    if s == "":
        return s
    fmt = params.get("to") or params.get("from")
    if not fmt:
        raise TransformError("dateFormat transform requires a 'from' or 'to' parameter")
    try:
        parsed = datetime.fromisoformat(s)
    except ValueError as exc:
        raise TransformError(f"value {s!r} is not an ISO date/datetime") from exc
    return parsed.strftime(fmt)


# ---------------------------------------------------------------------------
# impliedDecimals
# ---------------------------------------------------------------------------


def _implied_apply(value: Any, params: dict[str, Any]) -> Any:
    """Read: ``"12345"`` with places=2 → ``123.45``."""
    s = _as_str(value).strip()
    if s == "":
        return s
    places = int(params.get("places", 2))
    negative = s.startswith("-")
    digits = s[1:] if negative else s
    if not digits.isdigit():
        raise TransformError(f"impliedDecimals expects digits, got {s!r}")
    scaled = int(digits) / (10**places)
    return -scaled if negative else scaled


def _implied_invert(value: Any, params: dict[str, Any]) -> Any:
    """Write: ``123.45`` with places=2 → ``"12345"``."""
    s = _as_str(value).strip()
    if s == "":
        return s
    places = int(params.get("places", 2))
    try:
        number = float(s)
    except ValueError as exc:
        raise TransformError(f"impliedDecimals cannot render {s!r} as a number") from exc
    scaled = round(number * (10**places))
    sign = "-" if scaled < 0 else ""
    return f"{sign}{abs(scaled)}"


# ---------------------------------------------------------------------------
# lookup (code <-> value map)
# ---------------------------------------------------------------------------


def _lookup_apply(value: Any, params: dict[str, Any]) -> Any:
    table: dict[str, Any] = params.get("map", {})
    key = _as_str(value)
    if key in table:
        return table[key]
    if "default" in params:
        return params["default"]
    if params.get("strict", True):
        raise TransformError(f"lookup has no entry for code {key!r}")
    return value


def _lookup_match_key(value: Any) -> Any:
    """Normalize a value for tolerant reverse-lookup comparison.

    Codes map to typed values (``{Y: true}``, ``{"1": 100}``), but by write time
    the field value has been coerced and rendered, so ``True`` arrives as ``1``
    or ``"1"``. Collapse booleans, numbers and their string forms to a common
    key so a typed ``lookup`` still round-trips.
    """
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip()
    low = token.lower()
    if low == "true":
        return 1.0
    if low == "false":
        return 0.0
    try:
        return float(token)
    except ValueError:
        return token


def _lookup_invert(value: Any, params: dict[str, Any]) -> Any:
    table: dict[str, Any] = params.get("map", {})
    # Reverse the map: value -> code. First matching code wins.
    for code, mapped in table.items():
        if mapped == value:
            return code
    # Fall back to a type-tolerant match (handles coerced/rendered values).
    target = _lookup_match_key(value)
    for code, mapped in table.items():
        if _lookup_match_key(mapped) == target:
            return code
    if "writeDefault" in params:
        return params["writeDefault"]
    if params.get("strict", True):
        raise TransformError(f"lookup has no code for value {value!r}")
    return _as_str(value)


# ---------------------------------------------------------------------------
# replace / default / number
# ---------------------------------------------------------------------------


def _replace_apply(value: Any, params: dict[str, Any]) -> Any:
    return _as_str(value).replace(params.get("from", ""), params.get("to", ""))


def _replace_invert(value: Any, params: dict[str, Any]) -> Any:
    # Reverse the substitution for write.
    return _as_str(value).replace(params.get("to", ""), params.get("from", ""))


def _default_apply(value: Any, params: dict[str, Any]) -> Any:
    s = _as_str(value)
    return params.get("value", "") if s.strip() == "" else value


def _number_apply(value: Any, params: dict[str, Any]) -> Any:
    """Strip thousands separators and currency symbols → bare numeric string."""
    s = _as_str(value).strip()
    for sym in params.get("strip", [",", "$", "€", "£", " "]):
        s = s.replace(sym, "")
    return s


def _number_invert(value: Any, params: dict[str, Any]) -> Any:
    return _as_str(value)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TRANSFORMS: dict[str, TransformSpec] = {
    "trim": TransformSpec(
        name="trim",
        description="Strip whitespace (or given chars) from one or both sides.",
        apply=_trim_apply,
        invert=_identity,
        invertible=False,
        params=[
            {
                "name": "chars",
                "type": "string",
                "description": "Characters to strip (default whitespace)",
            },
            {"name": "side", "type": "string", "description": "left | right | both (default both)"},
        ],
    ),
    "pad": TransformSpec(
        name="pad",
        description="Pad a value to a fixed width (write); strip padding (read).",
        apply=_pad_apply,
        invert=_pad_invert,
        params=[
            {"name": "width", "type": "number", "description": "Target width (required)"},
            {"name": "char", "type": "string", "description": "Pad character (default space)"},
            {"name": "side", "type": "string", "description": "left | right (default right)"},
        ],
    ),
    "upper": TransformSpec(
        name="upper",
        description="Uppercase the value.",
        apply=lambda v, p: _as_str(v).upper(),
        invert=_identity,
        invertible=False,
    ),
    "lower": TransformSpec(
        name="lower",
        description="Lowercase the value.",
        apply=lambda v, p: _as_str(v).lower(),
        invert=_identity,
        invertible=False,
    ),
    "dateFormat": TransformSpec(
        name="dateFormat",
        description="Parse dates with a strptime pattern (read) and render them back (write).",
        apply=_date_apply,
        invert=_date_invert,
        params=[
            {"name": "from", "type": "string", "description": "strptime pattern of the file value"},
            {
                "name": "to",
                "type": "string",
                "description": "strftime pattern for writing (default: from)",
            },
        ],
    ),
    "impliedDecimals": TransformSpec(
        name="impliedDecimals",
        description="Interpret an integer string as a decimal with N implied places.",
        apply=_implied_apply,
        invert=_implied_invert,
        params=[
            {
                "name": "places",
                "type": "number",
                "description": "Number of implied decimal places (default 2)",
            }
        ],
    ),
    "lookup": TransformSpec(
        name="lookup",
        description="Translate codes to values via a map (read) and back (write).",
        apply=_lookup_apply,
        invert=_lookup_invert,
        params=[
            {"name": "map", "type": "object", "description": "code -> value mapping"},
            {
                "name": "default",
                "type": "any",
                "description": "value when a code is missing (read)",
            },
            {
                "name": "strict",
                "type": "boolean",
                "description": "error on missing code (default true)",
            },
        ],
    ),
    "replace": TransformSpec(
        name="replace",
        description="Substring replacement, reversed on write.",
        apply=_replace_apply,
        invert=_replace_invert,
        params=[
            {"name": "from", "type": "string", "description": "substring to find"},
            {"name": "to", "type": "string", "description": "replacement"},
        ],
    ),
    "default": TransformSpec(
        name="default",
        description="Substitute a value when the cell is empty.",
        apply=_default_apply,
        invert=_identity,
        invertible=False,
        params=[{"name": "value", "type": "any", "description": "value to use when empty"}],
    ),
    "number": TransformSpec(
        name="number",
        description="Strip thousands separators and symbols to a bare numeric string.",
        apply=_number_apply,
        invert=_number_invert,
        params=[{"name": "strip", "type": "array", "description": "symbols to remove"}],
    ),
}


def ensure_expression_functions() -> None:
    """Make sure the expression-DSL builtins are registered.

    The app registers them at startup; this lazy guard lets the layout engine's
    ``expression`` / ``writeExpression`` escape hatch work standalone and in
    tests. Idempotent and cheap once registered.
    """
    from metaforge.validation.expressions import FunctionRegistry

    if not FunctionRegistry.is_registered("trim"):
        from metaforge.validation.expressions.builtins import register_all_builtins

        register_all_builtins()


def is_known_transform(name: str) -> bool:
    return name in TRANSFORMS


def get_transform(name: str) -> TransformSpec:
    spec = TRANSFORMS.get(name)
    if spec is None:
        raise TransformError(f"Unknown transform: {name!r}")
    return spec


def apply_transforms(steps: list[TransformStep], value: Any) -> Any:
    """Run the read-direction pipeline (in order)."""
    for step in steps:
        value = get_transform(step.name).apply(value, step.params)
    return value


def invert_transforms(steps: list[TransformStep], value: Any) -> Any:
    """Run the write-direction pipeline (reverse order)."""
    for step in reversed(steps):
        value = get_transform(step.name).invert(value, step.params)
    return value


def export_documentation() -> list[dict[str, Any]]:
    """Export the transform catalog (for docs / future API surface)."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "invertible": spec.invertible,
            "params": spec.params,
        }
        for spec in TRANSFORMS.values()
    ]
