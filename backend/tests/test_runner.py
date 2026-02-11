"""Tests for the Alembic migration runner."""

import sqlite3
from pathlib import Path

import pytest

from metaforge.migrations.generator import generate_migration
from metaforge.migrations.runner import (
    apply_migrations,
    get_migration_status,
    rollback_migration,
    stamp_migration,
)
from metaforge.migrations.types import (
    AddColumn,
    CreateEntity,
    FieldInfo,
)


@pytest.fixture
def migrations_dir(tmp_path):
    """Fresh migrations directory."""
    d = tmp_path / "migrations"
    d.mkdir()
    return d


@pytest.fixture
def db_url(tmp_path):
    """SQLite database URL for testing."""
    return f"sqlite:///{tmp_path / 'test.db'}"


def _generate_initial(migrations_dir: Path) -> Path:
    """Helper to generate an initial migration with a contact table."""
    ops = [
        CreateEntity(
            table_name="contact",
            entity_name="Contact",
            fields=[
                FieldInfo("id", "TEXT", primary_key=True),
                FieldInfo("email", "TEXT"),
                FieldInfo("name", "TEXT", nullable=False),
            ],
        )
    ]
    return generate_migration(ops, "initial schema", migrations_dir)


def _table_exists(db_path: str, table_name: str) -> bool:
    """Check if a table exists in the SQLite database."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            [table_name],
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def _column_exists(db_path: str, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a SQLite table."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        return column_name in columns
    finally:
        conn.close()


class TestApplyMigrations:
    def test_apply_creates_table(self, db_url, migrations_dir, tmp_path):
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)

        db_path = str(tmp_path / "test.db")
        assert _table_exists(db_path, "contact")

    def test_apply_creates_columns(self, db_url, migrations_dir, tmp_path):
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)

        db_path = str(tmp_path / "test.db")
        assert _column_exists(db_path, "contact", "id")
        assert _column_exists(db_path, "contact", "email")
        assert _column_exists(db_path, "contact", "name")

    def test_apply_second_migration_adds_column(self, db_url, migrations_dir, tmp_path):
        # First migration
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)

        # Second migration — add a column
        ops = [AddColumn(table_name="contact", field_info=FieldInfo("phone", "TEXT"))]
        generate_migration(ops, "add phone", migrations_dir)
        apply_migrations(db_url, migrations_dir)

        db_path = str(tmp_path / "test.db")
        assert _column_exists(db_path, "contact", "phone")

    def test_apply_is_idempotent(self, db_url, migrations_dir, tmp_path):
        """Applying the same migrations twice should not error."""
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)
        # Second apply should be a no-op
        apply_migrations(db_url, migrations_dir)

        db_path = str(tmp_path / "test.db")
        assert _table_exists(db_path, "contact")


class TestRollbackMigration:
    def test_rollback_drops_table(self, db_url, migrations_dir, tmp_path):
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)

        db_path = str(tmp_path / "test.db")
        assert _table_exists(db_path, "contact")

        rollback_migration(db_url, migrations_dir)
        assert not _table_exists(db_path, "contact")

    def test_rollback_second_migration(self, db_url, migrations_dir, tmp_path):
        # Apply two migrations
        _generate_initial(migrations_dir)
        ops2 = [AddColumn(table_name="contact", field_info=FieldInfo("phone", "TEXT"))]
        generate_migration(ops2, "add phone", migrations_dir)
        apply_migrations(db_url, migrations_dir)

        db_path = str(tmp_path / "test.db")
        assert _column_exists(db_path, "contact", "phone")

        # Rollback removes only the phone column
        rollback_migration(db_url, migrations_dir)
        assert _table_exists(db_path, "contact")
        assert not _column_exists(db_path, "contact", "phone")


class TestMigrationStatus:
    def test_status_before_apply(self, db_url, migrations_dir):
        _generate_initial(migrations_dir)
        infos = get_migration_status(db_url, migrations_dir)

        assert len(infos) == 1
        assert infos[0].revision == "0001"
        assert infos[0].is_applied is False

    def test_status_after_apply(self, db_url, migrations_dir):
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)

        infos = get_migration_status(db_url, migrations_dir)
        assert len(infos) == 1
        assert infos[0].is_applied is True

    def test_status_mixed(self, db_url, migrations_dir):
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)

        # Generate second migration (not yet applied)
        ops = [AddColumn(table_name="contact", field_info=FieldInfo("phone", "TEXT"))]
        generate_migration(ops, "add phone", migrations_dir)

        infos = get_migration_status(db_url, migrations_dir)
        assert len(infos) == 2
        assert infos[0].is_applied is True  # 0001
        assert infos[1].is_applied is False  # 0002

    def test_status_after_rollback(self, db_url, migrations_dir):
        _generate_initial(migrations_dir)
        apply_migrations(db_url, migrations_dir)
        rollback_migration(db_url, migrations_dir)

        infos = get_migration_status(db_url, migrations_dir)
        assert len(infos) == 1
        assert infos[0].is_applied is False


class TestStampMigration:
    def test_stamp_marks_as_applied_without_running(self, db_url, migrations_dir, tmp_path):
        """Stamp should mark migration as applied but NOT create the table."""
        _generate_initial(migrations_dir)
        stamp_migration(db_url, migrations_dir)

        # Status shows applied
        infos = get_migration_status(db_url, migrations_dir)
        assert len(infos) == 1
        assert infos[0].is_applied is True

        # But the table was NOT created (stamp doesn't execute migrations)
        db_path = str(tmp_path / "test.db")
        assert not _table_exists(db_path, "contact")

    def test_stamp_then_incremental_apply(self, db_url, migrations_dir, tmp_path):
        """The brownfield workflow: stamp initial, then apply incremental."""
        db_path = str(tmp_path / "test.db")

        # Simulate existing database: create the table manually
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE contact (id TEXT PRIMARY KEY, email TEXT, name TEXT)"
        )
        conn.commit()
        conn.close()

        # Generate initial migration (CREATE TABLE contact)
        _generate_initial(migrations_dir)

        # Stamp it as applied (because table already exists)
        stamp_migration(db_url, migrations_dir)

        # Generate an incremental migration (ADD COLUMN phone)
        ops = [AddColumn(table_name="contact", field_info=FieldInfo("phone", "TEXT"))]
        generate_migration(ops, "add phone", migrations_dir)

        # Apply — should only run 0002, not 0001
        apply_migrations(db_url, migrations_dir)

        # Verify: table exists AND has the new column
        assert _table_exists(db_path, "contact")
        assert _column_exists(db_path, "contact", "phone")

        # Both migrations show as applied
        infos = get_migration_status(db_url, migrations_dir)
        assert len(infos) == 2
        assert all(i.is_applied for i in infos)

    def test_stamp_specific_revision(self, db_url, migrations_dir):
        """Stamp a specific revision, not head."""
        _generate_initial(migrations_dir)
        ops = [AddColumn(table_name="contact", field_info=FieldInfo("phone", "TEXT"))]
        generate_migration(ops, "add phone", migrations_dir)

        # Stamp only 0001
        stamp_migration(db_url, migrations_dir, revision="0001")

        infos = get_migration_status(db_url, migrations_dir)
        assert infos[0].is_applied is True  # 0001 stamped
        assert infos[1].is_applied is False  # 0002 still pending
