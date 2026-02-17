"""Tests for MCP server tools.

Tests call the underlying tool functions directly (via .fn) to verify
that the service layer integration works correctly.
"""

import asyncio
import os
from pathlib import Path

import pytest

import metaforge.mcp.server as server_module


@pytest.fixture
def services(tmp_path):
    """Initialize MetaForge services with a fresh database."""
    os.environ["METAFORGE_DB_PATH"] = str(tmp_path / "test.db")

    original_cwd = Path.cwd()
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)

    # Reset global services so each test gets a fresh instance
    server_module._services = None

    try:
        svc = server_module._get_services()
        yield svc
    finally:
        if svc.db:
            svc.db.close()
        server_module._services = None
        os.chdir(original_cwd)
        if "METAFORGE_DB_PATH" in os.environ:
            del os.environ["METAFORGE_DB_PATH"]
        for key in ("METAFORGE_MCP_USER_ID", "METAFORGE_MCP_TENANT_ID", "METAFORGE_MCP_ROLE"):
            os.environ.pop(key, None)


# Access underlying functions behind @mcp.tool() decorators
_list_entities = server_module.list_entities.fn
_get_entity_metadata = server_module.get_entity_metadata.fn
_query_records = server_module.query_records.fn
_get_record = server_module.get_record.fn
_aggregate_records = server_module.aggregate_records.fn
_list_view_configs = server_module.list_view_configs.fn
_get_view_config = server_module.get_view_config.fn
_create_record = server_module.create_record.fn
_update_record = server_module.update_record.fn
_delete_record = server_module.delete_record.fn
_create_view_config = server_module.create_view_config.fn
_update_view_config = server_module.update_view_config.fn


# =============================================================================
# Metadata Discovery
# =============================================================================


class TestListEntities:
    def test_returns_all_entities(self, services):
        result = _list_entities()
        names = [e["name"] for e in result]
        assert "Contact" in names
        assert "Company" in names
        assert "Category" in names

    def test_entity_structure(self, services):
        result = _list_entities()
        contact = next(e for e in result if e["name"] == "Contact")
        assert contact["displayName"] == "Contact"
        assert contact["pluralName"] == "Contacts"


class TestGetEntityMetadata:
    def test_returns_fields(self, services):
        result = _get_entity_metadata("Contact")
        assert result["entity"] == "Contact"
        assert result["primaryKey"] == "id"
        field_names = [f["name"] for f in result["fields"]]
        assert "firstName" in field_names
        assert "email" in field_names
        assert "status" in field_names

    def test_includes_validation(self, services):
        result = _get_entity_metadata("Contact")
        first_name = next(f for f in result["fields"] if f["name"] == "firstName")
        assert first_name["validation"]["required"] is True

    def test_includes_picklist_options(self, services):
        result = _get_entity_metadata("Contact")
        status = next(f for f in result["fields"] if f["name"] == "status")
        assert status["options"] is not None
        values = [o["value"] for o in status["options"]]
        assert "active" in values

    def test_includes_relations(self, services):
        result = _get_entity_metadata("Contact")
        company_field = next(f for f in result["fields"] if f["name"] == "companyId")
        assert company_field["relation"] is not None
        assert company_field["relation"]["entity"] == "Company"

    def test_includes_scope(self, services):
        result = _get_entity_metadata("Contact")
        assert result["scope"] == "tenant"

    def test_not_found(self, services):
        result = _get_entity_metadata("NonExistent")
        assert "error" in result


# =============================================================================
# Read Tools
# =============================================================================


class TestQueryRecords:
    def test_empty_query(self, services):
        result = _query_records("Company")
        assert result["data"] == []
        assert result["pagination"]["total"] == 0

    def test_query_with_data(self, services):
        entity = services.metadata_loader.get_entity("Company")
        services.db.create(entity, {"name": "Acme Corp", "industry": "technology"})

        result = _query_records("Company")
        assert result["pagination"]["total"] == 1
        assert result["data"][0]["name"] == "Acme Corp"

    def test_query_with_filter(self, services):
        entity = services.metadata_loader.get_entity("Company")
        services.db.create(entity, {"name": "Acme Corp", "industry": "technology"})
        services.db.create(entity, {"name": "Beta Inc", "industry": "healthcare"})

        result = _query_records(
            "Company",
            filter={
                "operator": "and",
                "conditions": [{"field": "industry", "operator": "eq", "value": "technology"}],
            },
        )
        assert result["pagination"]["total"] == 1
        assert result["data"][0]["name"] == "Acme Corp"

    def test_query_with_limit(self, services):
        entity = services.metadata_loader.get_entity("Company")
        for i in range(5):
            services.db.create(entity, {"name": f"Company {i}", "industry": "technology"})

        result = _query_records("Company", limit=2)
        assert len(result["data"]) == 2
        assert result["pagination"]["total"] == 5

    def test_not_found_entity(self, services):
        result = _query_records("NonExistent")
        assert "error" in result


class TestGetRecord:
    def test_get_existing(self, services):
        entity = services.metadata_loader.get_entity("Company")
        created = services.db.create(entity, {"name": "Acme Corp", "industry": "technology"})

        result = _get_record("Company", created["id"])
        assert result["data"]["name"] == "Acme Corp"

    def test_get_not_found(self, services):
        result = _get_record("Company", "nonexistent-id")
        assert "error" in result


class TestAggregateRecords:
    def test_aggregate_count(self, services):
        entity = services.metadata_loader.get_entity("Company")
        services.db.create(entity, {"name": "Acme", "industry": "technology"})
        services.db.create(entity, {"name": "Beta", "industry": "technology"})
        services.db.create(entity, {"name": "Gamma", "industry": "healthcare"})

        result = _aggregate_records(
            "Company",
            group_by=["industry"],
            measures=[{"field": "id", "aggregate": "count"}],
        )
        assert len(result["data"]) == 2

        tech = next(r for r in result["data"] if r["industry"] == "technology")
        assert tech["count_id"] == 2


class TestViewConfigs:
    def test_list_view_configs(self, services):
        result = _list_view_configs()
        # YAML configs should be seeded
        assert len(result) > 0

    def test_list_filtered(self, services):
        result = _list_view_configs(entity_name="Contact", style="grid")
        assert len(result) >= 1
        assert all(c["entityName"] == "Contact" for c in result)

    def test_get_view_config(self, services):
        all_configs = _list_view_configs()
        assert len(all_configs) > 0

        config = _get_view_config(all_configs[0]["id"])
        assert "name" in config

    def test_get_not_found(self, services):
        result = _get_view_config("nonexistent")
        assert "error" in result


# =============================================================================
# Write Tools
# =============================================================================


class TestCreateRecord:
    def test_create_company(self, services):
        result = asyncio.get_event_loop().run_until_complete(
            _create_record("Company", {"name": "Acme Corp", "industry": "technology"})
        )
        assert "data" in result
        assert result["data"]["name"] == "Acme Corp"
        assert result["data"]["id"].startswith("COM-")

    def test_create_with_validation_error(self, services):
        # Company requires name
        result = asyncio.get_event_loop().run_until_complete(
            _create_record("Company", {"industry": "technology"})
        )
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_create_not_found_entity(self, services):
        result = asyncio.get_event_loop().run_until_complete(
            _create_record("NonExistent", {"name": "test"})
        )
        assert "error" in result


class TestUpdateRecord:
    def test_update_company(self, services):
        created = asyncio.get_event_loop().run_until_complete(
            _create_record("Company", {"name": "Acme Corp", "industry": "technology"})
        )
        record_id = created["data"]["id"]

        updated = asyncio.get_event_loop().run_until_complete(
            _update_record("Company", record_id, {"name": "Acme Corporation"})
        )
        assert updated["data"]["name"] == "Acme Corporation"
        # Industry should be preserved
        assert updated["data"]["industry"] == "technology"

    def test_update_not_found(self, services):
        result = asyncio.get_event_loop().run_until_complete(
            _update_record("Company", "nonexistent", {"name": "test"})
        )
        assert "error" in result


class TestDeleteRecord:
    def test_delete_company(self, services):
        created = asyncio.get_event_loop().run_until_complete(
            _create_record("Company", {"name": "Acme Corp", "industry": "technology"})
        )
        record_id = created["data"]["id"]

        result = asyncio.get_event_loop().run_until_complete(
            _delete_record("Company", record_id)
        )
        assert result["success"] is True

        # Verify it's gone
        get_result = _get_record("Company", record_id)
        assert "error" in get_result

    def test_delete_not_found(self, services):
        result = asyncio.get_event_loop().run_until_complete(
            _delete_record("Company", "nonexistent")
        )
        assert "error" in result


class TestCreateViewConfig:
    def test_create_and_retrieve(self, services):
        created = _create_view_config(
            name="Test Grid",
            pattern="query",
            style="grid",
            data_config={"entity": "Company", "limit": 10},
            style_config={"columns": [{"field": "name"}, {"field": "industry"}]},
            entity_name="Company",
        )
        assert created["name"] == "Test Grid"
        assert created["pattern"] == "query"
        assert created["id"] is not None

        retrieved = _get_view_config(created["id"])
        assert retrieved["name"] == "Test Grid"


class TestUpdateViewConfig:
    def test_update_database_config(self, services):
        created = _create_view_config(
            name="Test Grid",
            pattern="query",
            style="grid",
            data_config={"entity": "Company", "limit": 10},
            style_config={"columns": [{"field": "name"}]},
            entity_name="Company",
        )

        updated = _update_view_config(
            created["id"],
            name="Updated Grid",
            style_config={"columns": [{"field": "name"}, {"field": "industry"}]},
        )
        assert updated["name"] == "Updated Grid"
        assert len(updated["styleConfig"]["columns"]) == 2

    def test_cannot_update_yaml_config(self, services):
        yaml_configs = [c for c in _list_view_configs() if c["source"] == "yaml"]
        if yaml_configs:
            result = _update_view_config(yaml_configs[0]["id"], name="Hacked")
            assert "error" in result
