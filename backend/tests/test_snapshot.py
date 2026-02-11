"""Tests for schema snapshot creation and serialization."""

import json
from pathlib import Path

import pytest

from metaforge.metadata.loader import MetadataLoader
from metaforge.migrations.snapshot import (
    EntitySnapshot,
    FieldSnapshot,
    SchemaSnapshot,
    create_snapshot_from_metadata,
    load_snapshot,
    save_snapshot,
)


@pytest.fixture
def metadata_loader():
    """Load the real metadata from the project."""
    cwd = Path.cwd()
    if cwd.name == "backend":
        base_path = cwd.parent
    else:
        base_path = cwd
    metadata_path = base_path / "metadata"
    loader = MetadataLoader(metadata_path)
    loader.load_all()
    return loader


class TestFieldSnapshot:
    def test_to_dict_minimal(self):
        fs = FieldSnapshot(name="email", type="email", storage_type="TEXT")
        d = fs.to_dict()
        assert d == {"name": "email", "type": "email", "storage_type": "TEXT"}
        assert "required" not in d
        assert "primary_key" not in d

    def test_to_dict_full(self):
        fs = FieldSnapshot(
            name="id", type="id", storage_type="TEXT",
            required=True, primary_key=True, max_length=100,
        )
        d = fs.to_dict()
        assert d["required"] is True
        assert d["primary_key"] is True
        assert d["max_length"] == 100

    def test_round_trip(self):
        original = FieldSnapshot(
            name="name", type="name", storage_type="TEXT",
            required=True, max_length=200,
        )
        restored = FieldSnapshot.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.type == original.type
        assert restored.storage_type == original.storage_type
        assert restored.required == original.required
        assert restored.max_length == original.max_length
        assert restored.primary_key == original.primary_key


class TestEntitySnapshot:
    def test_round_trip(self):
        original = EntitySnapshot(
            name="Contact",
            table_name="contact",
            scope="tenant",
            fields={
                "id": FieldSnapshot("id", "id", "TEXT", primary_key=True),
                "email": FieldSnapshot("email", "email", "TEXT"),
            },
        )
        restored = EntitySnapshot.from_dict(original.to_dict())
        assert restored.name == "Contact"
        assert restored.table_name == "contact"
        assert restored.scope == "tenant"
        assert len(restored.fields) == 2
        assert restored.fields["id"].primary_key is True


class TestSchemaSnapshot:
    def test_empty(self):
        snap = SchemaSnapshot.empty()
        assert snap.version == 0
        assert snap.entities == {}

    def test_round_trip(self):
        original = SchemaSnapshot(
            version=3,
            generated_at="2024-01-01T00:00:00",
            entities={
                "Contact": EntitySnapshot(
                    name="Contact",
                    table_name="contact",
                    scope="tenant",
                    fields={
                        "id": FieldSnapshot("id", "id", "TEXT", primary_key=True),
                    },
                ),
            },
        )
        d = original.to_dict()
        restored = SchemaSnapshot.from_dict(d)
        assert restored.version == 3
        assert "Contact" in restored.entities
        assert restored.entities["Contact"].fields["id"].primary_key is True


class TestCreateSnapshotFromMetadata:
    def test_creates_snapshot_with_all_entities(self, metadata_loader):
        snap = create_snapshot_from_metadata(metadata_loader)
        entity_names = set(snap.entities.keys())
        assert "Contact" in entity_names
        assert "Company" in entity_names
        assert "User" in entity_names
        assert "Tenant" in entity_names

    def test_contact_fields(self, metadata_loader):
        snap = create_snapshot_from_metadata(metadata_loader)
        contact = snap.entities["Contact"]
        assert contact.table_name == "contact"
        assert contact.scope == "tenant"
        assert "id" in contact.fields
        assert "firstName" in contact.fields
        assert "email" in contact.fields
        assert contact.fields["id"].primary_key is True
        assert contact.fields["firstName"].required is True
        assert contact.fields["firstName"].storage_type == "TEXT"

    def test_numeric_field_types(self, metadata_loader):
        """Verify storage type mapping for various field types."""
        snap = create_snapshot_from_metadata(metadata_loader)
        # User.active is a checkbox → INTEGER
        user = snap.entities["User"]
        assert user.fields["active"].storage_type == "INTEGER"

    def test_generated_at_is_set(self, metadata_loader):
        snap = create_snapshot_from_metadata(metadata_loader)
        assert snap.generated_at != ""


class TestSnapshotFileIO:
    def test_save_and_load(self, tmp_path, metadata_loader):
        snap = create_snapshot_from_metadata(metadata_loader)
        snap.version = 5

        path = tmp_path / "schema_snapshot.json"
        save_snapshot(snap, path)

        loaded = load_snapshot(path)
        assert loaded.version == 5
        assert set(loaded.entities.keys()) == set(snap.entities.keys())

    def test_load_nonexistent_returns_empty(self, tmp_path):
        path = tmp_path / "does_not_exist.json"
        loaded = load_snapshot(path)
        assert loaded.version == 0
        assert loaded.entities == {}

    def test_saved_file_is_valid_json(self, tmp_path, metadata_loader):
        snap = create_snapshot_from_metadata(metadata_loader)
        path = tmp_path / "schema_snapshot.json"
        save_snapshot(snap, path)

        with open(path) as f:
            data = json.load(f)
        assert "entities" in data
        assert "version" in data
