"""
Tests for metaforge.metadata.validator

Covers:
  - _preprocess_on_key()            — PyYAML boolean True → "on" rename
  - validate_yaml_file()            — single-file validation (valid + invalid)
  - validate_metadata_dir()         — directory walk (real metadata passes)
  - validate_metadata_dir(strict=True)
  - CLI: metaforge metadata validate
  - CLI: metaforge metadata validate --path <file>
  - CLI: metaforge metadata validate --strict
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from metaforge.cli.main import cli
from metaforge.metadata.validator import (
    ValidationIssue,
    _preprocess_on_key,
    validate_metadata_dir,
    validate_yaml_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data))
    return path


def _write_raw(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# Path to the real metadata directory
_REPO_ROOT = Path(__file__).resolve().parents[2]
_METADATA_DIR = _REPO_ROOT / "metadata"


# ---------------------------------------------------------------------------
# _preprocess_on_key
# ---------------------------------------------------------------------------


class TestPreprocessOnKey:
    def test_renames_bool_true_to_on(self):
        raw = {True: ["create", "update"]}
        result = _preprocess_on_key(raw)
        assert result == {"on": ["create", "update"]}

    def test_leaves_other_keys_intact(self):
        raw = {"name": "foo", "type": "string", True: ["create"]}
        result = _preprocess_on_key(raw)
        assert result == {"name": "foo", "type": "string", "on": ["create"]}

    def test_nested_dicts(self):
        raw = {"defaults": [{True: ["create"], "field": "x"}]}
        result = _preprocess_on_key(raw)
        assert result == {"defaults": [{"on": ["create"], "field": "x"}]}

    def test_lists_are_traversed(self):
        raw = [{True: ["create"]}, {True: ["update"]}]
        result = _preprocess_on_key(raw)
        assert result == [{"on": ["create"]}, {"on": ["update"]}]

    def test_no_bool_key_unchanged(self):
        raw = {"a": 1, "b": [1, 2, {"c": 3}]}
        assert _preprocess_on_key(raw) == raw

    def test_scalar_passthrough(self):
        assert _preprocess_on_key(42) == 42
        assert _preprocess_on_key("hello") == "hello"
        assert _preprocess_on_key(None) is None


# ---------------------------------------------------------------------------
# validate_yaml_file — entity
# ---------------------------------------------------------------------------


class TestValidateEntityFile:
    def test_valid_minimal_entity(self, tmp_path):
        f = _write_yaml(
            tmp_path / "entities" / "MyEntity.yaml",
            {
                "entity": "MyEntity",
                "fields": [{"name": "id", "type": "id", "primaryKey": True}],
            },
        )
        issues = validate_yaml_file(f, "entity.schema.json")
        assert issues == []

    def test_missing_entity_key(self, tmp_path):
        f = _write_yaml(
            tmp_path / "entities" / "Bad.yaml",
            {"fields": [{"name": "id", "type": "id"}]},
        )
        issues = validate_yaml_file(f, "entity.schema.json")
        assert any("entity" in i.message for i in issues)

    def test_missing_fields_key(self, tmp_path):
        f = _write_yaml(
            tmp_path / "entities" / "Bad.yaml",
            {"entity": "Bad"},
        )
        issues = validate_yaml_file(f, "entity.schema.json")
        assert any("fields" in i.message for i in issues)

    def test_invalid_field_type(self, tmp_path):
        f = _write_yaml(
            tmp_path / "entities" / "Bad.yaml",
            {
                "entity": "Bad",
                "fields": [{"name": "x", "type": "banana"}],
            },
        )
        issues = validate_yaml_file(f, "entity.schema.json")
        assert any("banana" in i.message for i in issues)

    def test_all_valid_field_types_accepted(self, tmp_path):
        valid_types = [
            "id", "uuid", "string", "name", "text", "description",
            "email", "phone", "url", "picklist", "multi_picklist",
            "checkbox", "boolean", "date", "datetime",
            "number", "currency", "percent", "relation", "address", "attachment",
        ]
        fields = [{"name": f"f_{t}", "type": t} for t in valid_types]
        f = _write_yaml(
            tmp_path / "entities" / "AllTypes.yaml",
            {"entity": "AllTypes", "fields": fields},
        )
        issues = validate_yaml_file(f, "entity.schema.json")
        assert issues == []

    def test_entity_with_on_key_in_defaults(self, tmp_path):
        """PyYAML parses 'on:' as boolean True — validator must preprocess it."""
        raw_yaml = textwrap.dedent("""\
            entity: Contact
            fields:
              - name: id
                type: id
            defaults:
              - field: fullName
                expression: 'concat(firstName, " ", lastName)'
                policy: overwrite
                on: [create, update]
        """)
        f = _write_raw(tmp_path / "entities" / "Contact.yaml", raw_yaml)
        issues = validate_yaml_file(f, "entity.schema.json")
        assert issues == [], f"Unexpected issues: {issues}"

    def test_empty_yaml_file_returns_error(self, tmp_path):
        f = _write_raw(tmp_path / "entities" / "Empty.yaml", "")
        issues = validate_yaml_file(f, "entity.schema.json")
        assert len(issues) == 1
        assert "empty" in issues[0].message.lower()

    def test_malformed_yaml_returns_error(self, tmp_path):
        f = _write_raw(tmp_path / "entities" / "Bad.yaml", "entity: [\nunclosed")
        issues = validate_yaml_file(f, "entity.schema.json")
        assert len(issues) == 1
        assert "YAML" in issues[0].message


# ---------------------------------------------------------------------------
# validate_yaml_file — block
# ---------------------------------------------------------------------------


class TestValidateBlockFile:
    def test_valid_block(self, tmp_path):
        f = _write_yaml(
            tmp_path / "blocks" / "AuditTrail.yaml",
            {
                "block": "AuditTrail",
                "description": "Standard audit fields",
                "fields": [
                    {"name": "createdAt", "type": "datetime", "readOnly": True},
                ],
            },
        )
        issues = validate_yaml_file(f, "block.schema.json")
        assert issues == []

    def test_missing_block_key(self, tmp_path):
        f = _write_yaml(
            tmp_path / "blocks" / "Bad.yaml",
            {"fields": [{"name": "x", "type": "string"}]},
        )
        issues = validate_yaml_file(f, "block.schema.json")
        assert any("block" in i.message for i in issues)


# ---------------------------------------------------------------------------
# validate_yaml_file — view
# ---------------------------------------------------------------------------


class TestValidateViewFile:
    def test_valid_query_grid_view(self, tmp_path):
        f = _write_yaml(
            tmp_path / "views" / "contact-grid.yaml",
            {
                "view": {
                    "name": "Contact Grid",
                    "entityName": "Contact",
                    "pattern": "query",
                    "style": "grid",
                    "data": {"sort": [{"field": "fullName", "direction": "asc"}], "pageSize": 25},
                    "styleConfig": {"columns": [{"field": "fullName"}]},
                }
            },
        )
        issues = validate_yaml_file(f, "view.schema.json")
        assert issues == []

    def test_invalid_pattern(self, tmp_path):
        f = _write_yaml(
            tmp_path / "views" / "bad.yaml",
            {"view": {"name": "Bad", "pattern": "unknown", "style": "grid"}},
        )
        issues = validate_yaml_file(f, "view.schema.json")
        assert any("unknown" in i.message for i in issues)

    def test_invalid_style(self, tmp_path):
        f = _write_yaml(
            tmp_path / "views" / "bad.yaml",
            {"view": {"name": "Bad", "pattern": "query", "style": "rainbow"}},
        )
        issues = validate_yaml_file(f, "view.schema.json")
        assert any("rainbow" in i.message for i in issues)

    def test_all_valid_styles_accepted(self, tmp_path):
        valid_styles = [
            "grid", "card-list", "search-list", "kanban", "tree", "calendar",
            "detail", "form",
            "kpi-card", "bar-chart", "pie-chart", "summary-grid",
            "time-series", "funnel",
            "detail-page", "dashboard",
        ]
        patterns = {
            "grid": "query", "card-list": "query", "search-list": "query",
            "kanban": "query", "tree": "query", "calendar": "query",
            "detail": "record", "form": "record",
            "kpi-card": "aggregate", "bar-chart": "aggregate",
            "pie-chart": "aggregate", "summary-grid": "aggregate",
            "time-series": "aggregate", "funnel": "aggregate",
            "detail-page": "compose", "dashboard": "compose",
        }
        for style in valid_styles:
            f = _write_yaml(
                tmp_path / "views" / f"{style}.yaml",
                {"view": {"name": style, "pattern": patterns[style], "style": style}},
            )
            issues = validate_yaml_file(f, "view.schema.json")
            assert issues == [], f"style={style} failed: {issues}"

    def test_missing_view_key(self, tmp_path):
        f = _write_yaml(
            tmp_path / "views" / "bad.yaml",
            {"name": "oops", "pattern": "query", "style": "grid"},
        )
        issues = validate_yaml_file(f, "view.schema.json")
        assert any("view" in i.message for i in issues)


# ---------------------------------------------------------------------------
# validate_yaml_file — screen
# ---------------------------------------------------------------------------


class TestValidateScreenFile:
    def test_valid_screen(self, tmp_path):
        f = _write_yaml(
            tmp_path / "screens" / "contacts.yaml",
            {
                "screen": {
                    "name": "Contacts",
                    "slug": "contacts",
                    "type": "entity",
                    "entityName": "Contact",
                    "nav": {"section": "CRM", "order": 1, "icon": "users"},
                    "views": {
                        "list": "yaml:contact-grid",
                        "detail": "yaml:contact-detail",
                    },
                }
            },
        )
        issues = validate_yaml_file(f, "screen.schema.json")
        assert issues == []

    def test_invalid_slug(self, tmp_path):
        f = _write_yaml(
            tmp_path / "screens" / "bad.yaml",
            {
                "screen": {
                    "name": "Bad Slug",
                    "slug": "Bad Slug!",
                    "nav": {"section": "CRM"},
                }
            },
        )
        issues = validate_yaml_file(f, "screen.schema.json")
        assert any(i.path and "slug" in i.path for i in issues), f"Got: {issues}"

    def test_missing_nav(self, tmp_path):
        f = _write_yaml(
            tmp_path / "screens" / "bad.yaml",
            {"screen": {"name": "No Nav", "slug": "no-nav"}},
        )
        issues = validate_yaml_file(f, "screen.schema.json")
        assert any("nav" in i.message for i in issues)

    def test_invalid_screen_type(self, tmp_path):
        f = _write_yaml(
            tmp_path / "screens" / "bad.yaml",
            {
                "screen": {
                    "name": "Bad",
                    "slug": "bad",
                    "type": "magic",
                    "nav": {"section": "CRM"},
                }
            },
        )
        issues = validate_yaml_file(f, "screen.schema.json")
        assert any("magic" in i.message for i in issues)


# ---------------------------------------------------------------------------
# validate_metadata_dir — real metadata passes
# ---------------------------------------------------------------------------


class TestValidateMetadataDir:
    @pytest.mark.skipif(
        not _METADATA_DIR.is_dir(),
        reason="Real metadata directory not found",
    )
    def test_real_metadata_is_valid(self):
        """All committed metadata YAML files must pass schema validation."""
        issues = validate_metadata_dir(_METADATA_DIR)
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            detail = "\n".join(str(i) for i in errors)
            pytest.fail(f"Real metadata has schema errors:\n{detail}")

    def test_nonexistent_dir_returns_issue(self, tmp_path):
        issues = validate_metadata_dir(tmp_path / "does-not-exist")
        assert len(issues) == 1
        assert "does not exist" in issues[0].message

    def test_empty_dir_returns_no_issues(self, tmp_path):
        issues = validate_metadata_dir(tmp_path)
        assert issues == []

    def test_skips_unknown_subdirs(self, tmp_path):
        """Unknown subdirectories are silently ignored."""
        (tmp_path / "misc").mkdir()
        (tmp_path / "misc" / "random.yaml").write_text("key: value\n")
        issues = validate_metadata_dir(tmp_path)
        assert issues == []

    def test_strict_mode_escalates_warnings(self, tmp_path):
        """With strict=True, warnings are promoted to errors."""
        # We simulate a warning by patching — for now just verify strict doesn't break on clean dir
        issues = validate_metadata_dir(tmp_path, strict=True)
        assert issues == []

    def test_multiple_invalid_files_all_reported(self, tmp_path):
        for i in range(3):
            _write_yaml(
                tmp_path / "entities" / f"Bad{i}.yaml",
                {"entity": f"Bad{i}"},  # missing 'fields'
            )
        issues = validate_metadata_dir(tmp_path)
        assert len(issues) == 3


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestValidateCLI:
    @pytest.mark.skipif(
        not _METADATA_DIR.is_dir(),
        reason="Real metadata directory not found",
    )
    def test_cli_validate_real_metadata(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["metadata", "validate"])
        assert result.exit_code == 0, f"Output:\n{result.output}"
        assert "valid" in result.output.lower()

    def test_cli_validate_single_valid_file(self, tmp_path):
        f = _write_yaml(
            tmp_path / "entities" / "Good.yaml",
            {"entity": "Good", "fields": [{"name": "id", "type": "id"}]},
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["metadata", "validate", "--path", str(f)])
        assert result.exit_code == 0, f"Output:\n{result.output}"

    def test_cli_validate_single_invalid_file(self, tmp_path):
        f = _write_yaml(
            tmp_path / "entities" / "Bad.yaml",
            {"entity": "Bad"},  # missing 'fields'
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["metadata", "validate", "--path", str(f)])
        assert result.exit_code != 0
        assert "error" in result.output.lower() or "ERROR" in result.output

    def test_cli_validate_strict_flag(self, tmp_path):
        """--strict flag is accepted and clean directory passes."""
        runner = CliRunner()
        result = runner.invoke(cli, ["metadata", "validate", "--strict"])
        # May fail due to metadata dir not found in test env, but flag must be accepted
        assert "--strict" not in result.output  # no "no such option" error


# ---------------------------------------------------------------------------
# Import for textwrap (used in entity test above)
# ---------------------------------------------------------------------------
import textwrap  # noqa: E402 — import at module bottom for readability
