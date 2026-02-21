"""Integration tests for API with validation system."""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Create test client with fresh in-memory database."""
    # Remove DATABASE_URL so METAFORGE_DB_PATH can take effect for isolation.
    # Integration tests always use a per-test SQLite DB regardless of the
    # DATABASE_URL that may be set in the environment for PG live testing.
    saved_db_url = os.environ.pop("DATABASE_URL", None)

    # Set up environment to use temporary directory for db
    os.environ["METAFORGE_DB_PATH"] = str(tmp_path / "test.db")
    # Disable auth for these tests (tests without authentication)
    os.environ["METAFORGE_DISABLE_AUTH"] = "1"

    # Change to backend directory so metadata can be found
    original_cwd = Path.cwd()
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)

    # Import app after setting env vars
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
        if saved_db_url is not None:
            os.environ["DATABASE_URL"] = saved_db_url


def create_company(client, name="Test Company"):
    """Helper to create a company and return its ID."""
    response = client.post(
        "/api/entities/Company",
        json={
            "data": {
                "name": name,
                "industry": "technology",
            }
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


class TestContactValidation:
    """Test validation integration with Contact entity."""

    def test_create_contact_with_defaults(self, client):
        """Test that defaults are applied on create."""
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "John",
                    "lastName": "Doe",
                }
            },
        )

        # Should get 202 because of the "no company" warning
        assert response.status_code == 202
        data = response.json()
        assert data["requiresAcknowledgment"] is True
        assert len(data["warnings"]) == 1
        assert data["warnings"][0]["code"] == "NO_COMPANY"

    def test_create_contact_acknowledge_warning(self, client):
        """Test creating contact by acknowledging warning."""
        # First request - get the warning
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "John",
                    "lastName": "Doe",
                }
            },
        )
        assert response.status_code == 202
        first_response = response.json()
        token = first_response["acknowledgmentToken"]
        processed_data = first_response["data"]  # Get the processed record

        # Second request - acknowledge the warning with the processed record
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": processed_data,  # Resubmit the processed record
                "acknowledgeWarnings": token,
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]

        # Verify defaults were applied
        assert data["fullName"] == "John Doe"
        assert data["status"] == "lead"
        assert "id" in data

    def test_create_active_contact_without_email_fails(self, client):
        """Test that active contacts require email."""
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Jane",
                    "lastName": "Smith",
                    "status": "active",
                }
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["valid"] is False

        # Should have the conditional required error
        error_codes = [e["code"] for e in data["errors"]]
        assert "EMAIL_REQUIRED_FOR_ACTIVE" in error_codes

    def test_create_active_contact_with_email_and_company(self, client):
        """Test creating active contact with required fields."""
        # First create a company
        company_id = create_company(client)

        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Jane",
                    "lastName": "Smith",
                    "status": "active",
                    "email": "jane@example.com",
                    "companyId": company_id,
                }
            },
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["fullName"] == "Jane Smith"
        assert data["status"] == "active"
        assert data["email"] == "jane@example.com"

    def test_update_contact_fullname_recomputed(self, client):
        """Test that fullName is recomputed on update."""
        # Create a contact first (acknowledge warning)
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "John",
                    "lastName": "Doe",
                }
            },
        )
        first_response = response.json()
        token = first_response["acknowledgmentToken"]
        processed_data = first_response["data"]

        response = client.post(
            "/api/entities/Contact",
            json={
                "data": processed_data,
                "acknowledgeWarnings": token,
            },
        )
        contact_id = response.json()["data"]["id"]

        # Update the contact
        response = client.put(
            f"/api/entities/Contact/{contact_id}",
            json={
                "data": {
                    "lastName": "Smith",
                }
            },
        )

        # Should still get warning about no company
        assert response.status_code == 202
        update_response = response.json()
        token = update_response["acknowledgmentToken"]
        processed_data = update_response["data"]

        # Check that fullName was recomputed in the 202 response
        assert processed_data.get("fullName") == "John Smith"

        response = client.put(
            f"/api/entities/Contact/{contact_id}",
            json={
                "data": processed_data,
                "acknowledgeWarnings": token,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["fullName"] == "John Smith"


class TestFieldValidation:
    """Test field-level validation (Layer 0)."""

    def test_required_field_missing(self, client):
        """Test that required fields are enforced."""
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "lastName": "Doe",  # firstName missing
                }
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["valid"] is False

        # Should have required field error for firstName
        error_codes = [e["code"] for e in data["errors"]]
        assert "REQUIRED" in error_codes

    def test_email_format_invalid(self, client):
        """Test that email format is validated."""
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "not-an-email",
                }
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["valid"] is False

        error_codes = [e["code"] for e in data["errors"]]
        assert "INVALID_EMAIL" in error_codes

    def test_email_format_valid(self, client):
        """Test that valid email passes validation."""
        # Create a real company first
        company_id = create_company(client)

        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john@example.com",
                    "companyId": company_id,
                }
            },
        )

        # Should pass field validation (gets 201 since company is set)
        assert response.status_code == 201

    def test_picklist_invalid_option(self, client):
        """Test that picklist options are validated."""
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "status": "invalid-status",
                }
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["valid"] is False

        error_codes = [e["code"] for e in data["errors"]]
        assert "INVALID_OPTION" in error_codes

    def test_phone_format_invalid(self, client):
        """Test that phone format is validated."""
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "phone": "not-a-phone",
                }
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["valid"] is False

        error_codes = [e["code"] for e in data["errors"]]
        assert "INVALID_PHONE" in error_codes


class TestMetadataEndpoints:
    """Test metadata endpoints."""

    def test_list_entities(self, client):
        """Test listing all entities."""
        response = client.get("/api/metadata")
        assert response.status_code == 200
        data = response.json()

        entity_names = [e["name"] for e in data["entities"]]
        assert "Contact" in entity_names

    def test_get_entity_metadata(self, client):
        """Test getting entity metadata."""
        response = client.get("/api/metadata/Contact")
        assert response.status_code == 200
        data = response.json()

        assert data["entity"] == "Contact"
        assert data["displayName"] == "Contact"
        assert data["pluralName"] == "Contacts"

        # Check fields
        field_names = [f["name"] for f in data["fields"]]
        assert "firstName" in field_names
        assert "lastName" in field_names
        assert "email" in field_names
        assert "fullName" in field_names

    def test_get_unknown_entity_returns_404(self, client):
        """Test that unknown entity returns 404."""
        response = client.get("/api/metadata/Unknown")
        assert response.status_code == 404


class TestRelations:
    """Test relation field handling."""

    def test_fk_validation_invalid_reference(self, client):
        """Test that invalid FK references are rejected."""
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Test",
                    "lastName": "User",
                    "companyId": "00000000-0000-0000-0000-000000000000",  # Non-existent
                }
            },
        )

        assert response.status_code == 422
        data = response.json()
        error_codes = [e["code"] for e in data["errors"]]
        assert "REFERENCE_NOT_FOUND" in error_codes

    def test_fk_validation_valid_reference(self, client):
        """Test that valid FK references are accepted."""
        # Create a company
        company_id = create_company(client)

        # Create a contact with valid FK
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Test",
                    "lastName": "User",
                    "companyId": company_id,
                }
            },
        )

        assert response.status_code == 201

    def test_display_value_hydration_in_query(self, client):
        """Test that query results include relation display values."""
        # Create a company
        company_id = create_company(client, "Acme Corp")

        # Create a contact
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Test",
                    "lastName": "User",
                    "companyId": company_id,
                }
            },
        )
        assert response.status_code == 201

        # Query contacts
        response = client.post(
            "/api/query/Contact",
            json={"fields": ["id", "firstName", "companyId"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 1

        # Find the contact we created
        contact = next(
            (c for c in data["data"] if c.get("firstName") == "Test"),
            None
        )
        assert contact is not None
        assert contact.get("companyId_display") == "Acme Corp"

    def test_display_value_hydration_in_get(self, client):
        """Test that single record get includes relation display values."""
        # Create a company
        company_id = create_company(client, "Test Company Inc")

        # Create a contact
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Get",
                    "lastName": "Test",
                    "companyId": company_id,
                }
            },
        )
        assert response.status_code == 201
        contact_id = response.json()["data"]["id"]

        # Get the contact
        response = client.get(f"/api/entities/Contact/{contact_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data.get("companyId_display") == "Test Company Inc"

    def test_delete_restrict_with_children(self, client):
        """Test that delete is restricted when children exist."""
        # Create a company
        company_id = create_company(client, "Protected Company")

        # Create a contact referencing the company
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Child",
                    "lastName": "Contact",
                    "companyId": company_id,
                }
            },
        )
        assert response.status_code == 201

        # Try to delete the company - should fail with restrict (default)
        response = client.delete(f"/api/entities/Company/{company_id}")
        assert response.status_code == 422
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "DELETE_RESTRICTED" in error_codes

    def test_delete_allowed_without_children(self, client):
        """Test that delete is allowed when no children exist."""
        # Create a company with no contacts
        company_id = create_company(client, "Lonely Company")

        # Delete should succeed
        response = client.delete(f"/api/entities/Company/{company_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify it's deleted
        response = client.get(f"/api/entities/Company/{company_id}")
        assert response.status_code == 404


class TestQueryEndpoint:
    """Test query endpoint."""

    def test_query_contacts(self, client):
        """Test querying contacts."""
        # Create a company first
        company_id = create_company(client, "Query Test Company")

        # Create a contact
        response = client.post(
            "/api/entities/Contact",
            json={
                "data": {
                    "firstName": "Query",
                    "lastName": "Test",
                    "companyId": company_id,
                }
            },
        )
        assert response.status_code == 201

        # Query contacts
        response = client.post(
            "/api/query/Contact",
            json={
                "fields": ["id", "firstName", "lastName", "fullName"],
                "filter": {
                    "operator": "and",
                    "conditions": [
                        {"field": "firstName", "operator": "eq", "value": "Query"}
                    ]
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 1
        assert data["data"][0]["firstName"] == "Query"
        assert data["data"][0]["fullName"] == "Query Test"


class TestAggregateEndpoint:
    """Test aggregate endpoint."""

    def _seed_contacts(self, client):
        """Create several contacts with different statuses for aggregation."""
        company_id = create_company(client, "Aggregate Test Co")
        contacts = [
            {"firstName": "A", "lastName": "One", "status": "active", "email": "a@test.com", "companyId": company_id},
            {"firstName": "B", "lastName": "Two", "status": "active", "email": "b@test.com", "companyId": company_id},
            {"firstName": "C", "lastName": "Three", "status": "inactive", "companyId": company_id},
            {"firstName": "D", "lastName": "Four", "status": "lead", "companyId": company_id},
            {"firstName": "E", "lastName": "Five", "status": "lead", "companyId": company_id},
        ]
        for contact in contacts:
            resp = client.post("/api/entities/Contact", json={"data": contact})
            assert resp.status_code == 201, f"Failed to seed contact: {resp.json()}"

    def test_count_all(self, client):
        """Count all contacts (no groupBy) returns a single row."""
        self._seed_contacts(client)
        response = client.post(
            "/api/aggregate/Contact",
            json={
                "measures": [{"field": "*", "aggregate": "count", "label": "total"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["total"] >= 5
        assert data["total"] == 1

    def test_count_grouped_by_status(self, client):
        """Count grouped by status returns one row per status."""
        self._seed_contacts(client)
        response = client.post(
            "/api/aggregate/Contact",
            json={
                "groupBy": ["status"],
                "measures": [{"field": "*", "aggregate": "count", "label": "count"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        # At least 3 groups: active, inactive, lead
        assert len(data["data"]) >= 3
        status_map = {row["status"]: row["count"] for row in data["data"]}
        assert status_map.get("active", 0) >= 2
        assert status_map.get("lead", 0) >= 2
        assert status_map.get("inactive", 0) >= 1

    def test_aggregate_with_filter(self, client):
        """Filter applied before aggregation."""
        self._seed_contacts(client)
        response = client.post(
            "/api/aggregate/Contact",
            json={
                "measures": [{"field": "*", "aggregate": "count", "label": "count"}],
                "filter": {
                    "conditions": [
                        {"field": "status", "operator": "eq", "value": "active"},
                    ],
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["count"] >= 2

    def test_aggregate_unknown_entity_404(self, client):
        """Unknown entity returns 404."""
        response = client.post(
            "/api/aggregate/Unknown",
            json={"measures": [{"field": "*", "aggregate": "count"}]},
        )
        assert response.status_code == 404

    def test_aggregate_empty_result(self, client):
        """COUNT on empty table returns 0."""
        response = client.post(
            "/api/aggregate/Contact",
            json={
                "measures": [{"field": "*", "aggregate": "count", "label": "total"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["total"] == 0

    def test_invalid_aggregate_function(self, client):
        """Unsupported aggregate function returns 400."""
        response = client.post(
            "/api/aggregate/Contact",
            json={
                "measures": [{"field": "id", "aggregate": "median"}],
            },
        )
        assert response.status_code == 400

    def test_no_measures_returns_empty(self, client):
        """No measures returns empty result."""
        response = client.post(
            "/api/aggregate/Contact",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total"] == 0
