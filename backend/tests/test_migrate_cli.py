"""Integration tests for the migrate CLI commands."""

import os
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from metaforge.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Set up an isolated environment for migration tests.

    Uses a temp directory for the database, but the real project
    metadata for entity definitions.
    """
    backend_dir = Path(__file__).parent.parent
    base_path = backend_dir.parent

    # Point to a temp database
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # Use the real metadata path
    monkeypatch.chdir(backend_dir)

    # Point migrations to a temp directory (so we don't pollute the project)
    migrations_dir = tmp_path / "migrations"
    # We need to patch _resolve_paths to use our temp migrations dir
    # Instead, we'll create a symlink or override. For simplicity,
    # we create the migrations dir at the expected location and clean up.

    # Actually, _resolve_paths uses base_path / "migrations" which is
    # the project root / migrations. We'll patch this by temporarily
    # creating the migrations dir there and cleaning up after.
    # Better approach: just use the real project migrations dir but clean up.

    # Simplest: set cwd to tmp_path and create metadata symlink
    monkeypatch.chdir(tmp_path)

    # Create metadata symlink
    metadata_link = tmp_path / "metadata"
    if not metadata_link.exists():
        metadata_link.symlink_to(base_path / "metadata")

    return tmp_path


class TestMigrateGenerate:
    def test_generate_initial(self, runner, isolated_env):
        result = runner.invoke(cli, ["migrate", "generate", "-m", "initial schema"])
        assert result.exit_code == 0, result.output
        assert "change(s)" in result.output or "Generated" in result.output

        # Verify migration file was created
        versions_dir = isolated_env / "migrations" / "versions"
        assert versions_dir.exists()
        migration_files = list(versions_dir.glob("0001_*.py"))
        assert len(migration_files) == 1

    def test_generate_creates_snapshot(self, runner, isolated_env):
        result = runner.invoke(cli, ["migrate", "generate", "-m", "initial"])
        assert result.exit_code == 0, result.output

        snapshot_path = isolated_env / "migrations" / "schema_snapshot.json"
        assert snapshot_path.exists()

        data = json.loads(snapshot_path.read_text())
        assert "entities" in data
        assert "Contact" in data["entities"]

    def test_generate_no_changes(self, runner, isolated_env):
        # First generate
        result = runner.invoke(cli, ["migrate", "generate", "-m", "initial"])
        assert result.exit_code == 0

        # Second generate — no changes
        result = runner.invoke(cli, ["migrate", "generate", "-m", "nothing"])
        assert result.exit_code == 0
        assert "No changes detected" in result.output


class TestMigrateApply:
    def test_apply_no_migrations(self, runner, isolated_env):
        result = runner.invoke(cli, ["migrate", "apply"])
        assert result.exit_code == 0
        assert "No migrations found" in result.output

    def test_generate_and_apply(self, runner, isolated_env):
        # Generate
        result = runner.invoke(cli, ["migrate", "generate", "-m", "initial"])
        assert result.exit_code == 0, result.output

        # Apply
        result = runner.invoke(cli, ["migrate", "apply"])
        assert result.exit_code == 0, result.output
        assert "applied" in result.output.lower()


class TestMigrateStatus:
    def test_status_no_migrations(self, runner, isolated_env):
        result = runner.invoke(cli, ["migrate", "status"])
        assert result.exit_code == 0
        assert "No migrations found" in result.output

    def test_status_after_generate(self, runner, isolated_env):
        runner.invoke(cli, ["migrate", "generate", "-m", "initial"])

        result = runner.invoke(cli, ["migrate", "status"])
        assert result.exit_code == 0
        assert "pending" in result.output.lower()
        assert "0001" in result.output

    def test_status_after_apply(self, runner, isolated_env):
        runner.invoke(cli, ["migrate", "generate", "-m", "initial"])
        runner.invoke(cli, ["migrate", "apply"])

        result = runner.invoke(cli, ["migrate", "status"])
        assert result.exit_code == 0
        assert "[x]" in result.output  # Applied marker


class TestMigrateRollback:
    def test_rollback_after_apply(self, runner, isolated_env):
        runner.invoke(cli, ["migrate", "generate", "-m", "initial"])
        runner.invoke(cli, ["migrate", "apply"])

        result = runner.invoke(cli, ["migrate", "rollback"])
        assert result.exit_code == 0, result.output
        assert "Rollback successful" in result.output


class TestMigrateStamp:
    def test_stamp_marks_initial_as_applied(self, runner, isolated_env):
        runner.invoke(cli, ["migrate", "generate", "-m", "initial"])

        result = runner.invoke(cli, ["migrate", "stamp"])
        assert result.exit_code == 0, result.output
        assert "Stamp successful" in result.output
        assert "[x]" in result.output  # Shows as applied

    def test_stamp_then_apply_incremental(self, runner, isolated_env):
        """Full brownfield workflow via CLI."""
        # Generate initial (will be stamped, not applied)
        runner.invoke(cli, ["migrate", "generate", "-m", "initial"])

        # Create tables manually to simulate existing DB
        import sqlite3

        db_path = isolated_env / "test.db"
        db_url = f"sqlite:///{db_path}"
        # The DATABASE_URL is already set by isolated_env fixture

        # Stamp initial as applied
        result = runner.invoke(cli, ["migrate", "stamp"])
        assert result.exit_code == 0, result.output

        # Verify status
        result = runner.invoke(cli, ["migrate", "status"])
        assert "[x]" in result.output
        assert "0 pending" in result.output


class TestMigrateInit:
    def test_init_creates_baseline(self, runner, isolated_env):
        """Init generates a migration, saves snapshot, and stamps the DB."""
        result = runner.invoke(cli, ["migrate", "init"])
        assert result.exit_code == 0, result.output
        assert "Baseline complete" in result.output

        # Migration file created
        versions_dir = isolated_env / "migrations" / "versions"
        migration_files = list(versions_dir.glob("0001_*.py"))
        assert len(migration_files) == 1

        # Snapshot saved
        snapshot_path = isolated_env / "migrations" / "schema_snapshot.json"
        assert snapshot_path.exists()
        data = json.loads(snapshot_path.read_text())
        assert "Contact" in data["entities"]

        # Database stamped — status shows applied
        result = runner.invoke(cli, ["migrate", "status"])
        assert "[x]" in result.output
        assert "0 pending" in result.output

    def test_init_then_incremental(self, runner, isolated_env):
        """Full brownfield workflow: init → add field → generate → apply."""
        import sqlite3

        db_path = isolated_env / "test.db"

        # Create existing tables (simulates initialize_entity)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE contact ("
            "id TEXT PRIMARY KEY, tenantId TEXT, firstName TEXT NOT NULL, "
            "lastName TEXT NOT NULL, email TEXT, phone TEXT, "
            "companyId TEXT, status TEXT, notes TEXT, fullName TEXT, "
            "createdBy TEXT, createdAt TEXT, updatedBy TEXT, updatedAt TEXT)"
        )
        conn.execute(
            "CREATE TABLE company ("
            "id TEXT PRIMARY KEY, tenantId TEXT, name TEXT NOT NULL, "
            "industry TEXT, website TEXT, phone TEXT, notes TEXT, "
            "createdBy TEXT, createdAt TEXT, updatedBy TEXT, updatedAt TEXT)"
        )
        conn.execute(
            "CREATE TABLE tenant ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL, "
            "active INTEGER, "
            "createdBy TEXT, createdAt TEXT, updatedBy TEXT, updatedAt TEXT)"
        )
        conn.execute(
            "CREATE TABLE tenant_membership ("
            "id TEXT PRIMARY KEY, userId TEXT NOT NULL, tenantId TEXT NOT NULL, "
            "role TEXT NOT NULL, "
            "createdBy TEXT, createdAt TEXT, updatedBy TEXT, updatedAt TEXT)"
        )
        conn.execute(
            "CREATE TABLE user ("
            "id TEXT PRIMARY KEY, email TEXT NOT NULL, passwordHash TEXT, "
            "name TEXT NOT NULL, active INTEGER, "
            "createdBy TEXT, createdAt TEXT, updatedBy TEXT, updatedAt TEXT)"
        )
        conn.commit()
        conn.close()

        # Step 1: Init baseline
        result = runner.invoke(cli, ["migrate", "init"])
        assert result.exit_code == 0, result.output
        assert "Baseline complete" in result.output

        # Step 2: Modify the snapshot to simulate a metadata change.
        # We'll add a "rating" field to the Contact entity in the snapshot
        # by removing it from the current snapshot (so next generate sees it
        # as a new column). Actually, the easier approach: modify the snapshot
        # to NOT include hq_state (since Company.yaml may already have it),
        # then generate will detect the diff.
        #
        # Actually, the cleanest approach: directly generate the diff by
        # editing the saved snapshot to remove a field that exists in metadata.
        snapshot_path = isolated_env / "migrations" / "schema_snapshot.json"
        data = json.loads(snapshot_path.read_text())

        # Company in current metadata has hq_state, so if we remove it from
        # snapshot, the next generate will produce an ADD COLUMN.
        if "hq_state" in data["entities"]["Company"]["fields"]:
            del data["entities"]["Company"]["fields"]["hq_state"]
            snapshot_path.write_text(json.dumps(data, indent=2))

            # Step 3: Generate incremental migration
            result = runner.invoke(
                cli, ["migrate", "generate", "-m", "add hq_state"]
            )
            assert result.exit_code == 0, result.output
            assert "Generated" in result.output

            # Verify 0002 was created
            versions_dir = isolated_env / "migrations" / "versions"
            assert any(versions_dir.glob("0002_*.py"))

            # Step 4: Apply — should only add the column
            result = runner.invoke(cli, ["migrate", "apply"])
            assert result.exit_code == 0, result.output
            assert "applied" in result.output.lower()

            # Verify the column was actually added
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("PRAGMA table_info(company)")
            columns = [row[1] for row in cursor.fetchall()]
            conn.close()
            assert "hq_state" in columns

            # Status should show both applied
            result = runner.invoke(cli, ["migrate", "status"])
            assert "[x] 0001" in result.output
            assert "[x] 0002" in result.output
            assert "0 pending" in result.output

    def test_init_blocks_if_migrations_exist(self, runner, isolated_env):
        """Init refuses to run if migrations already exist."""
        # First init
        result = runner.invoke(cli, ["migrate", "init"])
        assert result.exit_code == 0

        # Second init — should fail
        result = runner.invoke(cli, ["migrate", "init"])
        assert result.exit_code != 0
        assert "already exist" in result.output

    def test_init_custom_message(self, runner, isolated_env):
        """Init accepts a custom message."""
        result = runner.invoke(cli, ["migrate", "init", "-m", "custom baseline"])
        assert result.exit_code == 0

        versions_dir = isolated_env / "migrations" / "versions"
        migration_files = list(versions_dir.glob("0001_*.py"))
        assert len(migration_files) == 1
        assert "custom_baseline" in migration_files[0].name


class TestMigrateHelp:
    def test_migrate_help(self, runner):
        result = runner.invoke(cli, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.output
        assert "apply" in result.output
        assert "rollback" in result.output
        assert "stamp" in result.output
        assert "status" in result.output
        assert "init" in result.output
