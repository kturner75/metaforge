"""Tests for MCP sandbox tools: draft_entity, update_draft_entity, generate_fake_data.

The fixture boots services against a minimal isolated metadata directory so
tests never touch the real ``metadata/`` tree.
"""

import os
import textwrap
from pathlib import Path

import pytest

import metaforge.mcp.server as server_module


# ---------------------------------------------------------------------------
# Minimal entity YAML templates
# ---------------------------------------------------------------------------


_WIDGET_YAML = textwrap.dedent("""\
    entity: Widget
    abbreviation: WGT
    displayName: Widget
    pluralName: Widgets
    fields:
      - name: id
        type: id
        displayName: ID
        primaryKey: true
      - name: name
        type: name
        displayName: Name
      - name: status
        type: picklist
        displayName: Status
        options:
          - value: new
            label: New
          - value: active
            label: Active
      - name: price
        type: currency
        displayName: Price
""")

_GADGET_YAML = textwrap.dedent("""\
    entity: Gadget
    abbreviation: GDG
    displayName: Gadget
    pluralName: Gadgets
    fields:
      - name: id
        type: id
        displayName: ID
        primaryKey: true
      - name: name
        type: name
        displayName: Name
      - name: description
        type: description
        displayName: Description
""")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox_services(tmp_path):
    """Boot MetaForge services against an isolated tmp_path metadata directory."""
    saved_db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["METAFORGE_DB_PATH"] = str(tmp_path / "test.db")

    # Create a minimal metadata tree (no live entities — just directories)
    meta = tmp_path / "metadata"
    (meta / "entities").mkdir(parents=True)
    (meta / "blocks").mkdir(parents=True)
    (meta / "views").mkdir(parents=True)
    (meta / "screens").mkdir(parents=True)
    (meta / "drafts").mkdir(parents=True)

    # initialize_services() resolves base_path from CWD:
    # base_path = cwd.parent if cwd.name == "backend" else cwd
    # We set CWD to tmp_path so base_path == tmp_path.
    original_cwd = Path.cwd()
    os.chdir(tmp_path)

    server_module._services = None

    svc = None
    try:
        svc = server_module._get_services()
        yield svc
    finally:
        if svc and svc.db:
            svc.db.close()
        if svc and svc.draft_db:
            svc.draft_db.close()
        server_module._services = None
        os.chdir(original_cwd)
        os.environ.pop("METAFORGE_DB_PATH", None)
        if saved_db_url is not None:
            os.environ["DATABASE_URL"] = saved_db_url


# Shortcuts to underlying tool functions
_draft_entity = server_module.draft_entity.fn
_update_draft_entity = server_module.update_draft_entity.fn
_generate_fake_data = server_module.generate_fake_data.fn
_get_entity_metadata = server_module.get_entity_metadata.fn
_query_records = server_module.query_records.fn


# ---------------------------------------------------------------------------
# draft_entity
# ---------------------------------------------------------------------------


class TestDraftEntity:
    def test_creates_entity_from_valid_yaml(self, sandbox_services):
        result = _draft_entity(_WIDGET_YAML)
        assert "error" not in result
        assert result["entity"] == "Widget"
        assert result["isDraft"] is True

    def test_returns_field_list(self, sandbox_services):
        result = _draft_entity(_WIDGET_YAML)
        field_names = [f["name"] for f in result["fields"]]
        assert "name" in field_names
        assert "status" in field_names
        assert "price" in field_names

    def test_returns_reload_counts(self, sandbox_services):
        result = _draft_entity(_WIDGET_YAML)
        assert "reloaded" in result
        assert "entities" in result["reloaded"]

    def test_entity_is_queryable_after_creation(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _query_records("Widget")
        assert "data" in result
        assert result["data"] == []

    def test_entity_appears_in_metadata(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        meta = _get_entity_metadata("Widget")
        assert meta["entity"] == "Widget"

    def test_rejects_invalid_yaml(self, sandbox_services):
        result = _draft_entity("not: valid: yaml: [[[")
        assert "error" in result

    def test_rejects_yaml_without_entity_key(self, sandbox_services):
        result = _draft_entity("abbreviation: WGT\nfields: []")
        assert "error" in result

    def test_rejects_yaml_without_abbreviation(self, sandbox_services):
        result = _draft_entity("entity: Widget\nfields: []")
        assert "error" in result

    def test_can_create_multiple_draft_entities(self, sandbox_services):
        r1 = _draft_entity(_WIDGET_YAML)
        r2 = _draft_entity(_GADGET_YAML)
        assert "error" not in r1
        assert "error" not in r2
        assert r1["entity"] == "Widget"
        assert r2["entity"] == "Gadget"

    def test_overwrites_existing_draft(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        updated_yaml = textwrap.dedent("""\
            entity: Widget
            abbreviation: WGT
            displayName: Widget
            pluralName: Widgets
            fields:
              - name: id
                type: id
                displayName: ID
                primaryKey: true
              - name: name
                type: name
                displayName: Name
              - name: notes
                type: text
                displayName: Notes
        """)
        result = _draft_entity(updated_yaml)
        assert "error" not in result
        field_names = [f["name"] for f in result["fields"]]
        assert "notes" in field_names


# ---------------------------------------------------------------------------
# update_draft_entity
# ---------------------------------------------------------------------------


class TestUpdateDraftEntity:
    def test_updates_existing_draft(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        updated_yaml = textwrap.dedent("""\
            entity: Widget
            abbreviation: WGT
            displayName: Widget
            pluralName: Widgets
            fields:
              - name: id
                type: id
                displayName: ID
                primaryKey: true
              - name: name
                type: name
                displayName: Name
              - name: sku
                type: text
                displayName: SKU
        """)
        result = _update_draft_entity("Widget", updated_yaml)
        assert "error" not in result
        field_names = [f["name"] for f in result["fields"]]
        assert "sku" in field_names

    def test_returns_error_when_draft_does_not_exist(self, sandbox_services):
        result = _update_draft_entity("NonExistent", _WIDGET_YAML)
        assert "error" in result

    def test_rejects_invalid_yaml(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _update_draft_entity("Widget", "not: valid: yaml: [[[")
        assert "error" in result

    def test_rejects_yaml_missing_entity_key(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _update_draft_entity("Widget", "abbreviation: WGT\nfields: []")
        assert "error" in result

    def test_updated_entity_is_queryable(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        updated_yaml = _WIDGET_YAML.replace("displayName: Widget", "displayName: Widget v2")
        _update_draft_entity("Widget", updated_yaml)
        meta = _get_entity_metadata("Widget")
        assert meta["displayName"] == "Widget v2"


# ---------------------------------------------------------------------------
# generate_fake_data
# ---------------------------------------------------------------------------


class TestGenerateFakeData:
    def test_generates_requested_count(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _generate_fake_data("Widget", count=5)
        assert "error" not in result
        assert result["count"] == 5
        assert len(result["records"]) == 5

    def test_records_have_generated_ids(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _generate_fake_data("Widget", count=3)
        for r in result["records"]:
            assert r["id"].startswith("WGT-")

    def test_picklist_values_are_valid(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _generate_fake_data("Widget", count=10, seed=42)
        valid = {"new", "active"}
        for r in result["records"]:
            assert r["status"] in valid

    def test_records_persisted_in_draft_db(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        _generate_fake_data("Widget", count=7)
        result = _query_records("Widget")
        assert result["pagination"]["total"] == 7

    def test_rejects_non_draft_entity(self, sandbox_services):
        result = _generate_fake_data("Contact")  # Contact is not in isolated services
        assert "error" in result

    def test_rejects_count_zero(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _generate_fake_data("Widget", count=0)
        assert "error" in result

    def test_rejects_count_above_max(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _generate_fake_data("Widget", count=501)
        assert "error" in result

    def test_seed_produces_reproducible_records(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        r1 = _generate_fake_data("Widget", count=3, seed=7)
        r2 = _generate_fake_data("Widget", count=3, seed=7)
        names1 = [r["name"] for r in r1["records"]]
        names2 = [r["name"] for r in r2["records"]]
        assert names1 == names2

    def test_locale_parameter_accepted(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _generate_fake_data("Widget", count=3, locale="de_DE")
        assert "error" not in result
        assert result["count"] == 3

    def test_entity_field_is_returned(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        result = _generate_fake_data("Widget", count=2)
        assert result["entity"] == "Widget"

    def test_generates_for_second_draft_entity(self, sandbox_services):
        _draft_entity(_WIDGET_YAML)
        _draft_entity(_GADGET_YAML)
        result = _generate_fake_data("Gadget", count=4)
        assert "error" not in result
        assert result["count"] == 4
        assert result["entity"] == "Gadget"
