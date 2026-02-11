"""Tests for MetaForge CLI commands."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from metaforge.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def in_backend_dir(monkeypatch):
    """Ensure CWD is the backend directory for metadata resolution."""
    backend_dir = Path(__file__).parent.parent
    monkeypatch.chdir(backend_dir)


class TestMetadataValidate:
    def test_validate_succeeds(self, runner, in_backend_dir):
        result = runner.invoke(cli, ["metadata", "validate"])
        assert result.exit_code == 0
        assert "All metadata is valid" in result.output

    def test_validate_shows_entities(self, runner, in_backend_dir):
        result = runner.invoke(cli, ["metadata", "validate"])
        assert "Contact" in result.output
        assert "Company" in result.output
        assert "User" in result.output

    def test_validate_shows_field_counts(self, runner, in_backend_dir):
        result = runner.invoke(cli, ["metadata", "validate"])
        assert "fields" in result.output


class TestMetadataDiff:
    def test_diff_with_no_snapshot_shows_all_entities(self, runner, in_backend_dir):
        """When no snapshot exists, all entities are 'new'."""
        result = runner.invoke(cli, ["metadata", "diff"])
        assert result.exit_code == 0
        assert "change(s)" in result.output
        assert "Create table" in result.output

    def test_diff_with_matching_snapshot_shows_no_changes(
        self, runner, in_backend_dir, tmp_path, monkeypatch
    ):
        """When snapshot matches metadata, no changes detected."""
        from metaforge.metadata.loader import MetadataLoader
        from metaforge.migrations.snapshot import (
            create_snapshot_from_metadata,
            save_snapshot,
        )

        # Create a snapshot matching current metadata
        backend_dir = Path(__file__).parent.parent
        base_path = backend_dir.parent
        loader = MetadataLoader(base_path / "metadata")
        loader.load_all()
        snap = create_snapshot_from_metadata(loader)

        # Save it where the CLI expects it
        migrations_dir = base_path / "migrations"
        migrations_dir.mkdir(exist_ok=True)
        save_snapshot(snap, migrations_dir / "schema_snapshot.json")

        try:
            result = runner.invoke(cli, ["metadata", "diff"])
            assert result.exit_code == 0
            assert "No changes detected" in result.output
        finally:
            # Clean up the snapshot we created
            snapshot_path = migrations_dir / "schema_snapshot.json"
            if snapshot_path.exists():
                snapshot_path.unlink()
            if migrations_dir.exists() and not any(migrations_dir.iterdir()):
                migrations_dir.rmdir()


class TestCLIEntryPoint:
    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "MetaForge" in result.output

    def test_metadata_help(self, runner):
        result = runner.invoke(cli, ["metadata", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
        assert "diff" in result.output
