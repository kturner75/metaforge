"""Tests for sequence-based ID generation."""

import sqlite3
import pytest

from metaforge.persistence.sequences import SequenceService


@pytest.fixture
def conn():
    """Create in-memory database connection."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def service(conn):
    """Create sequence service with test connection."""
    return SequenceService(conn)


class TestSequenceService:
    """Tests for SequenceService."""

    def test_first_id_starts_at_1(self, service):
        """First ID should be 00001."""
        id = service.next_id("Contact", "CON", "tenant", "tenant-1")
        assert id == "CON-00001"

    def test_ids_increment(self, service):
        """IDs should increment sequentially."""
        id1 = service.next_id("Contact", "CON", "tenant", "tenant-1")
        id2 = service.next_id("Contact", "CON", "tenant", "tenant-1")
        id3 = service.next_id("Contact", "CON", "tenant", "tenant-1")

        assert id1 == "CON-00001"
        assert id2 == "CON-00002"
        assert id3 == "CON-00003"

    def test_different_entities_have_separate_sequences(self, service):
        """Each entity should have its own sequence."""
        contact_id = service.next_id("Contact", "CON", "tenant", "tenant-1")
        company_id = service.next_id("Company", "CMP", "tenant", "tenant-1")
        contact_id2 = service.next_id("Contact", "CON", "tenant", "tenant-1")

        assert contact_id == "CON-00001"
        assert company_id == "CMP-00001"
        assert contact_id2 == "CON-00002"

    def test_tenant_scoped_sequences_per_tenant(self, service):
        """Tenant-scoped entities should have per-tenant sequences."""
        # Tenant 1
        t1_id1 = service.next_id("Contact", "CON", "tenant", "tenant-1")
        t1_id2 = service.next_id("Contact", "CON", "tenant", "tenant-1")

        # Tenant 2 starts at 1
        t2_id1 = service.next_id("Contact", "CON", "tenant", "tenant-2")
        t2_id2 = service.next_id("Contact", "CON", "tenant", "tenant-2")

        assert t1_id1 == "CON-00001"
        assert t1_id2 == "CON-00002"
        assert t2_id1 == "CON-00001"  # Separate sequence for tenant 2
        assert t2_id2 == "CON-00002"

    def test_global_scope_ignores_tenant(self, service):
        """Global-scoped entities should have one sequence regardless of tenant."""
        # Different tenants, same global sequence
        id1 = service.next_id("Currency", "CUR", "global", "tenant-1")
        id2 = service.next_id("Currency", "CUR", "global", "tenant-2")
        id3 = service.next_id("Currency", "CUR", "global", "tenant-1")

        assert id1 == "CUR-00001"
        assert id2 == "CUR-00002"  # Continues from global sequence
        assert id3 == "CUR-00003"

    def test_global_scope_without_tenant(self, service):
        """Global-scoped entities work without tenant ID."""
        id1 = service.next_id("Currency", "CUR", "global", None)
        id2 = service.next_id("Currency", "CUR", "global", None)

        assert id1 == "CUR-00001"
        assert id2 == "CUR-00002"

    def test_current_value_returns_last_used(self, service):
        """current_value should return the last ID number generated."""
        assert service.current_value("Contact", "tenant-1") == 0  # No IDs yet

        service.next_id("Contact", "CON", "tenant", "tenant-1")
        assert service.current_value("Contact", "tenant-1") == 1

        service.next_id("Contact", "CON", "tenant", "tenant-1")
        service.next_id("Contact", "CON", "tenant", "tenant-1")
        assert service.current_value("Contact", "tenant-1") == 3

    def test_reset_sequence(self, service):
        """reset should set sequence to specific value."""
        # Generate some IDs
        service.next_id("Contact", "CON", "tenant", "tenant-1")
        service.next_id("Contact", "CON", "tenant", "tenant-1")
        service.next_id("Contact", "CON", "tenant", "tenant-1")

        # Reset to 100
        service.reset("Contact", "tenant-1", start_value=100)

        # Next ID should be 100
        id = service.next_id("Contact", "CON", "tenant", "tenant-1")
        assert id == "CON-00100"

    def test_id_format_five_digits(self, service):
        """IDs should be zero-padded to 5 digits."""
        service.reset("Contact", None, start_value=1)
        assert service.next_id("Contact", "CON", "global") == "CON-00001"

        service.reset("Contact", None, start_value=999)
        assert service.next_id("Contact", "CON", "global") == "CON-00999"

        service.reset("Contact", None, start_value=10000)
        assert service.next_id("Contact", "CON", "global") == "CON-10000"

        service.reset("Contact", None, start_value=99999)
        assert service.next_id("Contact", "CON", "global") == "CON-99999"

    def test_id_format_exceeds_five_digits(self, service):
        """IDs beyond 99999 should still work (just longer)."""
        service.reset("Contact", None, start_value=100000)
        id = service.next_id("Contact", "CON", "global")
        assert id == "CON-100000"


class TestSequenceServiceTableCreation:
    """Tests for sequence table initialization."""

    def test_creates_sequences_table(self, conn):
        """Service should create _sequences table on init."""
        # Table shouldn't exist yet
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_sequences'"
        )
        assert cursor.fetchone() is None

        # Create service
        SequenceService(conn)

        # Table should now exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_sequences'"
        )
        assert cursor.fetchone() is not None

    def test_table_creation_is_idempotent(self, conn):
        """Creating multiple services should not fail."""
        SequenceService(conn)
        SequenceService(conn)  # Should not raise
        SequenceService(conn)  # Should not raise

        # Table should still work
        service = SequenceService(conn)
        id = service.next_id("Test", "TST", "global")
        assert id == "TST-00001"
