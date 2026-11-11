"""Tests for MF-004: ``description`` and the namespaced ``extensions`` map.

Covers:
  - MetadataLoader keeps ``description`` and ``extensions`` on entities and fields
  - block-included fields carry their extensions, deep-copied per entity
  - malformed ``extensions`` fail at load time instead of being dropped
  - the JSON Schemas accept entity- and field-level extensions and reject bad shapes
  - the loader's namespace rule matches the schema's
  - /api/metadata/{entity} and the MCP get_entity_metadata tool return both
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from metaforge.metadata.loader import EXTENSION_NAMESPACE_PATTERN, MetadataLoader
from metaforge.metadata.validator import validate_yaml_file

ENTITY_WITH_EXTENSIONS = """\
entity: Employer
abbreviation: EMP
description: A company that sponsors a benefit plan.
extensions:
  hostapp:
    sections: [identity, contacts]
    collection:
      minRows: 1
  acme.reporting:
    owner: finance
fields:
  - name: id
    type: id
    primaryKey: true
  - name: ein
    type: string
    description: Federal Employer Identification Number.
    validation:
      pattern: "^\\\\d{2}-\\\\d{7}$"
    extensions:
      hostapp:
        help: "Format: 12-3456789."
        preferredSource: document
  - name: name
    type: name
"""

ADDRESS_BLOCK = """\
block: Address
fields:
  - name: street
    type: string
    description: Street line.
    extensions:
      hostapp:
        help: Number and street.
"""


def _entity_yaml(name: str, abbreviation: str) -> str:
    return f"""\
entity: {name}
abbreviation: {abbreviation}
includes:
  - block: Address
fields:
  - name: id
    type: id
    primaryKey: true
"""


@pytest.fixture
def metadata_dir(tmp_path: Path) -> Path:
    for sub in ("entities", "drafts", "blocks"):
        (tmp_path / sub).mkdir()
    return tmp_path


def _load(metadata_dir: Path, entity_yaml: str) -> MetadataLoader:
    (metadata_dir / "entities" / "entity.yaml").write_text(entity_yaml)
    loader = MetadataLoader(metadata_dir)
    loader.load_all()
    return loader


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class TestLoaderKeepsDescriptionAndExtensions:
    def test_entity_description_and_extensions(self, metadata_dir):
        entity = _load(metadata_dir, ENTITY_WITH_EXTENSIONS).get_entity("Employer")

        assert entity.description == "A company that sponsors a benefit plan."
        assert entity.extensions == {
            "hostapp": {"sections": ["identity", "contacts"], "collection": {"minRows": 1}},
            "acme.reporting": {"owner": "finance"},
        }
        assert entity.extension("hostapp")["sections"] == ["identity", "contacts"]

    def test_field_description_and_extensions(self, metadata_dir):
        entity = _load(metadata_dir, ENTITY_WITH_EXTENSIONS).get_entity("Employer")
        ein = next(f for f in entity.fields if f.name == "ein")

        assert ein.description == "Federal Employer Identification Number."
        assert ein.extension("hostapp") == {
            "help": "Format: 12-3456789.",
            "preferredSource": "document",
        }

    def test_defaults_when_absent(self, metadata_dir):
        entity = _load(metadata_dir, ENTITY_WITH_EXTENSIONS).get_entity("Employer")
        name = next(f for f in entity.fields if f.name == "name")

        assert name.description == ""
        assert name.extensions == {}
        assert name.extension("hostapp") == {}
        assert entity.extension("unknown") == {}

    def test_namespace_is_not_hardcoded(self, metadata_dir):
        """Any valid namespace key works, so a host can pick or rename its own."""
        yaml_text = ENTITY_WITH_EXTENSIONS.replace("hostapp:", "renamed_app:")
        entity = _load(metadata_dir, yaml_text).get_entity("Employer")

        assert "renamed_app" in entity.extensions
        assert "hostapp" not in entity.extensions

    def test_null_namespace_value_becomes_empty_object(self, metadata_dir):
        yaml_text = (
            "entity: Thing\nabbreviation: THG\n"
            "extensions:\n  hostapp:\n"
            "fields:\n  - name: id\n    type: id\n"
        )
        entity = _load(metadata_dir, yaml_text).get_entity("Thing")
        assert entity.extensions["hostapp"] == {}

    def test_block_fields_carry_extensions_as_independent_copies(self, metadata_dir):
        (metadata_dir / "blocks" / "address.yaml").write_text(ADDRESS_BLOCK)
        (metadata_dir / "entities" / "a.yaml").write_text(_entity_yaml("Alpha", "ALP"))
        (metadata_dir / "entities" / "b.yaml").write_text(_entity_yaml("Beta", "BET"))
        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        alpha_street = next(f for f in loader.get_entity("Alpha").fields if f.name == "street")
        beta_street = next(f for f in loader.get_entity("Beta").fields if f.name == "street")
        assert alpha_street.description == "Street line."
        assert alpha_street.extension("hostapp") == {"help": "Number and street."}

        alpha_street.extensions["hostapp"]["help"] = "changed"
        assert beta_street.extension("hostapp") == {"help": "Number and street."}
        assert loader.blocks["Address"][0]["extensions"]["hostapp"]["help"] == "Number and street."


class TestLoaderRejectsMalformedExtensions:
    @pytest.mark.parametrize(
        "extensions_yaml, message",
        [
            ("extensions: [hostapp]", "must be a map"),
            ("extensions:\n  HostApp:\n    a: 1", "must be lowercase"),
            ("extensions:\n  1app:\n    a: 1", "must be lowercase"),
            ("extensions:\n  hostapp: just-a-string", "extensions.hostapp must be an object"),
            ("extensions:\n  hostapp: [1, 2]", "extensions.hostapp must be an object"),
        ],
    )
    def test_entity_level(self, metadata_dir, extensions_yaml, message):
        yaml_text = (
            f"entity: Bad\nabbreviation: BAD\n{extensions_yaml}\n"
            "fields:\n  - name: id\n    type: id\n"
        )
        with pytest.raises(ValueError, match=message) as exc:
            _load(metadata_dir, yaml_text)
        assert "entity 'Bad'" in str(exc.value)

    def test_field_level_names_the_field(self, metadata_dir):
        yaml_text = (
            "entity: Bad\nabbreviation: BAD\nfields:\n"
            "  - name: code\n    type: string\n    extensions: nope\n"
        )
        with pytest.raises(ValueError, match="field 'Bad.code'"):
            _load(metadata_dir, yaml_text)


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data))
    return path


class TestSchemaAcceptsExtensions:
    def test_entity_and_field_extensions_are_valid(self, tmp_path):
        f = tmp_path / "entities" / "Employer.yaml"
        f.parent.mkdir(parents=True)
        f.write_text(ENTITY_WITH_EXTENSIONS)
        assert validate_yaml_file(f, "entity.schema.json") == []

    def test_entity_level_extensions_no_longer_rejected(self, tmp_path):
        """Before MF-004 the entity schema's additionalProperties:false rejected this."""
        f = _write(
            tmp_path / "entities" / "E.yaml",
            {
                "entity": "E",
                "extensions": {"hostapp": {"sections": ["a"]}},
                "fields": [{"name": "id", "type": "id"}],
            },
        )
        assert validate_yaml_file(f, "entity.schema.json") == []

    def test_block_field_extensions_are_valid(self, tmp_path):
        f = tmp_path / "blocks" / "address.yaml"
        f.parent.mkdir(parents=True)
        f.write_text(ADDRESS_BLOCK)
        assert validate_yaml_file(f, "block.schema.json") == []

    @pytest.mark.parametrize(
        "extensions",
        [
            {"HostApp": {"a": 1}},
            {"1app": {"a": 1}},
            {"hostapp": "string"},
            {"hostapp": [1, 2]},
            ["hostapp"],
        ],
    )
    def test_bad_entity_extensions_rejected(self, tmp_path, extensions):
        f = _write(
            tmp_path / "entities" / "E.yaml",
            {"entity": "E", "extensions": extensions, "fields": [{"name": "id", "type": "id"}]},
        )
        assert validate_yaml_file(f, "entity.schema.json") != []

    def test_bad_field_extensions_rejected(self, tmp_path):
        f = _write(
            tmp_path / "entities" / "E.yaml",
            {
                "entity": "E",
                "fields": [{"name": "id", "type": "id", "extensions": {"hostapp": 5}}],
            },
        )
        assert validate_yaml_file(f, "entity.schema.json") != []

    def test_loader_and_schema_share_the_namespace_rule(self):
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "src" / "metaforge" / "metadata" / "schemas" / "_defs.schema.json"
        )
        defs = json.loads(schema_path.read_text())["$defs"]
        pattern = defs["extensionsMap"]["propertyNames"]["pattern"]
        assert pattern == EXTENSION_NAMESPACE_PATTERN.pattern


# ---------------------------------------------------------------------------
# API and MCP
# ---------------------------------------------------------------------------


def _decorate_contact(monkeypatch, loader):
    """Give the sample Contact entity a description and extensions for one test."""
    contact = loader.get_entity("Contact")
    email = next(f for f in contact.fields if f.name == "email")
    monkeypatch.setattr(contact, "description", "A person we work with.")
    monkeypatch.setattr(contact, "extensions", {"hostapp": {"sections": ["basics"]}})
    monkeypatch.setattr(email, "description", "Work email address.")
    monkeypatch.setattr(email, "extensions", {"hostapp": {"help": "name@company.com"}})


class TestApiReturnsDescriptionAndExtensions:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("METAFORGE_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("METAFORGE_DISABLE_AUTH", "1")
        monkeypatch.chdir(Path(__file__).parent.parent)

        from fastapi.testclient import TestClient

        from metaforge.api.app import app

        with TestClient(app) as client:
            yield client

    def test_defaults_when_metadata_has_none(self, client):
        data = client.get("/api/metadata/Contact").json()
        assert data["description"] == ""
        assert data["extensions"] == {}
        first_name = next(f for f in data["fields"] if f["name"] == "firstName")
        assert first_name["description"] == ""
        assert first_name["extensions"] == {}

    def test_returns_entity_and_field_values(self, client, monkeypatch):
        # metaforge.api re-exports the FastAPI instance as ``app``, which shadows
        # the module on attribute access, so look the module up directly.
        app_module = sys.modules["metaforge.api.app"]

        _decorate_contact(monkeypatch, app_module.metadata_loader)
        data = client.get("/api/metadata/Contact").json()

        assert data["description"] == "A person we work with."
        assert data["extensions"] == {"hostapp": {"sections": ["basics"]}}
        email = next(f for f in data["fields"] if f["name"] == "email")
        assert email["description"] == "Work email address."
        assert email["extensions"] == {"hostapp": {"help": "name@company.com"}}


class TestMcpReturnsDescriptionAndExtensions:
    @pytest.fixture
    def services(self, tmp_path, monkeypatch):
        import metaforge.mcp.server as server_module

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("METAFORGE_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.chdir(Path(__file__).parent.parent)
        server_module._services = None
        svc = server_module._get_services()
        try:
            yield svc
        finally:
            if svc.db:
                svc.db.close()
            server_module._services = None

    def test_returns_entity_and_field_values(self, services, monkeypatch):
        import metaforge.mcp.server as server_module

        _decorate_contact(monkeypatch, services.metadata_loader)
        result = server_module.get_entity_metadata.fn("Contact")

        assert result["description"] == "A person we work with."
        assert result["extensions"] == {"hostapp": {"sections": ["basics"]}}
        email = next(f for f in result["fields"] if f["name"] == "email")
        assert email["description"] == "Work email address."
        assert email["extensions"] == {"hostapp": {"help": "name@company.com"}}
