"""Tests for PostgreSQLAdapter.

Protocol conformance tests run without a real PostgreSQL server.
Full CRUD tests are skipped unless DATABASE_URL points to PostgreSQL.

Run with a real database:
    DATABASE_URL=postgresql://user:pass@localhost/testdb pytest tests/test_postgresql_adapter.py
"""

from __future__ import annotations

import os

import pytest

from metaforge.persistence.adapter import PersistenceAdapter
from metaforge.persistence.config import DatabaseConfig, create_adapter
from metaforge.persistence.postgresql import PostgreSQLAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PG_URL = os.environ.get("DATABASE_URL", "")
_HAS_PG = _PG_URL.startswith("postgresql")


def _pg_url() -> str:
    """Return the PostgreSQL URL or skip the test."""
    if not _HAS_PG:
        pytest.skip("DATABASE_URL is not a postgresql:// URL — skipping live tests")
    return _PG_URL


# ---------------------------------------------------------------------------
# Protocol conformance (no live DB required)
# ---------------------------------------------------------------------------


class TestPostgreSQLAdapterProtocol:
    """Verify PostgreSQLAdapter satisfies the PersistenceAdapter protocol."""

    def test_postgresql_adapter_is_instance(self):
        adapter = PostgreSQLAdapter("postgresql://user:pass@localhost/db")
        assert isinstance(adapter, PersistenceAdapter)

    def test_postgresql_adapter_has_all_methods(self):
        """All protocol methods must exist on PostgreSQLAdapter."""
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
            "create_no_commit",
            "update_no_commit",
            "delete_no_commit",
            "commit",
            "rollback",
        ]
        adapter = PostgreSQLAdapter("postgresql://user:pass@localhost/db")
        for method_name in required_methods:
            assert hasattr(adapter, method_name), f"Missing method: {method_name}"
            assert callable(getattr(adapter, method_name))

    def test_postgresql_adapter_conn_starts_none(self):
        adapter = PostgreSQLAdapter("postgresql://user:pass@localhost/db")
        assert adapter.conn is None

    def test_create_adapter_returns_postgresql_adapter(self):
        config = DatabaseConfig(url="postgresql://user:pass@localhost/db")
        adapter = create_adapter(config)
        assert isinstance(adapter, PostgreSQLAdapter)

    def test_create_adapter_psycopg_url_returns_postgresql_adapter(self):
        config = DatabaseConfig(url="postgresql+psycopg://user:pass@localhost/db")
        adapter = create_adapter(config)
        assert isinstance(adapter, PostgreSQLAdapter)


# ---------------------------------------------------------------------------
# Live integration tests (require DATABASE_URL=postgresql://...)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_adapter():
    """Create a connected PostgreSQLAdapter for integration tests."""
    url = _pg_url()
    config = DatabaseConfig(url=url)
    adapter = create_adapter(config)
    adapter.connect()
    yield adapter
    adapter.close()


@pytest.fixture(scope="module")
def pg_entity():
    """A minimal EntityModel-like object for testing."""
    from unittest.mock import MagicMock

    entity = MagicMock()
    entity.name = "PgTestEntity"
    entity.plural_name = "PgTestEntities"
    entity.abbreviation = "PTE"
    entity.scope = "global"
    entity.primary_key = "id"

    # Build realistic FieldDefinition-like mocks
    def make_field(name, ftype="TEXT", pk=False, required=False):
        f = MagicMock()
        f.name = name
        f.type = "text"
        f.primary_key = pk
        f.validation = MagicMock()
        f.validation.required = required
        f.relation = None
        return f

    entity.fields = [
        make_field("id", pk=True, required=True),
        make_field("name", required=True),
        make_field("email"),
        make_field("createdAt"),
        make_field("updatedAt"),
    ]
    return entity


@pytest.mark.skipif(not _HAS_PG, reason="No PostgreSQL DATABASE_URL configured")
class TestPostgreSQLAdapterLive:
    """Full CRUD integration tests against a real PostgreSQL database."""

    def test_connect_and_close(self):
        url = _pg_url()
        adapter = PostgreSQLAdapter(url)
        adapter.connect()
        assert adapter.conn is not None
        adapter.close()
        assert adapter.conn is None

    def test_initialize_entity(self, pg_adapter, pg_entity):
        """initialize_entity should create the table idempotently."""
        pg_adapter.initialize_entity(pg_entity)
        # Second call must not raise
        pg_adapter.initialize_entity(pg_entity)

    def test_create_and_get(self, pg_adapter, pg_entity):
        """Create should insert and return the new record."""
        pg_adapter.initialize_entity(pg_entity)

        record = pg_adapter.create(pg_entity, {"name": "Alice", "email": "alice@example.com"})
        assert record is not None
        assert record["name"] == "Alice"
        assert "id" in record
        assert record["id"].startswith("PTE-")

        # Get it back
        fetched = pg_adapter.get(pg_entity, record["id"])
        assert fetched is not None
        assert fetched["name"] == "Alice"
        assert fetched["email"] == "alice@example.com"

    def test_update(self, pg_adapter, pg_entity):
        """Update should modify specified fields."""
        pg_adapter.initialize_entity(pg_entity)

        record = pg_adapter.create(pg_entity, {"name": "Bob"})
        updated = pg_adapter.update(pg_entity, record["id"], {"name": "Robert"})

        assert updated is not None
        assert updated["name"] == "Robert"

    def test_delete(self, pg_adapter, pg_entity):
        """Delete should remove the record and return True."""
        pg_adapter.initialize_entity(pg_entity)

        record = pg_adapter.create(pg_entity, {"name": "ToDelete"})
        deleted = pg_adapter.delete(pg_entity, record["id"])
        assert deleted is True
        assert pg_adapter.get(pg_entity, record["id"]) is None

    def test_delete_nonexistent_returns_false(self, pg_adapter, pg_entity):
        """Delete of a non-existent record should return False."""
        pg_adapter.initialize_entity(pg_entity)
        assert pg_adapter.delete(pg_entity, "PTE-99999") is False

    def test_query_with_filter(self, pg_adapter, pg_entity):
        """Query should return filtered results."""
        pg_adapter.initialize_entity(pg_entity)

        pg_adapter.create(pg_entity, {"name": "QueryAlice"})
        pg_adapter.create(pg_entity, {"name": "QueryBob"})

        result = pg_adapter.query(
            pg_entity,
            filter={
                "operator": "and",
                "conditions": [{"field": "name", "operator": "eq", "value": "QueryAlice"}],
            },
        )
        assert result["pagination"]["total"] >= 1
        names = [r["name"] for r in result["data"]]
        assert "QueryAlice" in names

    def test_query_pagination(self, pg_adapter, pg_entity):
        """Query should honour limit/offset."""
        pg_adapter.initialize_entity(pg_entity)

        for i in range(5):
            pg_adapter.create(pg_entity, {"name": f"PaginateRecord{i}"})

        page1 = pg_adapter.query(pg_entity, limit=2, offset=0)
        assert len(page1["data"]) <= 2

    def test_aggregate_count(self, pg_adapter, pg_entity):
        """Aggregate COUNT(*) should return a non-negative total."""
        pg_adapter.initialize_entity(pg_entity)

        result = pg_adapter.aggregate(
            pg_entity,
            measures=[{"field": "*", "aggregate": "count", "label": "total"}],
        )
        assert result["total"] >= 0
        assert len(result["data"]) == 1
        assert "total" in result["data"][0]

    def test_transaction_commit(self, pg_adapter, pg_entity):
        """create_no_commit + commit should persist the record."""
        pg_adapter.initialize_entity(pg_entity)

        record = pg_adapter.create_no_commit(pg_entity, {"name": "TxCommit"})
        pg_adapter.commit()

        fetched = pg_adapter.get(pg_entity, record["id"])
        assert fetched is not None
        assert fetched["name"] == "TxCommit"

    def test_transaction_rollback(self, pg_adapter, pg_entity):
        """create_no_commit + rollback should discard the record."""
        pg_adapter.initialize_entity(pg_entity)

        record = pg_adapter.create_no_commit(pg_entity, {"name": "TxRollback"})
        record_id = record["id"]
        pg_adapter.rollback()

        fetched = pg_adapter.get(pg_entity, record_id)
        assert fetched is None

    def test_sequence_is_sequential(self, pg_adapter, pg_entity):
        """Sequential creates should produce sequential IDs."""
        pg_adapter.initialize_entity(pg_entity)

        r1 = pg_adapter.create(pg_entity, {"name": "Seq1"})
        r2 = pg_adapter.create(pg_entity, {"name": "Seq2"})

        # IDs look like "PTE-00001", "PTE-00002"
        n1 = int(r1["id"].split("-")[1])
        n2 = int(r2["id"].split("-")[1])
        assert n2 > n1
