"""Write entity values back out in a file layout (MF-020).

The inverse of :mod:`metaforge.layouts.reader`. For a layout using only
invertible transforms, ``read(write(records)) == records``.

Single-record layouts emit one line per data record (plus an optional header row
for delimited files with ``hasHeader``). Multi-record layouts emit the layout's
header record(s), then one line per data record, then the trailer record(s) —
with any ``recordCountField`` filled in with the number of data records.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Any

from metaforge.layouts import coercion
from metaforge.layouts.transforms import ensure_expression_functions, invert_transforms
from metaforge.layouts.types import (
    FieldMapping,
    LayoutConfigError,
    LayoutDefinition,
    RecordType,
)
from metaforge.validation.expressions import evaluate

if TYPE_CHECKING:
    from metaforge.metadata.loader import EntityModel


def write(
    layout: LayoutDefinition,
    records: list[dict[str, Any]],
    *,
    entity: EntityModel | None = None,
    entities: dict[str, EntityModel] | None = None,
    encode: bool = True,
) -> bytes | str:
    """Write ``records`` (data value dicts) into ``layout``'s file format.

    Returns ``bytes`` encoded with the layout's encoding, or ``str`` when
    ``encode=False``.
    """
    writer = _Writer(layout, entity=entity, entities=entities)
    text = writer.run(records)
    return text.encode(layout.format.encoding) if encode else text


def _type_map(entity: EntityModel | None) -> dict[str, str]:
    if entity is None:
        return {}
    return {f.name: f.type for f in entity.fields}


class _Writer:
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

    def _types_for(self, entity_name: str | None) -> dict[str, str]:
        if entity_name and entity_name in self._entity_models:
            return _type_map(self._entity_models[entity_name])
        return self._default_types

    def run(self, records: list[dict[str, Any]]) -> str:
        if self.layout.is_multi_record:
            return self._run_multi(records)
        return self._run_single(records)

    # -- single record type ---------------------------------------------

    def _run_single(self, records: list[dict[str, Any]]) -> str:
        mapping = self.layout.mapping
        types = self._default_types
        if self.fmt.is_delimited:
            rows: list[list[str]] = []
            if self.fmt.has_header:
                rows.append(self._header_row(mapping))
            for rec in records:
                rows.append(self._delimited_cells(mapping, rec, types))
            return self._emit_delimited(rows)
        lines = [self._fixed_line(mapping, rec, types) for rec in records]
        return self._join_fixed(lines)

    # -- multi record type ----------------------------------------------

    def _run_multi(self, records: list[dict[str, Any]]) -> str:
        data_rt = self._record_type("data")
        if data_rt is None:
            raise LayoutConfigError("multi-record layout has no 'data' record type")

        emitted_rows: list[list[str]] = []
        emitted_lines: list[str] = []

        def emit(mapping: list[FieldMapping], values: dict[str, Any], entity_name: str | None):
            types = self._types_for(entity_name)
            if self.fmt.is_delimited:
                emitted_rows.append(self._delimited_cells(mapping, values, types))
            else:
                emitted_lines.append(self._fixed_line(mapping, values, types))

        for rt in self.layout.records:
            if rt.kind == "header":
                emit(rt.mapping, {}, rt.entity)

        for rec in records:
            emit(data_rt.mapping, rec, data_rt.entity)

        for rt in self.layout.records:
            if rt.kind == "trailer":
                values: dict[str, Any] = {}
                if rt.record_count_field:
                    values[rt.record_count_field] = len(records)
                emit(rt.mapping, values, rt.entity)

        if self.fmt.is_delimited:
            return self._emit_delimited(emitted_rows)
        return self._join_fixed(emitted_lines)

    # -- cell rendering --------------------------------------------------

    def _cell_value(self, m: FieldMapping, values: dict[str, Any], types: dict[str, str]) -> str:
        if m.const is not None:
            return str(m.const)

        raw_value = values.get(m.field, m.default)

        # Expression escape hatch: must be reversible to write.
        if m.expression is not None and m.write_expression is None and not m.transforms:
            raise LayoutConfigError(
                f"field '{m.field}' uses a read-only 'expression'; add "
                "'writeExpression' to write this layout"
            )
        if m.write_expression is not None:
            ensure_expression_functions()
            rendered = evaluate(m.write_expression, values, variables={"value": raw_value})
            return "" if rendered is None else str(rendered)

        field_type = types.get(m.field, "string")
        rendered = coercion.render(raw_value, field_type, m.field)
        return str(invert_transforms(m.transforms, rendered))

    def _header_row(self, mapping: list[FieldMapping]) -> list[str]:
        header: list[str] = []
        for m in mapping:
            col = m.source.column if m.source else None
            header.append(col if isinstance(col, str) else m.field)
        return header

    def _delimited_cells(
        self, mapping: list[FieldMapping], values: dict[str, Any], types: dict[str, str]
    ) -> list[str]:
        # Integer columns define explicit positions; otherwise use mapping order.
        int_positions = [
            m.source.column for m in mapping if m.source and isinstance(m.source.column, int)
        ]
        if int_positions:
            row = [""] * (max(int_positions) + 1)
            for m in mapping:
                if m.source and isinstance(m.source.column, int):
                    row[m.source.column] = self._cell_value(m, values, types)
            return row
        return [self._cell_value(m, values, types) for m in mapping]

    def _fixed_line(
        self, mapping: list[FieldMapping], values: dict[str, Any], types: dict[str, str]
    ) -> str:
        width = self.fmt.record_length or self._implied_width(mapping)
        buffer = [" "] * width
        for m in mapping:
            if not m.source or not m.source.is_fixed:
                continue
            cell = self._cell_value(m, values, types)
            offset = m.source.offset or 0
            field_width = m.source.width or len(cell)
            cell = cell[:field_width].ljust(field_width)
            for i, ch in enumerate(cell):
                if offset + i < width:
                    buffer[offset + i] = ch
        return "".join(buffer)

    @staticmethod
    def _implied_width(mapping: list[FieldMapping]) -> int:
        end = 0
        for m in mapping:
            if m.source and m.source.is_fixed:
                end = max(end, (m.source.offset or 0) + (m.source.width or 0))
        return end

    # -- emit ------------------------------------------------------------

    def _emit_delimited(self, rows: list[list[str]]) -> str:
        out = io.StringIO()
        kwargs: dict[str, Any] = {
            "delimiter": self.fmt.delimiter,
            "quotechar": self.fmt.quote,
            "lineterminator": self.fmt.line_terminator,
        }
        if self.fmt.escape:
            kwargs["escapechar"] = self.fmt.escape
            kwargs["doublequote"] = False
        csv.writer(out, **kwargs).writerows(rows)
        return out.getvalue()

    def _join_fixed(self, lines: list[str]) -> str:
        term = self.fmt.line_terminator
        return "".join(line + term for line in lines)

    def _record_type(self, kind: str) -> RecordType | None:
        for rt in self.layout.records:
            if rt.kind == kind:
                return rt
        return None
