"""Tests for the file-layout system (MF-020)."""

from pathlib import Path

import pytest

from metaforge.layouts import (
    LayoutConfigError,
    LayoutLoader,
    LayoutReadError,
    apply_transforms,
    parse_layout,
    read,
    write,
)
from metaforge.layouts.coercion import coerce, render
from metaforge.layouts.transforms import TRANSFORMS, get_transform
from metaforge.layouts.types import TransformStep
from metaforge.metadata.loader import EntityModel, FieldDefinition

REPO_ROOT = Path(__file__).resolve().parents[2]


def _entity(**field_types: str) -> EntityModel:
    """Build a throwaway EntityModel with the given field name -> type map."""
    fields = [FieldDefinition(name=n, type=t, display_name=n) for n, t in field_types.items()]
    return EntityModel(
        name="T",
        display_name="T",
        plural_name="Ts",
        primary_key="id",
        fields=fields,
        abbreviation="TT",
    )


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------


class TestTransforms:
    def test_trim(self):
        assert get_transform("trim").apply("  hi  ", {}) == "hi"
        assert get_transform("trim").apply("xxhixx", {"chars": "x"}) == "hi"

    def test_trim_invert_is_identity(self):
        assert get_transform("trim").invert("hi", {}) == "hi"

    def test_pad_invert_pads_and_apply_strips(self):
        assert (
            get_transform("pad").invert("42", {"width": 5, "char": "0", "side": "left"}) == "00042"
        )
        assert get_transform("pad").apply("00042", {"char": "0", "side": "left"}) == "42"

    def test_pad_requires_width(self):
        with pytest.raises(Exception):
            get_transform("pad").invert("x", {})

    def test_date_format_roundtrip(self):
        spec = get_transform("dateFormat")
        assert spec.apply("20240115", {"from": "%Y%m%d"}) == "2024-01-15"
        assert spec.invert("2024-01-15", {"from": "%Y%m%d"}) == "20240115"

    def test_date_format_bad_value(self):
        with pytest.raises(Exception):
            get_transform("dateFormat").apply("notadate", {"from": "%Y%m%d"})

    def test_implied_decimals(self):
        spec = get_transform("impliedDecimals")
        assert spec.apply("12345", {"places": 2}) == 123.45
        assert spec.invert(123.45, {"places": 2}) == "12345"
        assert spec.apply("-500", {"places": 2}) == -5.0
        assert spec.invert(-5.0, {"places": 2}) == "-500"

    def test_lookup_both_ways(self):
        spec = get_transform("lookup")
        params = {"map": {"A": "active", "I": "inactive"}}
        assert spec.apply("A", params) == "active"
        assert spec.invert("inactive", params) == "I"

    def test_lookup_missing_code_strict(self):
        with pytest.raises(Exception):
            get_transform("lookup").apply("Z", {"map": {"A": "active"}})

    def test_lookup_default(self):
        assert (
            get_transform("lookup").apply("Z", {"map": {"A": "active"}, "default": "unknown"})
            == "unknown"
        )

    def test_pipeline_order(self):
        steps = [TransformStep("trim", {}), TransformStep("upper", {})]
        assert apply_transforms(steps, "  hi ") == "HI"

    def test_every_transform_has_both_directions(self):
        for spec in TRANSFORMS.values():
            assert callable(spec.apply)
            assert callable(spec.invert)


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------


class TestCoercion:
    def test_number(self):
        assert coerce("12.5", "currency", "amt") == 12.5
        assert coerce(10, "number", "n") == 10.0

    def test_number_invalid_is_loud(self):
        with pytest.raises(Exception):
            coerce("abc", "number", "n")

    def test_boolean(self):
        assert coerce("yes", "checkbox", "b") == 1
        assert coerce("0", "checkbox", "b") == 0

    def test_boolean_invalid_is_loud(self):
        with pytest.raises(Exception):
            coerce("maybe", "boolean", "b")

    def test_date(self):
        assert coerce("2024-01-15", "date", "d") == "2024-01-15"

    def test_date_invalid_is_loud(self):
        with pytest.raises(Exception):
            coerce("2024-99-99", "date", "d")

    def test_empty_is_none(self):
        assert coerce("", "number", "n") is None
        assert coerce("   ", "string", "s") is None

    def test_render(self):
        assert render(123.0, "currency", "a") == "123"
        assert render(123.45, "currency", "a") == "123.45"
        assert render(1, "checkbox", "b") == "1"
        assert render(None, "string", "s") == ""


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class TestReaderDelimited:
    def _layout(self, **fmt):
        return parse_layout(
            {
                "layout": "L",
                "format": {"kind": "delimited", "delimiter": ",", **fmt},
                "mapping": [
                    {"field": "a", "column": "a", "required": True, "transform": [{"trim": {}}]},
                    {"field": "b", "column": "b"},
                ],
            }
        )

    def test_header(self):
        res = read(self._layout(hasHeader=True), "a,b\n 1 ,2\n3,4\n")
        assert res.data == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]

    def test_no_header_by_index(self):
        layout = parse_layout(
            {
                "layout": "L",
                "format": {"kind": "delimited"},
                "mapping": [{"field": "a", "column": 0}, {"field": "b", "column": 1}],
            }
        )
        assert read(layout, "x,y\n").data == [{"a": "x", "b": "y"}]

    def test_provenance(self):
        res = read(self._layout(hasHeader=True), "a,b\n1,2\n")
        loc = res.records[0].provenance["a"]
        assert loc.row == 2 and loc.column == "a" and loc.raw == "1"

    def test_missing_required_is_loud(self):
        with pytest.raises(LayoutReadError) as exc:
            read(self._layout(hasHeader=True), "a,b\n,2\n")
        assert "required" in str(exc.value)

    def test_missing_column_is_loud(self):
        with pytest.raises(LayoutReadError) as exc:
            read(self._layout(hasHeader=True), "x,b\n1,2\n")
        assert "not found" in str(exc.value)

    def test_non_strict_collects_errors(self):
        res = read(self._layout(hasHeader=True), "a,b\n,2\n", strict=False)
        assert res.errors and res.errors[0].field == "a"


class TestReaderFixed:
    def _layout(self):
        return parse_layout(
            {
                "layout": "F",
                "format": {"kind": "fixed", "recordLength": 10},
                "mapping": [
                    {"field": "a", "at": {"offset": 0, "width": 5}, "transform": [{"trim": {}}]},
                    {"field": "b", "at": {"offset": 5, "width": 5}, "transform": [{"trim": {}}]},
                ],
            }
        )

    def test_read(self):
        assert read(self._layout(), "John Doe  \n").data == [{"a": "John", "b": "Doe"}]

    def test_provenance_byte_offset(self):
        loc = read(self._layout(), "John Doe  \n").records[0].provenance["b"]
        assert loc.byte_offset == 5 and loc.length == 5

    def test_length_drift_is_loud(self):
        with pytest.raises(LayoutReadError) as exc:
            read(self._layout(), "short\n")
        assert "length" in str(exc.value)


class TestReaderMultiRecord:
    def _layout(self):
        return parse_layout(
            {
                "layout": "Feed",
                "format": {"kind": "delimited", "delimiter": ","},
                "recordType": {"column": 0},
                "records": [
                    {
                        "type": "H",
                        "kind": "header",
                        "mapping": [{"field": "rt", "const": "H", "column": 0}],
                    },
                    {
                        "type": "D",
                        "kind": "data",
                        "mapping": [
                            {"field": "rt", "const": "D", "column": 0},
                            {"field": "name", "column": 1, "required": True},
                        ],
                    },
                    {
                        "type": "T",
                        "kind": "trailer",
                        "recordCountField": "count",
                        "mapping": [
                            {"field": "rt", "const": "T", "column": 0},
                            {"field": "count", "column": 1},
                        ],
                    },
                ],
            }
        )

    def test_kinds_and_data(self):
        res = read(self._layout(), "H\nD,Ada\nD,Grace\nT,2\n")
        assert [r.kind for r in res.records] == ["header", "data", "data", "trailer"]
        assert res.data == [{"rt": "D", "name": "Ada"}, {"rt": "D", "name": "Grace"}]

    def test_unknown_record_type_is_loud(self):
        with pytest.raises(LayoutReadError) as exc:
            read(self._layout(), "H\nZ,bad\nT,0\n")
        assert "unknown record type" in str(exc.value)

    def test_trailer_count_mismatch_is_loud(self):
        with pytest.raises(LayoutReadError) as exc:
            read(self._layout(), "H\nD,Ada\nT,9\n")
        assert "count" in str(exc.value)


# ---------------------------------------------------------------------------
# Writer + round-trip
# ---------------------------------------------------------------------------


class TestWriter:
    def test_delimited_header_emitted(self):
        layout = parse_layout(
            {
                "layout": "L",
                "format": {"kind": "delimited", "hasHeader": True},
                "mapping": [{"field": "a", "column": "a"}, {"field": "b", "column": "b"}],
            }
        )
        out = write(layout, [{"a": "1", "b": "2"}], encode=False)
        assert out.splitlines()[0] == "a,b"

    def test_returns_bytes_by_default(self):
        layout = parse_layout(
            {
                "layout": "L",
                "format": {"kind": "delimited"},
                "mapping": [{"field": "a", "column": 0}],
            }
        )
        assert isinstance(write(layout, [{"a": "x"}]), bytes)

    def test_delimited_roundtrip(self):
        layout = parse_layout(
            {
                "layout": "L",
                "format": {"kind": "delimited", "hasHeader": True},
                "mapping": [
                    {
                        "field": "code",
                        "column": "code",
                        "transform": [{"lookup": {"map": {"A": "active"}}}],
                    },
                    {
                        "field": "when",
                        "column": "when",
                        "transform": [{"dateFormat": {"from": "%Y%m%d"}}],
                    },
                ],
            }
        )
        recs = read(layout, "code,when\nA,20240115\n").data
        assert read(layout, write(layout, recs, encode=False)).data == recs

    def test_fixed_roundtrip(self):
        layout = parse_layout(
            {
                "layout": "F",
                "format": {"kind": "fixed", "recordLength": 15},
                "mapping": [
                    {"field": "a", "at": {"offset": 0, "width": 10}, "transform": [{"trim": {}}]},
                    {"field": "b", "at": {"offset": 10, "width": 5}, "transform": [{"trim": {}}]},
                ],
            }
        )
        recs = read(layout, "Ada       LOV  \n").data
        out = write(layout, recs, encode=False)
        assert len(out.splitlines()[0]) == 15
        assert read(layout, out).data == recs

    def test_multi_record_write_emits_header_data_trailer(self):
        layout = TestReaderMultiRecord()._layout()
        out = write(
            layout, [{"rt": "D", "name": "Ada"}, {"rt": "D", "name": "Grace"}], encode=False
        )
        lines = out.splitlines()
        assert lines[0] == "H"
        assert lines[-1] == "T,2"  # trailer count = number of data records


# ---------------------------------------------------------------------------
# Expression escape hatch
# ---------------------------------------------------------------------------


class TestExpressionHatch:
    def test_read_expression(self):
        layout = parse_layout(
            {
                "layout": "E",
                "format": {"kind": "delimited", "hasHeader": True},
                "mapping": [{"field": "name", "column": "n", "expression": "upper(trim(value))"}],
            }
        )
        assert read(layout, "n\n ada \n").data == [{"name": "ADA"}]

    def test_write_requires_write_expression(self):
        layout = parse_layout(
            {
                "layout": "E",
                "format": {"kind": "delimited", "hasHeader": True},
                "mapping": [{"field": "name", "column": "n", "expression": "upper(value)"}],
            }
        )
        with pytest.raises(LayoutConfigError):
            write(layout, [{"name": "ADA"}])

    def test_write_expression_used(self):
        layout = parse_layout(
            {
                "layout": "E",
                "format": {"kind": "delimited", "hasHeader": True},
                "mapping": [
                    {
                        "field": "name",
                        "column": "n",
                        "expression": "upper(value)",
                        "writeExpression": "lower(value)",
                    }
                ],
            }
        )
        assert write(layout, [{"name": "ADA"}], encode=False).splitlines()[1] == "ada"


# ---------------------------------------------------------------------------
# Typed coercion through the engine
# ---------------------------------------------------------------------------


class TestEngineWithEntityTypes:
    def test_numbers_and_dates_coerced(self):
        entity = _entity(amount="currency", closed="date", active="checkbox")
        layout = parse_layout(
            {
                "layout": "D",
                "entity": "T",
                "format": {"kind": "delimited", "hasHeader": True},
                "mapping": [
                    {
                        "field": "amount",
                        "column": "amt",
                        "transform": [{"impliedDecimals": {"places": 2}}],
                    },
                    {
                        "field": "closed",
                        "column": "cd",
                        "transform": [{"dateFormat": {"from": "%Y%m%d"}}],
                    },
                    {"field": "active", "column": "ac"},
                ],
            }
        )
        res = read(layout, "amt,cd,ac\n12345,20240115,yes\n", entity=entity)
        assert res.data == [{"amount": 123.45, "closed": "2024-01-15", "active": 1}]

    def test_bad_number_is_loud_with_location(self):
        entity = _entity(amount="currency")
        layout = parse_layout(
            {
                "layout": "D",
                "entity": "T",
                "format": {"kind": "delimited", "hasHeader": True},
                "mapping": [{"field": "amount", "column": "amt"}],
            }
        )
        with pytest.raises(LayoutReadError) as exc:
            read(layout, "amt\nNOPE\n", entity=entity)
        issue = exc.value.issues[0]
        assert issue.field == "amount" and issue.row == 2


# ---------------------------------------------------------------------------
# Loader + config validation
# ---------------------------------------------------------------------------


class TestLoader:
    def test_loads_from_dir(self, tmp_path):
        layouts = tmp_path / "layouts"
        layouts.mkdir()
        (layouts / "sample.yaml").write_text(
            "layout: Sample\n"
            "format:\n  kind: delimited\n  hasHeader: true\n"
            "mapping:\n  - field: a\n    column: a\n"
        )
        loader = LayoutLoader(layouts)
        loader.load_all()
        assert [lay.name for lay in loader.list_layouts()] == ["Sample"]
        assert loader.get_layout("Sample").format.has_header is True

    def test_reload(self, tmp_path):
        layouts = tmp_path / "layouts"
        layouts.mkdir()
        loader = LayoutLoader(layouts)
        loader.load_all()
        assert loader.list_layouts() == []
        (layouts / "s.yaml").write_text(
            "layout: S\nformat:\n  kind: fixed\n  recordLength: 3\n"
            "mapping:\n  - field: a\n    at: {offset: 0, width: 3}\n"
        )
        loader.reload()
        assert loader.get_layout("S") is not None

    def test_unknown_transform_is_loud(self):
        with pytest.raises(LayoutConfigError):
            parse_layout(
                {
                    "layout": "X",
                    "format": {"kind": "delimited"},
                    "mapping": [{"field": "a", "column": 0, "transform": [{"nope": {}}]}],
                }
            )

    def test_records_without_selector_is_loud(self):
        with pytest.raises(LayoutConfigError):
            parse_layout(
                {
                    "layout": "X",
                    "format": {"kind": "delimited"},
                    "records": [{"type": "D", "kind": "data", "mapping": []}],
                }
            )

    @pytest.mark.skipif(
        not (REPO_ROOT / "metadata" / "layouts").exists(),
        reason="repo metadata/layouts not present",
    )
    def test_repo_sample_layouts_load(self):
        loader = LayoutLoader(REPO_ROOT / "metadata" / "layouts")
        loader.load_all()
        names = {lay.name for lay in loader.list_layouts()}
        assert {"ContactCsv", "ContactFixed"} <= names


@pytest.mark.skipif(
    not (REPO_ROOT / "metadata" / "layouts").exists(),
    reason="repo metadata not present",
)
def test_repo_layouts_pass_schema_validation():
    from metaforge.metadata.validator import validate_metadata_dir

    issues = [i for i in validate_metadata_dir(REPO_ROOT / "metadata") if "layouts" in str(i.file)]
    assert issues == []
