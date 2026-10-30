"""Core data types for the MetaForge file-layout system (MF-020).

A *file layout* describes how a flat file (delimited or fixed-width) maps to and
from entity values. These dataclasses are the parsed, in-memory form of a
``metadata/layouts/*.yaml`` definition, plus the provenance and error types the
reader/writer produce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LayoutError(Exception):
    """Base class for all file-layout errors."""


class LayoutConfigError(LayoutError):
    """The layout definition itself is invalid (bad YAML shape or references)."""


class TransformError(LayoutError):
    """A transform could not be applied (or inverted) to a value."""


class CoercionError(LayoutError):
    """A raw value could not be coerced into (or rendered from) a field type."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        target_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.value = value
        self.target_type = target_type


@dataclass
class ReadIssue:
    """A single problem found while reading a file.

    Carries enough location detail to point a human (or a provenance-aware
    caller) straight at the offending cell.
    """

    message: str
    row: int | None = None
    field: str | None = None
    column: str | int | None = None
    byte_offset: int | None = None
    raw: str | None = None

    def __str__(self) -> str:
        loc_parts = []
        if self.row is not None:
            loc_parts.append(f"row {self.row}")
        if self.field is not None:
            loc_parts.append(f"field '{self.field}'")
        if self.column is not None:
            loc_parts.append(f"column {self.column!r}")
        if self.byte_offset is not None:
            loc_parts.append(f"offset {self.byte_offset}")
        loc = f" ({', '.join(loc_parts)})" if loc_parts else ""
        return f"{self.message}{loc}"


class LayoutReadError(LayoutError):
    """Raised when reading fails loudly. Aggregates one or more :class:`ReadIssue`."""

    def __init__(self, issues: list[ReadIssue]):
        self.issues = issues
        summary = "; ".join(str(i) for i in issues[:5])
        if len(issues) > 5:
            summary += f"; … (+{len(issues) - 5} more)"
        super().__init__(f"File did not match layout: {summary}")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass
class CellLocation:
    """Exact source location of a value read from a file.

    ``row`` is the 1-based physical line number in the input. For delimited
    files ``column`` holds the header name or integer index; for fixed-width
    files ``byte_offset`` and ``length`` describe the slice. ``raw`` is the
    original substring before transforms and coercion.
    """

    row: int
    column: str | int | None = None
    byte_offset: int | None = None
    length: int | None = None
    raw: str = ""


# ---------------------------------------------------------------------------
# Layout definition
# ---------------------------------------------------------------------------


@dataclass
class FileFormat:
    """How a file is physically structured."""

    kind: str  # "delimited" | "fixed"
    # delimited
    delimiter: str = ","
    quote: str = '"'
    escape: str | None = None
    # shared
    encoding: str = "utf-8"
    has_header: bool = False
    skip_blank_lines: bool = True
    # fixed-width
    record_length: int | None = None
    line_terminator: str = "\n"

    @property
    def is_fixed(self) -> bool:
        return self.kind == "fixed"

    @property
    def is_delimited(self) -> bool:
        return self.kind == "delimited"


@dataclass
class SourceSpec:
    """Where a value comes from within a record.

    Delimited layouts set ``column`` (a header name or 0-based integer index).
    Fixed-width layouts set ``offset`` and ``width`` (a 0-based byte slice).
    """

    column: str | int | None = None
    offset: int | None = None
    width: int | None = None

    @property
    def is_fixed(self) -> bool:
        return self.offset is not None


@dataclass
class TransformStep:
    """A single named, parameterized transform in a mapping's pipeline."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class FieldMapping:
    """Maps one entity field to a cell in the file (either direction)."""

    field: str
    source: SourceSpec | None = None
    transforms: list[TransformStep] = field(default_factory=list)
    expression: str | None = None  # read-direction escape hatch
    write_expression: str | None = None  # write-direction escape hatch
    required: bool = False
    default: Any = None  # substituted when the source cell is empty/missing
    const: Any = None  # literal value, no source (header/trailer markers)


@dataclass
class RecordTypeSelector:
    """How to recognize which record type a physical line is."""

    source: SourceSpec


@dataclass
class RecordType:
    """One record type within a multi-record file."""

    kind: str = "data"  # "data" | "header" | "trailer"
    type_code: str | None = None  # value that selects this record type
    entity: str | None = None  # per-record entity override
    mapping: list[FieldMapping] = field(default_factory=list)
    # trailer-only: field whose value is the count of data records
    record_count_field: str | None = None


@dataclass
class LayoutDefinition:
    """A fully-resolved file layout, loaded from a single YAML file."""

    name: str
    entity: str | None
    format: FileFormat
    mapping: list[FieldMapping] = field(default_factory=list)
    record_selector: RecordTypeSelector | None = None
    records: list[RecordType] = field(default_factory=list)
    description: str = ""

    @property
    def is_multi_record(self) -> bool:
        return bool(self.records)


# ---------------------------------------------------------------------------
# Read results
# ---------------------------------------------------------------------------


@dataclass
class ReadRecord:
    """One record produced by reading a file."""

    values: dict[str, Any]
    provenance: dict[str, CellLocation]
    kind: str = "data"  # "data" | "header" | "trailer"
    entity: str | None = None


@dataclass
class ReadResult:
    """Everything a read produced: records (with provenance) and any issues.

    In strict mode the reader raises :class:`LayoutReadError` instead of
    returning issues; non-strict callers inspect ``errors`` themselves.
    """

    records: list[ReadRecord] = field(default_factory=list)
    errors: list[ReadIssue] = field(default_factory=list)

    @property
    def data_records(self) -> list[ReadRecord]:
        """Records of kind ``data`` only (header/trailer excluded)."""
        return [r for r in self.records if r.kind == "data"]

    @property
    def data(self) -> list[dict[str, Any]]:
        """Value dicts for the data records — the common case."""
        return [r.values for r in self.data_records]
