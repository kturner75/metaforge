"""Tests for PersistenceAdapter Protocol and DatabaseConfig."""

import os

import pytest

from metaforge.persistence.adapter import PersistenceAdapter
from metaforge.persistence.config import DatabaseConfig, create_adapter
from metaforge.persistence.postgresql import PostgreSQLAdapter
from metaforge.persistence.sqlite import SQLiteAdapter


class TestPersistenceAdapterProtocol:
    """Verify SQLiteAdapter satisfies the PersistenceAdapter protocol."""

    def test_sqlite_adapter_is_instance(self):
        adapter = SQLiteAdapter(":memory:")
        assert isinstance(adapter, PersistenceAdapter)

    def test_sqlite_adapter_has_all_methods(self):
        """Verify all Protocol methods exist on SQLiteAdapter."""
        required_methods = [
            "connect",
            "close",
            "initialize_entity",
            "create",
            "get",
            "update",
            "delete",
            "query",
            "aggregate",
            "hydrate_relations",
            "handle_delete_relations",
        ]
        adapter = SQLiteAdapter(":memory:")
        for method_name in required_methods:
            assert hasattr(adapter, method_name), f"Missing method: {method_name}"
            assert callable(getattr(adapter, method_name))

    def test_sqlite_adapter_has_conn_attribute(self):
        adapter = SQLiteAdapter(":memory:")
        # Before connect, conn is None
        assert adapter.conn is None
        adapter.connect()
        assert adapter.conn is not None
        adapter.close()


class TestDatabaseConfig:
    """Test DatabaseConfig creation from environment."""

    def test_from_env_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.delenv("METAFORGE_DB_PATH", raising=False)
        config = DatabaseConfig.from_env()
        assert config.url == "postgresql://user:pass@localhost/db"
        assert config.is_postgresql
        assert not config.is_sqlite

    def test_from_env_metaforge_db_path(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("METAFORGE_DB_PATH", "/tmp/test.db")
        config = DatabaseConfig.from_env()
        assert config.url == "sqlite:////tmp/test.db"
        assert config.is_sqlite
        assert not config.is_postgresql

    def test_from_env_database_url_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///override.db")
        monkeypatch.setenv("METAFORGE_DB_PATH", "/tmp/ignored.db")
        config = DatabaseConfig.from_env()
        assert config.url == "sqlite:///override.db"

    def test_from_env_with_base_path(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("METAFORGE_DB_PATH", raising=False)
        config = DatabaseConfig.from_env(base_path=tmp_path)
        expected = f"sqlite:///{tmp_path / 'data' / 'metaforge.db'}"
        assert config.url == expected

    def test_from_env_no_env_no_base(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("METAFORGE_DB_PATH", raising=False)
        config = DatabaseConfig.from_env()
        assert config.url == "sqlite:///metaforge.db"

    def test_sqlalchemy_url_sqlite_unchanged(self):
        config = DatabaseConfig(url="sqlite:///test.db")
        assert config.sqlalchemy_url == "sqlite:///test.db"

    def test_sqlalchemy_url_postgresql_adds_psycopg_driver(self):
        config = DatabaseConfig(url="postgresql://user:pass@localhost/db")
        assert config.sqlalchemy_url == "postgresql+psycopg://user:pass@localhost/db"

    def test_sqlalchemy_url_postgresql_psycopg_unchanged(self):
        config = DatabaseConfig(url="postgresql+psycopg://user:pass@localhost/db")
        assert config.sqlalchemy_url == "postgresql+psycopg://user:pass@localhost/db"


class TestCreateAdapter:
    """Test adapter factory."""

    def test_create_sqlite_adapter(self):
        config = DatabaseConfig(url="sqlite:///test.db")
        adapter = create_adapter(config)
        assert isinstance(adapter, SQLiteAdapter)

    def test_create_sqlite_memory_adapter(self):
        config = DatabaseConfig(url="sqlite:///")
        adapter = create_adapter(config)
        assert isinstance(adapter, SQLiteAdapter)

    def test_create_postgresql_returns_adapter(self):
        config = DatabaseConfig(url="postgresql://user:pass@localhost/db")
        adapter = create_adapter(config)
        assert isinstance(adapter, PostgreSQLAdapter)

    def test_create_unsupported_raises(self):
        config = DatabaseConfig(url="mysql://localhost/db")
        with pytest.raises(ValueError, match="Unsupported"):
            create_adapter(config)

    def test_created_adapter_satisfies_protocol(self):
        config = DatabaseConfig(url="sqlite:///:memory:")
        adapter = create_adapter(config)
        assert isinstance(adapter, PersistenceAdapter)
