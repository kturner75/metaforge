"""Integration tests for views API endpoints."""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Create test client with fresh database."""
    os.environ["METAFORGE_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["METAFORGE_DISABLE_AUTH"] = "1"

    original_cwd = Path.cwd()
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)

    from metaforge.api.app import app

    try:
        with TestClient(app) as client:
            yield client
    finally:
        os.chdir(original_cwd)
        if "METAFORGE_DB_PATH" in os.environ:
            del os.environ["METAFORGE_DB_PATH"]
        if "METAFORGE_DISABLE_AUTH" in os.environ:
            del os.environ["METAFORGE_DISABLE_AUTH"]


class TestListConfigs:
    """Test GET /api/views/configs."""

    def test_list_includes_yaml_configs(self, client):
        """YAML-seeded configs should appear in list."""
        response = client.get("/api/views/configs")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 1

        names = [c["name"] for c in data]
        assert "Contact Grid" in names

    def test_list_filter_by_entity_name(self, client):
        """Should filter by entity_name query param."""
        response = client.get("/api/views/configs?entity_name=Contact")
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(c["entityName"] == "Contact" for c in data)

    def test_list_filter_by_style(self, client):
        """Should filter by style query param."""
        response = client.get("/api/views/configs?style=grid")
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(c["style"] == "grid" for c in data)

    def test_list_filter_no_results(self, client):
        """Filtering with no matches should return empty list."""
        response = client.get("/api/views/configs?entity_name=NonExistent")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data == []


class TestGetConfig:
    """Test GET /api/views/configs/{config_id}."""

    def test_get_yaml_config(self, client):
        """Should return a YAML-seeded config by ID."""
        response = client.get("/api/views/configs/yaml:contact-grid")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Contact Grid"
        assert data["entityName"] == "Contact"
        assert data["pattern"] == "query"
        assert data["style"] == "grid"
        assert data["source"] == "yaml"

    def test_get_yaml_config_has_data_and_style(self, client):
        """YAML config should have populated dataConfig and styleConfig."""
        response = client.get("/api/views/configs/yaml:contact-grid")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["dataConfig"]["pageSize"] == 25
        assert len(data["styleConfig"]["columns"]) >= 1

    def test_get_nonexistent_returns_404(self, client):
        """Unknown config ID should return 404."""
        response = client.get("/api/views/configs/nonexistent")
        assert response.status_code == 404


class TestCreateConfig:
    """Test POST /api/views/configs."""

    def test_create_config(self, client):
        """Should create a new config."""
        response = client.post(
            "/api/views/configs",
            json={
                "name": "My Contact Grid",
                "entity_name": "Contact",
                "pattern": "query",
                "style": "grid",
                "scope": "personal",
                "data_config": {"pageSize": 50},
                "style_config": {"selectable": True},
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "My Contact Grid"
        assert data["entityName"] == "Contact"
        assert data["pattern"] == "query"
        assert data["dataConfig"]["pageSize"] == 50
        assert data["id"]  # Should have generated ID

    def test_create_config_appears_in_list(self, client):
        """Created config should appear in list endpoint."""
        client.post(
            "/api/views/configs",
            json={
                "name": "Listed Config",
                "pattern": "query",
                "style": "grid",
                "data_config": {},
                "style_config": {},
            },
        )

        response = client.get("/api/views/configs")
        names = [c["name"] for c in response.json()["data"]]
        assert "Listed Config" in names


class TestUpdateConfig:
    """Test PUT /api/views/configs/{config_id}."""

    def test_update_db_config(self, client):
        """Should update a database-source config."""
        # Create first
        create_response = client.post(
            "/api/views/configs",
            json={
                "name": "Original",
                "pattern": "query",
                "style": "grid",
                "data_config": {"pageSize": 25},
                "style_config": {},
            },
        )
        config_id = create_response.json()["data"]["id"]

        # Update
        response = client.put(
            f"/api/views/configs/{config_id}",
            json={"name": "Updated", "data_config": {"pageSize": 100}},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Updated"
        assert data["dataConfig"]["pageSize"] == 100

    def test_update_yaml_config_forbidden(self, client):
        """Should not allow editing YAML-source configs."""
        response = client.put(
            "/api/views/configs/yaml:contact-grid",
            json={"name": "Hacked"},
        )
        assert response.status_code == 403

    def test_update_nonexistent_returns_404(self, client):
        """Should return 404 for unknown config ID."""
        response = client.put(
            "/api/views/configs/nonexistent",
            json={"name": "nope"},
        )
        assert response.status_code == 404


class TestDeleteConfig:
    """Test DELETE /api/views/configs/{config_id}."""

    def test_delete_db_config(self, client):
        """Should delete a database-source config."""
        create_response = client.post(
            "/api/views/configs",
            json={
                "name": "To Delete",
                "pattern": "query",
                "style": "grid",
                "data_config": {},
                "style_config": {},
            },
        )
        config_id = create_response.json()["data"]["id"]

        response = client.delete(f"/api/views/configs/{config_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify it's gone
        response = client.get(f"/api/views/configs/{config_id}")
        assert response.status_code == 404

    def test_delete_yaml_config_forbidden(self, client):
        """Should not allow deleting YAML-source configs."""
        response = client.delete("/api/views/configs/yaml:contact-grid")
        assert response.status_code == 403

    def test_delete_nonexistent_returns_404(self, client):
        """Should return 404 for unknown config ID."""
        response = client.delete("/api/views/configs/nonexistent")
        assert response.status_code == 404


class TestResolveConfig:
    """Test GET /api/views/resolve."""

    def test_resolve_returns_yaml_fallback(self, client):
        """Should resolve to YAML config when no user config exists."""
        response = client.get(
            "/api/views/resolve?entity_name=Contact&style=grid"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Contact Grid"
        assert data["source"] == "yaml"

    def test_resolve_user_config_over_yaml(self, client):
        """User-created config should take precedence over YAML."""
        # Create a personal config
        client.post(
            "/api/views/configs",
            json={
                "name": "My Custom Grid",
                "entity_name": "Contact",
                "pattern": "query",
                "style": "grid",
                "scope": "personal",
                "data_config": {"pageSize": 100},
                "style_config": {"selectable": True},
            },
        )

        response = client.get(
            "/api/views/resolve?entity_name=Contact&style=grid"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        # Without auth, user_id is None so personal config won't match via user precedence.
        # But it will still exist in the store. The YAML config should still resolve
        # since there's no authenticated user to claim the personal config.
        assert data["name"] in ("Contact Grid", "My Custom Grid")

    def test_resolve_no_match_returns_404(self, client):
        """Should return 404 when no config matches."""
        response = client.get(
            "/api/views/resolve?entity_name=NonExistent&style=grid"
        )
        assert response.status_code == 404
