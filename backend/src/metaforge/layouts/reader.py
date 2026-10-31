"""Read a flat file into entity values using a file layout (MF-020).

Produces records with exact provenance (row, column or byte offset) and fails
loudly on drift: missing/unexpected columns, bad record types, bad trailer
counts, and values that won't coerce. In strict mode (the default) all issues
are collected and then raised together as a :class:`LayoutReadError`; non-strict
callers inspect ``ReadResult.errors`` instead.

Delimited input is decoded to text and parsed with :mod:`csv`. Fixed-width input
is kept as bytes so that ``offset``/``width`` are honoured as **byte** positions
(a UTF-8 multibyte character occupies more than one byte); each field slice is
decoded with the layout's encoding.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Any

from metaforge.layouts import coercion
from metaforge.layouts.transforms import apply_transforms, ensure_expression_functions
from metaforge.layouts.types import (
    CellLocation,
    FieldMapping,
    LayoutDefinition,
    LayoutReadError,
    ReadIssue,
    ReadRecord,
    ReadResult,
    RecordType,
    SourceSpec,
)
from metaforge.validation.expressions import evaluate

if TYPE_CHECKING:
    from metaforge.metadata.loader import EntityModel


def read(
    layout: LayoutDefinition,
    data: bytes | str,
    *,
    entity: EntityModel | None = None,
    entities: dict[str, EntityModel] | None = None,
    strict: bool = True,
) -> ReadResult:
    """Read ``data`` into records according to ``layout``.

    Args:
        layout: The parsed layout definition.
        data: File contents as bytes (decoded with the layout's encoding) or str.
        entity: EntityModel for ``layout.entity``, used for type coercion.
        entities: Map of entity name → EntityModel, for multi-record layouts
            whose record types target different entities.
        strict: When True, raise :class:`LayoutReadError` if any issue is found.
    """
    reader = _Reader(layout, entity=entity, entities=entities)
    result = reader.run(data)
    if strict and result.errors:
        raise LayoutReadError(result.errors)
    return result


def _type_map(entity: EntityModel | None) -> dict[str, str]:
    if entity is None:
        return {}
    return {f.name: f.type for f in entity.fields}


def _as_integral(value: Any) -> int | None:
    """Return ``value`` as an exact integer, or ``None`` if it is not integral.

    Booleans, non-integral floats (``1.9``), empty values and non-numeric
    strings (``"garbage"``) all return ``None`` so the caller can report drift.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    token = str(value).strip()
    if token == "":
        return None
    try:
        return int(token)
    except ValueError:
        pass
    try:
        number = float(token)
    except ValueError:
        return None
    return int(number) if number.is_integer() else None


class _Reader:
    def __init__(
        self,
        layout: LayoutDefinition,
        *,
        entity: EntityModel | None,
        entities: dict[str, EntityModel] | None,
    ):
        self.layout = layout
        self.fmt = layout.format
        self._entity_models: dict[str, Any] = dict(entities or {})
        if entity is not None:
            self._entity_models.setdefault(entity.name, entity)
        self._default_types = _type_map(entity)
        self._header: list[str] | None = None
        self.issues: list[ReadIssue] = []
        self.records: list[ReadRecord] = []
        self._data_count = 0

    def _types_for(self, entity_name: str | None) -> dict[str, str]:
        if entity_name and entity_name in self._entity_models:
            return _type_map(self._entity_models[entity_name])
        return self._default_types

    # -- top level -------------------------------------------------------

    def run(self, data: bytes | str) -> ReadResult:
        if self.fmt.is_delimited:
            text = data.decode(self.fmt.encoding) if isinstance(data, bytes) else data
            for row_num, cells in self._iter_delimited(text):
                self._read_delimited_line(row_num, cells)
        else:
            raw = data if isinstance(data, bytes) else data.encode(self.fmt.encoding)
            for row_num, line in self._iter_fixed(raw):
                self._read_fixed_line(row_num, line)
        self._check_trailers()
        return ReadResult(records=self.records, errors=self.issues)

    def _iter_delimited(self, text: str):
        """Yield (row_num, cells) for delimited input; handles header + blanks."""
        dialect_kwargs: dict[str, Any] = {
            "delimiter": self.fmt.delimiter,
            "quotechar": self.fmt.quote,
        }
        if self.fmt.escape:
            dialect_kwargs["escapechar"] = self.fmt.escape
            dialect_kwargs["doublequote"] = False
        parsed = list(csv.reader(io.StringIO(text), **dialect_kwargs))
        for idx, cells in enumerate(parsed, start=1):
            if self.fmt.has_header and idx == 1:
                self._header = cells
                continue
            if self.fmt.skip_blank_lines and (not cells or cells == [""]):
                continue
            yield idx, cells

    def _iter_fixed(self, raw: bytes):
        r"""Yield (row_num, line_bytes) for fixed-width input.

        Lines are split on the layout's *encoded* line terminator so multibyte
        encodings (e.g. UTF-16, whose newline is ``b"\n\x00"``) are honoured
        rather than split on a bare ``0x0a``. A trailing encoded carriage
        return is stripped so a ``"\n"`` layout still reads ``"\r\n"`` files.
        """
        enc = self.fmt.encoding
        term = self.fmt.line_terminator.encode(enc)
        cr = "\r".encode(enc)
        parts = raw.split(term) if term else [raw]
        for idx, line in enumerate(parts, start=1):
            if cr and line.endswith(cr):
                line = line[: -len(cr)]
            if self.fmt.has_header and idx == 1:
                continue
            if self.fmt.skip_blank_lines and line.strip() == b"":
                continue
            yield idx, line

    # -- record-type selection ------------------------------------------

    def _select_record_type(
        self, row_num: int, cells: list[str] | None, line: bytes | None
    ) -> RecordType | None:
        sel = self.layout.record_selector
        assert sel is not None
        code = self._raw_from_source(sel.source, cells, line)
        for rt in self.layout.records:
            if rt.type_code == code:
                return rt
        self.issues.append(
            ReadIssue(
                message=f"unknown record type {code!r}",
                row=row_num,
                raw=code,
            )
        )
        return None

    def _read_delimited_line(self, row_num: int, cells: list[str]) -> None:
        if self.layout.is_multi_record:
            rt = self._select_record_type(row_num, cells, None)
            if rt is None:
                return
            self._validate_delimited_shape(row_num, cells, rt.mapping, use_header=False)
            self._build_record(row_num, cells, None, rt.mapping, rt.kind, rt.entity, rt)
        else:
            self._validate_delimited_shape(row_num, cells, self.layout.mapping, use_header=True)
            self._build_record(
                row_num, cells, None, self.layout.mapping, "data", self.layout.entity, None
            )

    def _validate_delimited_shape(
        self,
        row_num: int,
        cells: list[str],
        mapping: list[FieldMapping],
        *,
        use_header: bool,
    ) -> None:
        """Flag column-count drift: too many or too few cells for this row."""
        # Position-based layouts (any integer column) are validated by the
        # highest referenced index, not header equality — the header is then
        # cosmetic and may be sparser than the mapped positions.
        has_int_cols = any(m.source and isinstance(m.source.column, int) for m in mapping)
        if use_header and self.fmt.has_header and self._header is not None and not has_int_cols:
            expected = len(self._header)
            if len(cells) != expected:
                self.issues.append(
                    ReadIssue(
                        message=f"row has {len(cells)} columns, expected {expected}",
                        row=row_num,
                    )
                )
            return
        # The highest referenced integer index sets the minimum width.
        max_index = -1
        for m in mapping:
            if m.source and isinstance(m.source.column, int):
                max_index = max(max_index, m.source.column)
        sel = self.layout.record_selector
        if sel and sel.source and isinstance(sel.source.column, int):
            max_index = max(max_index, sel.source.column)
        if max_index >= 0 and len(cells) <= max_index:
            self.issues.append(
                ReadIssue(
                    message=f"row has {len(cells)} columns, need at least {max_index + 1}",
                    row=row_num,
                )
            )

    def _read_fixed_line(self, row_num: int, line: bytes) -> None:
        if self.fmt.record_length is not None and len(line) != self.fmt.record_length:
            self.issues.append(
                ReadIssue(
                    message=(
                        f"line length {len(line)} bytes != expected record length "
                        f"{self.fmt.record_length}"
                    ),
                    row=row_num,
                    raw=self._safe_decode(line),
                )
            )
        if self.layout.is_multi_record:
            rt = self._select_record_type(row_num, None, line)
            if rt is None:
                return
            self._build_record(row_num, None, line, rt.mapping, rt.kind, rt.entity, rt)
        else:
            self._build_record(
                row_num, None, line, self.layout.mapping, "data", self.layout.entity, None
            )

    # -- cell extraction -------------------------------------------------

    def _safe_decode(self, chunk: bytes) -> str:
        """Lossy decode for *diagnostic* text only (never for field values)."""
        return chunk.decode(self.fmt.encoding, errors="replace")

    def _raw_from_source(
        self, source: SourceSpec, cells: list[str] | None, line: bytes | None
    ) -> str | None:
        if source.is_fixed:
            assert line is not None
            end = source.offset + source.width  # type: ignore[operator]
            try:
                return line[source.offset : end].decode(self.fmt.encoding)
            except UnicodeDecodeError:
                return None  # surfaced as an unknown record type
        # delimited
        pos = self._resolve_column(source.column)
        if pos is None:
            return None
        if cells is None or pos < 0 or pos >= len(cells):
            return None
        return cells[pos]

    def _resolve_column(self, column: str | int | None) -> int | None:
        if column is None:
            return None
        if isinstance(column, int):
            return column
        if self._header and column in self._header:
            return self._header.index(column)
        return None

    def _build_record(
        self,
        row_num: int,
        cells: list[str] | None,
        line: bytes | None,
        mapping: list[FieldMapping],
        kind: str,
        entity_name: str | None,
        record_type: RecordType | None,
    ) -> None:
        types = self._types_for(entity_name)
        values: dict[str, Any] = {}
        provenance: dict[str, CellLocation] = {}

        for m in mapping:
            # A const field is a literal (e.g. a record-type marker). A source
            # may still be given to tell the writer which column/offset it owns;
            # on read we ignore the cell and take the literal.
            if m.const is not None:
                values[m.field] = m.const
                continue

            raw, loc, decoded_ok = self._extract(m, row_num, cells, line)
            provenance[m.field] = loc

            # A field whose bytes could not be decoded is already a reported
            # issue; do not let a replacement value flow into the record.
            if not decoded_ok:
                values[m.field] = None
                continue

            raw_is_empty = raw is None or raw.strip() == ""

            # An empty cell is only an error up front when the field is required.
            if raw_is_empty and m.required:
                self.issues.append(
                    ReadIssue(
                        message="required field is missing or empty",
                        row=row_num,
                        field=m.field,
                        column=loc.column,
                        byte_offset=loc.byte_offset,
                        raw=raw,
                    )
                )

            # With no transform/expression there is nothing that could fill an
            # empty cell, so fall straight back to the mapping default.
            if raw_is_empty and m.expression is None and not m.transforms:
                values[m.field] = m.default
                continue

            # Transform (expression escape hatch or declarative pipeline). These
            # run even for empty cells so the `default` transform and empty-cell
            # expressions can fire.
            transform_input = raw if raw is not None else ""
            try:
                if m.expression is not None:
                    ensure_expression_functions()
                    processed = evaluate(m.expression, values, variables={"value": transform_input})
                else:
                    processed = apply_transforms(m.transforms, transform_input)
            except Exception as exc:  # TransformError or evaluation error
                self.issues.append(
                    ReadIssue(
                        message=f"transform failed: {exc}",
                        row=row_num,
                        field=m.field,
                        column=loc.column,
                        byte_offset=loc.byte_offset,
                        raw=raw,
                    )
                )
                values[m.field] = None
                continue

            # Coerce to the entity field's type.
            field_type = types.get(m.field, "string")
            try:
                coerced = coercion.coerce(processed, field_type, m.field)
            except Exception as exc:
                self.issues.append(
                    ReadIssue(
                        message=str(exc),
                        row=row_num,
                        field=m.field,
                        column=loc.column,
                        byte_offset=loc.byte_offset,
                        raw=raw,
                    )
                )
                values[m.field] = None
                continue

            # Fall back to the mapping default when the value is still empty.
            if coerced is None and m.default is not None:
                coerced = m.default
            values[m.field] = coerced

        if kind == "data":
            self._data_count += 1
        self.records.append(
            ReadRecord(values=values, provenance=provenance, kind=kind, entity=entity_name)
        )

    def _extract(
        self, m: FieldMapping, row_num: int, cells: list[str] | None, line: bytes | None
    ) -> tuple[str | None, CellLocation, bool]:
        """Return (raw_value, location, decoded_ok).

        ``decoded_ok`` is False only when a fixed-width field's bytes could not
        be decoded with the layout encoding — a reported, located failure.
        """
        source = m.source
        if source is None:
            return None, CellLocation(row=row_num, raw=""), True
        if source.is_fixed:
            end = source.offset + source.width  # type: ignore[operator]
            chunk = line[source.offset : end] if line is not None else b""
            try:
                raw = chunk.decode(self.fmt.encoding)
            except UnicodeDecodeError:
                display = self._safe_decode(chunk)
                self.issues.append(
                    ReadIssue(
                        message=f"could not decode field bytes as {self.fmt.encoding}",
                        row=row_num,
                        field=m.field,
                        byte_offset=source.offset,
                        raw=display,
                    )
                )
                loc = CellLocation(
                    row=row_num, byte_offset=source.offset, length=source.width, raw=display
                )
                return None, loc, False
            return (
                raw,
                CellLocation(row=row_num, byte_offset=source.offset, length=source.width, raw=raw),
                True,
            )
        pos = self._resolve_column(source.column)
        if pos is None:
            self.issues.append(
                ReadIssue(
                    message=f"column {source.column!r} not found in header",
                    row=row_num,
                    field=m.field,
                    column=source.column,
                )
            )
            return None, CellLocation(row=row_num, column=source.column, raw=""), True
        raw = cells[pos] if cells is not None and 0 <= pos < len(cells) else None
        return raw, CellLocation(row=row_num, column=source.column, raw=raw or ""), True

    # -- trailer validation ----------------------------------------------

    def _check_trailers(self) -> None:
        for rec in self.records:
            if rec.kind != "trailer":
                continue
            rt = self._trailer_type_for(rec)
            if rt is None or not rt.record_count_field:
                continue
            declared = rec.values.get(rt.record_count_field)
            declared_int = _as_integral(declared)
            if declared_int is None:
                self.issues.append(
                    ReadIssue(
                        message=f"trailer record count {declared!r} is not an integer",
                        field=rt.record_count_field,
                        raw=None if declared is None else str(declared),
                    )
                )
                continue
            if declared_int != self._data_count:
                self.issues.append(
                    ReadIssue(
                        message=(
                            f"trailer record count {declared_int} != "
                            f"{self._data_count} data records read"
                        ),
                        field=rt.record_count_field,
                    )
                )

    def _trailer_type_for(self, rec: ReadRecord) -> RecordType | None:
        for rt in self.layout.records:
            if rt.kind == "trailer":
                return rt
        return None
