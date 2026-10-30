"""Load file-layout definitions from metadata/layouts/*.yaml (MF-020)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from metaforge.layouts.transforms import is_known_transform
from metaforge.layouts.types import (
    FieldMapping,
    FileFormat,
    LayoutConfigError,
    LayoutDefinition,
    RecordType,
    RecordTypeSelector,
    SourceSpec,
    TransformStep,
)


class LayoutLoader:
    """Loads file-layout configurations from ``metadata/layouts/*.yaml``.

    Mirrors :class:`~metaforge.views.loader.ViewConfigLoader` and
    :class:`~metaforge.metadata.loader.MetadataLoader`: ``load_all`` /
    ``reload`` / ``get_layout`` / ``list_layouts``.
    """

    def __init__(self, layouts_path: Path):
        self.layouts_path = layouts_path
        self.layouts: dict[str, LayoutDefinition] = {}

    def load_all(self) -> None:
        if not self.layouts_path.exists():
            return
        for yaml_file in sorted(self.layouts_path.glob("*.yaml")):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if data and "layout" in data:
                layout = parse_layout(data)
                self.layouts[layout.name] = layout

    def reload(self) -> None:
        self.layouts.clear()
        self.load_all()

    def get_layout(self, name: str) -> LayoutDefinition | None:
        return self.layouts.get(name)

    def list_layouts(self) -> list[LayoutDefinition]:
        return list(self.layouts.values())


# ---------------------------------------------------------------------------
# Parsing (also usable standalone, e.g. in tests)
# ---------------------------------------------------------------------------


def parse_layout(data: dict[str, Any]) -> LayoutDefinition:
    """Parse a raw YAML dict into a :class:`LayoutDefinition`."""
    name = data.get("layout")
    if not name:
        raise LayoutConfigError("layout file is missing a 'layout' name")

    fmt = _parse_format(data.get("format") or {})

    records: list[RecordType] = []
    selector: RecordTypeSelector | None = None
    mapping: list[FieldMapping] = []

    if "records" in data:
        selector_data = data.get("recordType")
        if not selector_data:
            raise LayoutConfigError(
                f"layout '{name}' uses 'records' but has no 'recordType' selector"
            )
        selector = RecordTypeSelector(source=_parse_source(selector_data, where="recordType"))
        records = [_parse_record_type(rt, name) for rt in data["records"]]
    else:
        mapping = [_parse_mapping(m, name) for m in data.get("mapping", [])]

    return LayoutDefinition(
        name=name,
        entity=data.get("entity"),
        format=fmt,
        mapping=mapping,
        record_selector=selector,
        records=records,
        description=data.get("description", ""),
    )


def _parse_format(data: dict[str, Any]) -> FileFormat:
    kind = data.get("kind", "delimited")
    if kind not in ("delimited", "fixed"):
        raise LayoutConfigError(f"unknown format kind {kind!r} (expected 'delimited' or 'fixed')")
    return FileFormat(
        kind=kind,
        delimiter=data.get("delimiter", ","),
        quote=data.get("quote", '"'),
        escape=data.get("escape"),
        encoding=data.get("encoding", "utf-8"),
        has_header=data.get("hasHeader", False),
        skip_blank_lines=data.get("skipBlankLines", True),
        record_length=data.get("recordLength"),
        line_terminator=data.get("lineTerminator", "\n"),
    )


def _parse_record_type(data: dict[str, Any], layout_name: str) -> RecordType:
    kind = data.get("kind", "data")
    if kind not in ("data", "header", "trailer"):
        raise LayoutConfigError(f"layout '{layout_name}': unknown record kind {kind!r}")
    return RecordType(
        kind=kind,
        type_code=_as_code(data.get("type")),
        entity=data.get("entity"),
        mapping=[_parse_mapping(m, layout_name) for m in data.get("mapping", [])],
        record_count_field=data.get("recordCountField"),
    )


def _as_code(value: Any) -> str | None:
    return None if value is None else str(value)


def _parse_mapping(data: dict[str, Any], layout_name: str) -> FieldMapping:
    field_name = data.get("field")
    if not field_name:
        raise LayoutConfigError(f"layout '{layout_name}': a mapping entry has no 'field'")

    source: SourceSpec | None = None
    if "column" in data or "at" in data:
        source = _parse_source(data, where=f"mapping '{field_name}'")

    return FieldMapping(
        field=field_name,
        source=source,
        transforms=_parse_transforms(data.get("transform", []), field_name),
        expression=data.get("expression"),
        write_expression=data.get("writeExpression"),
        required=data.get("required", False),
        default=data.get("default"),
        const=data.get("const"),
    )


def _parse_source(data: dict[str, Any], *, where: str) -> SourceSpec:
    if "at" in data:
        at = data["at"] or {}
        offset = at.get("offset")
        width = at.get("width")
        if offset is None or width is None:
            raise LayoutConfigError(f"{where}: 'at' requires both 'offset' and 'width'")
        return SourceSpec(offset=offset, width=width)
    if "column" in data:
        return SourceSpec(column=data["column"])
    raise LayoutConfigError(f"{where}: source needs either 'column' or 'at'")


def _parse_transforms(raw: Any, field_name: str) -> list[TransformStep]:
    steps: list[TransformStep] = []
    for item in raw or []:
        if isinstance(item, str):
            name, params = item, {}
        elif isinstance(item, dict) and len(item) == 1:
            name, params = next(iter(item.items()))
            params = params or {}
        else:
            raise LayoutConfigError(
                f"field '{field_name}': each transform must be a name or a single-key "
                f"mapping, got {item!r}"
            )
        if not is_known_transform(name):
            raise LayoutConfigError(f"field '{field_name}': unknown transform {name!r}")
        steps.append(TransformStep(name=name, params=params))
    return steps
