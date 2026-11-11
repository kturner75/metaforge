"""Auth gates on endpoints that have no entity permission check.

With auth on, the metadata endpoints need a signed-in user and the admin
endpoints (metadata reload, sandbox draft/promote/dismiss) need the admin role.
With auth off (METAFORGE_DISABLE_AUTH=1) they stay open, as before.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).parent.parent


def _app_module():
    # metaforge.api re-exports the FastAPI instance as ``app``, which shadows the
    # module on attribute access, so look the module up directly.
    from metaforge.api.app import app  # noqa: F401  (ensures the module is imported)

    return sys.modules["metaforge.api.app"]


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """App with auth enabled."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("METAFORGE_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("METAFORGE_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("METAFORGE_SECRET_KEY", "test-secret")
    monkeypatch.chdir(BACKEND_DIR)

    module = _app_module()
    try:
        with TestClient(module.app) as client:
            yield client
    finally:
        module.jwt_service = None


@pytest.fixture
def open_client(tmp_path, monkeypatch):
    """App with auth disabled."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("METAFORGE_DISABLE_AUTH", "1")
    monkeypatch.setenv("METAFORGE_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.chdir(BACKEND_DIR)

    with TestClient(_app_module().app) as client:
        yield client


def _headers(role: str) -> dict[str, str]:
    tokens = _app_module().jwt_service.generate_token_pair(
        user_id="user-1", tenant_id="tenant-1", role=role
    )
    return {"Authorization": f"Bearer {tokens.access_token}"}


class TestMetadataRequiresLogin:
    @pytest.mark.parametrize("path", ["/api/metadata", "/api/metadata/Contact"])
    def test_anonymous_gets_401(self, auth_client, path):
        assert auth_client.get(path).status_code == 401

    def test_bad_token_gets_401(self, auth_client):
        response = auth_client.get(
            "/api/metadata/Contact", headers={"Authorization": "Bearer not-a-token"}
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("path", ["/api/metadata", "/api/metadata/Contact"])
    def test_signed_in_user_gets_200(self, auth_client, path):
        assert auth_client.get(path, headers=_headers("readonly")).status_code == 200


ADMIN_CALLS = [
    ("/api/admin/metadata/reload", None),
    ("/api/admin/sandbox/draft", {"yaml": "entity: X\nfields: []\n"}),
    ("/api/admin/sandbox/promote/NoSuchEntity", None),
    ("/api/admin/sandbox/dismiss/NoSuchEntity", None),
]


class TestAdminEndpointsRequireAdmin:
    @pytest.mark.parametrize("path, body", ADMIN_CALLS)
    def test_anonymous_gets_401(self, auth_client, path, body):
        assert auth_client.post(path, json=body).status_code == 401

    @pytest.mark.parametrize("role", ["readonly", "user", "manager"])
    @pytest.mark.parametrize("path, body", ADMIN_CALLS)
    def test_non_admin_gets_403(self, auth_client, path, body, role):
        response = auth_client.post(path, json=body, headers=_headers(role))
        assert response.status_code == 403

    def test_admin_can_reload(self, auth_client):
        response = auth_client.post("/api/admin/metadata/reload", headers=_headers("admin"))
        assert response.status_code == 200

    def test_admin_passes_the_gate(self, auth_client):
        # Unknown draft: the handler's own 400, which means the gate let it through.
        response = auth_client.post(
            "/api/admin/sandbox/dismiss/NoSuchEntity", headers=_headers("admin")
        )
        assert response.status_code == 400


class TestAuthDisabledStaysOpen:
    def test_metadata_open(self, open_client):
        assert open_client.get("/api/metadata/Contact").status_code == 200

    def test_admin_open(self, open_client):
        response = open_client.post("/api/admin/sandbox/dismiss/NoSuchEntity")
        assert response.status_code == 400

    def test_auth_service_reset_after_an_auth_enabled_run(self, tmp_path, monkeypatch):
        """A later start with auth disabled must not keep the earlier JWT service."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("METAFORGE_DISABLE_AUTH", raising=False)
        monkeypatch.setenv("METAFORGE_SECRET_KEY", "test-secret")
        monkeypatch.setenv("METAFORGE_DB_PATH", str(tmp_path / "first.db"))
        monkeypatch.chdir(BACKEND_DIR)
        module = _app_module()
        try:
            with TestClient(module.app):
                assert module.jwt_service is not None

            monkeypatch.setenv("METAFORGE_DISABLE_AUTH", "1")
            monkeypatch.setenv("METAFORGE_DB_PATH", str(tmp_path / "second.db"))
            with TestClient(module.app) as client:
                assert module.jwt_service is None
                assert client.get("/api/metadata/Contact").status_code == 200
        finally:
            module.jwt_service = None
