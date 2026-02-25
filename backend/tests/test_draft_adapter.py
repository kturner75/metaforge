"""Tests for DraftAdapter and draft DB isolation."""

import pytest
from pathlib import Path

from metaforge.persistence.draft import DraftAdapter
from metaforge.persistence.sqlite import SQLiteAdapter
from metaforge.metadata.loader import EntityModel, FieldDefinition, ValidationRules


def _minimal_entity(name: str = "Widget", abbrev: str = "WGT") -> EntityModel:
    """Build a minimal EntityModel for testing."""
    return EntityModel(
        name=name,
        display_name=name,
        plural_name=name + "s",
        primary_key="id",
        fields=[
            FieldDefinition(
                name="id",
                type="id",
                display_name="ID",
                primary_key=True,
            ),
            FieldDefinition(
                name="name",
                type="name",
                display_name="Name",
            ),
        ],
        abbreviation=abbrev,
    )


class TestDraftAdapterClass:
    """DraftAdapter class-level properties."""

    def test_is_subclass_of_sqlite_adapter(self):
        assert issubclass(DraftAdapter, SQLiteAdapter)

    def test_from_base_path_returns_draft_adapter(self, tmp_path):
        adapter = DraftAdapter.from_base_path(tmp_path)
        assert isinstance(adapter, DraftAdapter)

    def test_from_base_path_targets_data_subdir(self, tmp_path):
        adapter = DraftAdapter.from_base_path(tmp_path)
        assert adapter.db_path == str(tmp_path / "data" / "draft.db")

    def test_from_base_path_creates_data_dir(self, tmp_path):
        data_dir = tmp_path / "data"
        assert not data_dir.exists()

        DraftAdapter.from_base_path(tmp_path)

        assert data_dir.exists()

    def test_explicit_path_constructor(self, tmp_path):
        path = tmp_path / "custom_draft.db"
        adapter = DraftAdapter(str(path))
        assert adapter.db_path == str(path)


class TestDraftAdapterCRUD:
    """DraftAdapter can connect and perform CRUD operations."""

    @pytest.fixture
    def adapter(self, tmp_path):
        a = DraftAdapter.from_base_path(tmp_path)
        a.connect()
        yield a
        a.close()

    @pytest.fixture
    def entity(self):
        return _minimal_entity()

    def test_connect_creates_db_file(self, tmp_path):
        adapter = DraftAdapter.from_base_path(tmp_path)
        adapter.connect()
        assert (tmp_path / "data" / "draft.db").exists()
        adapter.close()

    def test_initialize_entity_creates_table(self, adapter, entity):
        adapter.initialize_entity(entity)
        cursor = adapter.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='widget'"
        )
        assert cursor.fetchone() is not None

    def test_create_and_get_record(self, adapter, entity):
        adapter.initialize_entity(entity)
        created = adapter.create(entity, {"name": "Draft Widget"})
        assert created["name"] == "Draft Widget"
        assert created["id"].startswith("WGT-")

        fetched = adapter.get(entity, created["id"])
        assert fetched is not None
        assert fetched["name"] == "Draft Widget"

    def test_update_record(self, adapter, entity):
        adapter.initialize_entity(entity)
        created = adapter.create(entity, {"name": "Original"})
        updated = adapter.update(entity, created["id"], {"name": "Updated"})
        assert updated["name"] == "Updated"

    def test_delete_record(self, adapter, entity):
        adapter.initialize_entity(entity)
        created = adapter.create(entity, {"name": "To Delete"})
        success = adapter.delete(entity, created["id"])
        assert success is True
        assert adapter.get(entity, created["id"]) is None

    def test_query_records(self, adapter, entity):
        adapter.initialize_entity(entity)
        adapter.create(entity, {"name": "A"})
        adapter.create(entity, {"name": "B"})
        result = adapter.query(entity)
        assert result["pagination"]["total"] == 2


class TestDraftIsolation:
    """Draft data is isolated from the main DB."""

    def test_draft_and_main_use_separate_files(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        main_path = data_dir / "metaforge.db"
        draft_path = data_dir / "draft.db"

        main_db = SQLiteAdapter(str(main_path))
        main_db.connect()

        draft_adapter = DraftAdapter.from_base_path(tmp_path)
        draft_adapter.connect()

        # Both should exist and be different files
        assert main_path.exists()
        assert draft_path.exists()
        assert main_path != draft_path

        main_db.close()
        draft_adapter.close()

    def test_records_in_draft_db_dont_appear_in_main_db(self, tmp_path):
        entity = _minimal_entity()

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        main_db = SQLiteAdapter(str(data_dir / "main.db"))
        main_db.connect()
        main_db.initialize_entity(entity)

        draft_adapter = DraftAdapter.from_base_path(tmp_path)
        draft_adapter.connect()
        draft_adapter.initialize_entity(entity)

        # Create a record in draft only
        draft_adapter.create(entity, {"name": "Draft Only"})

        main_result = main_db.query(entity)
        draft_result = draft_adapter.query(entity)

        assert main_result["pagination"]["total"] == 0
        assert draft_result["pagination"]["total"] == 1

        main_db.close()
        draft_adapter.close()
