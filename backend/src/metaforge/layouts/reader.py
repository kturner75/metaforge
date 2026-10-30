"""Read a flat file into entity values using a file layout (MF-020).

Produces records with exact provenance (row, column or byte offset) and fails
loudly on drift: missing/unexpected columns, bad record types, and values that
won't coerce. In strict mode (the default) all issues are collected and then
raised together as a :class:`LayoutReadError`; non-strict callers inspect
``ReadResult.errors`` instead.
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
        self.issues: list[ReadIssue] = []
        self.records: list[ReadRecord] = []
        self._data_count = 0

    def _types_for(self, entity_name: str | None) -> dict[str, str]:
        if entity_name and entity_name in self._entity_models:
            return _type_map(self._entity_models[entity_name])
        return self._default_types

    # -- top level -------------------------------------------------------

    def run(self, data: bytes | str) -> ReadResult:
        text = data.decode(self.fmt.encoding) if isinstance(data, bytes) else data
        rows = list(self._iter_rows(text))
        for row_num, cells, line in rows:
            if self.fmt.is_delimited:
                self._read_delimited_line(row_num, cells)
            else:
                self._read_fixed_line(row_num, line)
        self._check_trailers()
        return ReadResult(records=self.records, errors=self.issues)

    def _iter_rows(self, text: str):
        """Yield (row_num, cells_or_None, raw_line). Handles header skip + blanks."""
        if self.fmt.is_delimited:
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
                yield idx, cells, None
        else:
            self._header = None
            for idx, line in enumerate(text.splitlines(), start=1):
                if self.fmt.has_header and idx == 1:
                    continue
                if self.fmt.skip_blank_lines and line.strip() == "":
                    continue
                yield idx, None, line

    # -- record-type selection ------------------------------------------

    def _select_record_type(self, row_num, cells, line) -> RecordType | None:
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
            self._build_record(row_num, cells, None, rt.mapping, rt.kind, rt.entity, rt)
        else:
            self._build_record(
                row_num, cells, None, self.layout.mapping, "data", self.layout.entity, None
            )

    def _read_fixed_line(self, row_num: int, line: str) -> None:
        if self.fmt.record_length is not None and len(line) != self.fmt.record_length:
            self.issues.append(
                ReadIssue(
                    message=(
                        f"line length {len(line)} != expected record length "
                        f"{self.fmt.record_length}"
                    ),
                    row=row_num,
                    raw=line,
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

    def _raw_from_source(
        self, source: SourceSpec, cells: list[str] | None, line: str | None
    ) -> str | None:
        if source.is_fixed:
            assert line is not None
            end = source.offset + source.width  # type: ignore[operator]
            return line[source.offset : end]
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
        header = getattr(self, "_header", None)
        if header and column in header:
            return header.index(column)
        return None

    def _build_record(
        self,
        row_num: int,
        cells: list[str] | None,
        line: str | None,
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

            raw, loc = self._extract(m, row_num, cells, line)
            provenance[m.field] = loc

            if raw is None or raw.strip() == "":
                if m.required:
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
                values[m.field] = m.default
                continue

            # Transform (expression escape hatch or declarative pipeline).
            try:
                if m.expression is not None:
                    ensure_expression_functions()
                    processed = evaluate(m.expression, values, variables={"value": raw})
                else:
                    processed = apply_transforms(m.transforms, raw)
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
                values[m.field] = coercion.coerce(processed, field_type, m.field)
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

        if kind == "data":
            self._data_count += 1
        self.records.append(
            ReadRecord(values=values, provenance=provenance, kind=kind, entity=entity_name)
        )

    def _extract(
        self, m: FieldMapping, row_num: int, cells: list[str] | None, line: str | None
    ) -> tuple[str | None, CellLocation]:
        source = m.source
        if source is None:
            return None, CellLocation(row=row_num, raw="")
        if source.is_fixed:
            end = source.offset + source.width  # type: ignore[operator]
            raw = line[source.offset : end] if line is not None else ""
            return raw, CellLocation(
                row=row_num, byte_offset=source.offset, length=source.width, raw=raw
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
            return None, CellLocation(row=row_num, column=source.column, raw="")
        raw = cells[pos] if cells is not None and 0 <= pos < len(cells) else None
        return raw, CellLocation(row=row_num, column=source.column, raw=raw or "")

    # -- trailer validation ----------------------------------------------

    def _check_trailers(self) -> None:
        for rec in self.records:
            if rec.kind != "trailer":
                continue
            rt = self._trailer_type_for(rec)
            if rt is None or not rt.record_count_field:
                continue
            declared = rec.values.get(rt.record_count_field)
            if declared is None:
                continue
            try:
                declared_int = int(float(declared))
            except (TypeError, ValueError):
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
