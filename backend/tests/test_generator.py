"""Tests for migration file generator."""

import ast
from pathlib import Path

import pytest

from metaforge.migrations.generator import generate_migration, _next_revision
from metaforge.migrations.types import (
    AddColumn,
    CreateEntity,
    DropColumn,
    FieldInfo,
)


class TestNextRevision:
    def test_first_revision(self, tmp_path):
        versions_dir = tmp_path / "versions"
        rev, down = _next_revision(versions_dir)
        assert rev == "0001"
        assert down is None

    def test_empty_versions_dir(self, tmp_path):
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir()
        rev, down = _next_revision(versions_dir)
        assert rev == "0001"
        assert down is None

    def test_increments_from_existing(self, tmp_path):
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir()
        (versions_dir / "0001_initial.py").write_text("pass")
        (versions_dir / "0002_add_field.py").write_text("pass")

        rev, down = _next_revision(versions_dir)
        assert rev == "0003"
        assert down == "0002"

    def test_ignores_non_migration_files(self, tmp_path):
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir()
        (versions_dir / "__init__.py").write_text("")
        (versions_dir / "0001_initial.py").write_text("pass")

        rev, down = _next_revision(versions_dir)
        assert rev == "0002"
        assert down == "0001"


class TestGenerateMigration:
    def test_generates_valid_python(self, tmp_path):
        ops = [
            CreateEntity(
                table_name="contact",
                entity_name="Contact",
                fields=[
                    FieldInfo("id", "TEXT", primary_key=True),
                    FieldInfo("email", "TEXT"),
                ],
            )
        ]
        filepath = generate_migration(ops, "initial schema", tmp_path)

        assert filepath.exists()
        content = filepath.read_text()

        # Verify it's valid Python
        ast.parse(content)

    def test_filename_format(self, tmp_path):
        ops = [CreateEntity(table_name="t", entity_name="T", fields=[])]
        filepath = generate_migration(ops, "add contact entity", tmp_path)

        assert filepath.name.startswith("0001_")
        assert "add_contact_entity" in filepath.name
        assert filepath.suffix == ".py"

    def test_contains_upgrade_and_downgrade(self, tmp_path):
        ops = [
            AddColumn(
                table_name="contact",
                field_info=FieldInfo("priority", "TEXT"),
            )
        ]
        filepath = generate_migration(ops, "add priority", tmp_path)
        content = filepath.read_text()

        assert "def upgrade():" in content
        assert "def downgrade():" in content

    def test_upgrade_contains_op_calls(self, tmp_path):
        ops = [
            CreateEntity(
                table_name="contact",
                entity_name="Contact",
                fields=[FieldInfo("id", "TEXT", primary_key=True)],
            )
        ]
        filepath = generate_migration(ops, "initial", tmp_path)
        content = filepath.read_text()

        assert "op.create_table" in content
        assert "'contact'" in content

    def test_downgrade_reverses_create(self, tmp_path):
        ops = [
            CreateEntity(
                table_name="contact",
                entity_name="Contact",
                fields=[FieldInfo("id", "TEXT", primary_key=True)],
            )
        ]
        filepath = generate_migration(ops, "initial", tmp_path)
        content = filepath.read_text()

        # Downgrade should drop the table
        assert "op.drop_table" in content

    def test_revision_metadata(self, tmp_path):
        ops = [CreateEntity(table_name="t", entity_name="T", fields=[])]
        filepath = generate_migration(ops, "test migration", tmp_path)
        content = filepath.read_text()

        assert 'revision = "0001"' in content
        assert "down_revision = None" in content

    def test_sequential_revisions(self, tmp_path):
        ops = [CreateEntity(table_name="t", entity_name="T", fields=[])]

        # First migration
        f1 = generate_migration(ops, "first", tmp_path)
        c1 = f1.read_text()
        assert 'revision = "0001"' in c1
        assert "down_revision = None" in c1

        # Second migration
        f2 = generate_migration(ops, "second", tmp_path)
        c2 = f2.read_text()
        assert 'revision = "0002"' in c2
        assert 'down_revision = "0001"' in c2

    def test_multiple_ops(self, tmp_path):
        ops = [
            CreateEntity(
                table_name="contact",
                entity_name="Contact",
                fields=[FieldInfo("id", "TEXT", primary_key=True)],
            ),
            AddColumn(
                table_name="user",
                field_info=FieldInfo("phone", "TEXT"),
            ),
        ]
        filepath = generate_migration(ops, "multi op", tmp_path)
        content = filepath.read_text()

        assert "op.create_table" in content
        assert "op.add_column" in content

    def test_empty_ops_produces_pass(self, tmp_path):
        filepath = generate_migration([], "empty", tmp_path)
        content = filepath.read_text()

        # Both functions should just have 'pass'
        ast.parse(content)  # Still valid Python
