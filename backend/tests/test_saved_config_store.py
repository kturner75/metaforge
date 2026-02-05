"""Tests for SavedConfigStore."""

import sqlite3
import pytest

from metaforge.views.types import (
    ConfigScope,
    ConfigSource,
    DataPattern,
    OwnerType,
    SavedConfig,
)
from metaforge.views.store import SavedConfigStore


@pytest.fixture
def conn():
    """Create in-memory database connection."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def store(conn):
    """Create config store with test connection."""
    return SavedConfigStore(conn)


def _make_config(**overrides) -> SavedConfig:
    """Helper to create a SavedConfig with sensible defaults."""
    defaults = dict(
        id="",
        name="Test Config",
        pattern=DataPattern.QUERY,
        style="grid",
        data_config={"sort": [{"field": "name", "direction": "asc"}]},
        style_config={"columns": [{"field": "name"}]},
        entity_name="Contact",
        source=ConfigSource.DATABASE,
    )
    defaults.update(overrides)
    return SavedConfig(**defaults)


class TestSavedConfigStoreTableCreation:
    """Tests for table initialization."""

    def test_creates_table(self, conn):
        """Store should create _saved_configs table on init."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_saved_configs'"
        )
        assert cursor.fetchone() is None

        SavedConfigStore(conn)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_saved_configs'"
        )
        assert cursor.fetchone() is not None

    def test_table_creation_is_idempotent(self, conn):
        """Creating multiple stores should not fail."""
        SavedConfigStore(conn)
        SavedConfigStore(conn)
        store = SavedConfigStore(conn)
        config = store.create(_make_config())
        assert config.id


class TestCreateAndGet:
    """Tests for create and get operations."""

    def test_create_generates_id(self, store):
        """Create should generate an ID when not provided."""
        config = store.create(_make_config())
        assert config.id
        assert len(config.id) == 32  # uuid4().hex

    def test_create_sets_timestamps(self, store):
        """Create should set created_at and updated_at."""
        config = store.create(_make_config())
        assert config.created_at is not None
        assert config.updated_at is not None

    def test_create_and_get_roundtrip(self, store):
        """Get should return the same config that was created."""
        original = _make_config(
            name="Roundtrip Test",
            entity_name="Contact",
            pattern=DataPattern.QUERY,
            style="grid",
            data_config={"pageSize": 50, "sort": [{"field": "name", "direction": "desc"}]},
            style_config={"columns": [{"field": "name"}, {"field": "email"}], "selectable": True},
        )
        created = store.create(original)
        fetched = store.get(created.id)

        assert fetched is not None
        assert fetched.name == "Roundtrip Test"
        assert fetched.entity_name == "Contact"
        assert fetched.pattern == DataPattern.QUERY
        assert fetched.style == "grid"
        assert fetched.data_config == {"pageSize": 50, "sort": [{"field": "name", "direction": "desc"}]}
        assert fetched.style_config == {"columns": [{"field": "name"}, {"field": "email"}], "selectable": True}

    def test_get_nonexistent_returns_none(self, store):
        """Get should return None for unknown IDs."""
        assert store.get("nonexistent") is None

    def test_create_preserves_explicit_id(self, store):
        """Create should use the provided ID if non-empty."""
        config = store.create(_make_config(id="yaml:contact-grid"))
        assert config.id == "yaml:contact-grid"


class TestUpdate:
    """Tests for update operations."""

    def test_update_name(self, store):
        """Update should change the name field."""
        created = store.create(_make_config(name="Original"))
        updated = store.update(created.id, {"name": "Updated"})

        assert updated is not None
        assert updated.name == "Updated"

    def test_update_data_config_only(self, store):
        """Update should allow changing just data_config."""
        created = store.create(_make_config(
            data_config={"pageSize": 25},
            style_config={"selectable": False},
        ))
        updated = store.update(created.id, {"data_config": {"pageSize": 50}})

        assert updated is not None
        assert updated.data_config == {"pageSize": 50}
        assert updated.style_config == {"selectable": False}  # Unchanged

    def test_update_style_config_only(self, store):
        """Update should allow changing just style_config."""
        created = store.create(_make_config(
            data_config={"pageSize": 25},
            style_config={"selectable": False},
        ))
        updated = store.update(created.id, {"style_config": {"selectable": True}})

        assert updated is not None
        assert updated.style_config == {"selectable": True}
        assert updated.data_config == {"pageSize": 25}  # Unchanged

    def test_update_bumps_version(self, store):
        """Update should increment the version number."""
        created = store.create(_make_config())
        assert created.version == 1

        updated = store.update(created.id, {"name": "V2"})
        assert updated is not None
        assert updated.version == 2

        updated2 = store.update(created.id, {"name": "V3"})
        assert updated2 is not None
        assert updated2.version == 3

    def test_update_nonexistent_returns_none(self, store):
        """Update should return None for unknown IDs."""
        assert store.update("nonexistent", {"name": "nope"}) is None

    def test_update_ignores_disallowed_fields(self, store):
        """Update should ignore fields not in the allowed set."""
        created = store.create(_make_config())
        updated = store.update(created.id, {"pattern": "aggregate", "entity_name": "Other"})

        assert updated is not None
        assert updated.pattern == DataPattern.QUERY  # Unchanged
        assert updated.entity_name == "Contact"  # Unchanged


class TestDelete:
    """Tests for delete operations."""

    def test_delete_existing(self, store):
        """Delete should remove the config and return True."""
        created = store.create(_make_config())
        assert store.delete(created.id) is True
        assert store.get(created.id) is None

    def test_delete_nonexistent(self, store):
        """Delete should return False for unknown IDs."""
        assert store.delete("nonexistent") is False


class TestList:
    """Tests for list operations with filtering."""

    def test_list_all(self, store):
        """List without filters should return all configs."""
        store.create(_make_config(name="A"))
        store.create(_make_config(name="B"))
        store.create(_make_config(name="C"))

        configs = store.list()
        assert len(configs) == 3

    def test_list_filter_by_entity_name(self, store):
        """List should filter by entity_name."""
        store.create(_make_config(name="Contact Grid", entity_name="Contact"))
        store.create(_make_config(name="Company Grid", entity_name="Company"))
        store.create(_make_config(name="Contact Chart", entity_name="Contact"))

        configs = store.list(entity_name="Contact")
        assert len(configs) == 2
        assert all(c.entity_name == "Contact" for c in configs)

    def test_list_filter_by_pattern(self, store):
        """List should filter by pattern."""
        store.create(_make_config(name="Query View", pattern=DataPattern.QUERY))
        store.create(_make_config(name="Aggregate View", pattern=DataPattern.AGGREGATE))

        configs = store.list(pattern="query")
        assert len(configs) == 1
        assert configs[0].name == "Query View"

    def test_list_filter_by_style(self, store):
        """List should filter by style."""
        store.create(_make_config(name="Grid", style="grid"))
        store.create(_make_config(name="Chart", style="barChart"))

        configs = store.list(style="grid")
        assert len(configs) == 1
        assert configs[0].name == "Grid"

    def test_list_ordered_by_name(self, store):
        """List should return configs ordered by name."""
        store.create(_make_config(name="Zebra"))
        store.create(_make_config(name="Alpha"))
        store.create(_make_config(name="Middle"))

        configs = store.list()
        names = [c.name for c in configs]
        assert names == ["Alpha", "Middle", "Zebra"]


class TestResolve:
    """Tests for config resolution with precedence."""

    def test_resolve_returns_user_config_over_global(self, store):
        """User personal config should take precedence over global."""
        store.create(_make_config(
            name="Global Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.GLOBAL,
            owner_type=OwnerType.GLOBAL,
        ))
        store.create(_make_config(
            name="My Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.PERSONAL,
            owner_type=OwnerType.USER,
            owner_id="user-1",
        ))

        result = store.resolve("Contact", "grid", user_id="user-1")
        assert result is not None
        assert result.name == "My Grid"

    def test_resolve_returns_role_config_over_global(self, store):
        """Role config should take precedence over global."""
        store.create(_make_config(
            name="Global Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.GLOBAL,
            owner_type=OwnerType.GLOBAL,
        ))
        store.create(_make_config(
            name="Admin Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.ROLE,
            owner_type=OwnerType.ROLE,
            owner_id="admin",
        ))

        result = store.resolve("Contact", "grid", role="admin")
        assert result is not None
        assert result.name == "Admin Grid"

    def test_resolve_user_over_role_over_global(self, store):
        """Full precedence: user > role > global."""
        store.create(_make_config(
            name="Global Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.GLOBAL,
            owner_type=OwnerType.GLOBAL,
        ))
        store.create(_make_config(
            name="Admin Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.ROLE,
            owner_type=OwnerType.ROLE,
            owner_id="admin",
        ))
        store.create(_make_config(
            name="My Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.PERSONAL,
            owner_type=OwnerType.USER,
            owner_id="user-1",
        ))

        result = store.resolve("Contact", "grid", user_id="user-1", role="admin")
        assert result is not None
        assert result.name == "My Grid"

    def test_resolve_falls_back_to_global(self, store):
        """Resolve should fall back to global when no user/role config exists."""
        store.create(_make_config(
            name="Global Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.GLOBAL,
            owner_type=OwnerType.GLOBAL,
        ))

        result = store.resolve("Contact", "grid", user_id="user-1", role="viewer")
        assert result is not None
        assert result.name == "Global Grid"

    def test_resolve_returns_none_when_no_match(self, store):
        """Resolve should return None when nothing matches."""
        result = store.resolve("Contact", "grid")
        assert result is None

    def test_resolve_yaml_fallback(self, store):
        """YAML-source configs should work as global fallback."""
        store.create(_make_config(
            id="yaml:contact-grid",
            name="YAML Grid",
            entity_name="Contact",
            style="grid",
            scope=ConfigScope.GLOBAL,
            owner_type=OwnerType.GLOBAL,
            source=ConfigSource.YAML,
        ))

        result = store.resolve("Contact", "grid")
        assert result is not None
        assert result.name == "YAML Grid"
        assert result.source == ConfigSource.YAML


class TestUpsertFromYaml:
    """Tests for YAML config upsert."""

    def test_upsert_creates_new(self, store):
        """upsert_from_yaml should create config if not exists."""
        config = _make_config(
            id="yaml:test",
            name="YAML Test",
            source=ConfigSource.YAML,
        )
        result = store.upsert_from_yaml(config)
        assert result.id == "yaml:test"
        assert result.name == "YAML Test"

    def test_upsert_updates_existing_yaml(self, store):
        """upsert_from_yaml should update existing YAML-source config."""
        config = _make_config(
            id="yaml:test",
            name="Original",
            source=ConfigSource.YAML,
        )
        store.upsert_from_yaml(config)

        updated_config = _make_config(
            id="yaml:test",
            name="Updated",
            source=ConfigSource.YAML,
        )
        result = store.upsert_from_yaml(updated_config)
        assert result.name == "Updated"

    def test_upsert_does_not_overwrite_db_config(self, store):
        """upsert_from_yaml should not overwrite a database-source config."""
        # Create a DB config with the same ID (edge case)
        db_config = _make_config(
            id="yaml:test",
            name="DB Override",
            source=ConfigSource.DATABASE,
        )
        store.create(db_config)

        # Try to upsert YAML - the UPDATE has WHERE source='yaml',
        # so the DB config should keep its name
        yaml_config = _make_config(
            id="yaml:test",
            name="YAML Original",
            source=ConfigSource.YAML,
        )
        result = store.upsert_from_yaml(yaml_config)
        assert result.name == "DB Override"


class TestToDict:
    """Tests for SavedConfig serialization."""

    def test_to_dict_camel_case(self, store):
        """to_dict should return camelCase keys."""
        created = store.create(_make_config(
            name="Serialization Test",
            entity_name="Contact",
        ))
        d = created.to_dict()

        assert "entityName" in d
        assert "dataConfig" in d
        assert "styleConfig" in d
        assert "ownerType" in d
        assert "createdAt" in d
        assert "updatedAt" in d
        assert d["entityName"] == "Contact"
        assert d["pattern"] == "query"
        assert d["source"] == "database"
