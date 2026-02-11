"""Tests for the migration diff engine."""

import pytest

from metaforge.migrations.diff import compute_diff
from metaforge.migrations.snapshot import EntitySnapshot, FieldSnapshot, SchemaSnapshot
from metaforge.migrations.types import (
    AddColumn,
    AlterColumnType,
    CreateEntity,
    DropColumn,
    DropColumnWarning,
    DropEntity,
    DropEntityWarning,
    DropNotNull,
    SetNotNull,
)


def _make_snapshot(entities: dict[str, EntitySnapshot]) -> SchemaSnapshot:
    return SchemaSnapshot(version=1, entities=entities, generated_at="test")


def _make_entity(name: str, fields: dict[str, FieldSnapshot], scope: str = "tenant") -> EntitySnapshot:
    table_name = ""
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            table_name += "_"
        table_name += char.lower()
    return EntitySnapshot(name=name, table_name=table_name, scope=scope, fields=fields)


def _field(name: str, type_: str = "text", storage: str = "TEXT",
           required: bool = False, pk: bool = False) -> FieldSnapshot:
    return FieldSnapshot(name=name, type=type_, storage_type=storage,
                         required=required, primary_key=pk)


class TestNoChanges:
    def test_identical_snapshots_produce_no_ops(self):
        entity = _make_entity("Contact", {
            "id": _field("id", pk=True),
            "name": _field("name", required=True),
        })
        old = _make_snapshot({"Contact": entity})
        new = _make_snapshot({"Contact": entity})
        ops = compute_diff(old, new)
        assert ops == []

    def test_both_empty_produce_no_ops(self):
        ops = compute_diff(SchemaSnapshot.empty(), SchemaSnapshot.empty())
        assert ops == []


class TestNewEntity:
    def test_new_entity_creates_table(self):
        old = SchemaSnapshot.empty()
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "email": _field("email", type_="email"),
            })
        })
        ops = compute_diff(old, new)
        assert len(ops) == 1
        assert isinstance(ops[0], CreateEntity)
        assert ops[0].table_name == "contact"
        assert ops[0].entity_name == "Contact"
        assert len(ops[0].fields) == 2

    def test_new_entity_is_not_destructive(self):
        old = SchemaSnapshot.empty()
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {"id": _field("id", pk=True)})
        })
        ops = compute_diff(old, new)
        assert not ops[0].destructive

    def test_create_entity_renders_upgrade(self):
        old = SchemaSnapshot.empty()
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "name": _field("name", required=True),
            })
        })
        ops = compute_diff(old, new)
        lines = ops[0].render_upgrade()
        joined = "\n".join(lines)
        assert "op.create_table" in joined
        assert "'contact'" in joined
        assert "'id'" in joined
        assert "'name'" in joined


class TestRemovedEntity:
    def test_removed_entity_without_destructive_emits_warning(self):
        old = _make_snapshot({
            "Legacy": _make_entity("Legacy", {"id": _field("id", pk=True)})
        })
        new = SchemaSnapshot.empty()
        ops = compute_diff(old, new, allow_destructive=False)
        assert len(ops) == 1
        assert isinstance(ops[0], DropEntityWarning)
        assert ops[0].entity_name == "Legacy"

    def test_removed_entity_with_destructive_emits_drop(self):
        old = _make_snapshot({
            "Legacy": _make_entity("Legacy", {"id": _field("id", pk=True)})
        })
        new = SchemaSnapshot.empty()
        ops = compute_diff(old, new, allow_destructive=True)
        assert len(ops) == 1
        assert isinstance(ops[0], DropEntity)
        assert ops[0].destructive is True
        assert ops[0].table_name == "legacy"


class TestNewField:
    def test_new_field_adds_column(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
            })
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "email": _field("email", type_="email"),
            })
        })
        ops = compute_diff(old, new)
        assert len(ops) == 1
        assert isinstance(ops[0], AddColumn)
        assert ops[0].field_info.name == "email"
        assert ops[0].table_name == "contact"

    def test_add_column_renders_upgrade(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {"id": _field("id", pk=True)})
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "priority": _field("priority", type_="picklist"),
            })
        })
        ops = compute_diff(old, new)
        lines = ops[0].render_upgrade()
        joined = "\n".join(lines)
        assert "op.add_column" in joined
        assert "'priority'" in joined


class TestRemovedField:
    def test_removed_field_without_destructive_emits_warning(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "legacy": _field("legacy"),
            })
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {"id": _field("id", pk=True)})
        })
        ops = compute_diff(old, new, allow_destructive=False)
        assert len(ops) == 1
        assert isinstance(ops[0], DropColumnWarning)
        assert ops[0].field_name == "legacy"

    def test_removed_field_with_destructive_emits_drop(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "legacy": _field("legacy"),
            })
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {"id": _field("id", pk=True)})
        })
        ops = compute_diff(old, new, allow_destructive=True)
        assert len(ops) == 1
        assert isinstance(ops[0], DropColumn)
        assert ops[0].destructive is True


class TestFieldTypeChange:
    def test_type_change_emits_alter(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "score": _field("score", type_="text", storage="TEXT"),
            })
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "score": _field("score", type_="number", storage="REAL"),
            })
        })
        ops = compute_diff(old, new)
        assert len(ops) == 1
        assert isinstance(ops[0], AlterColumnType)
        assert ops[0].old_storage_type == "TEXT"
        assert ops[0].new_storage_type == "REAL"


class TestConstraintChanges:
    def test_required_added_emits_set_not_null(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "email": _field("email", required=False),
            })
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "email": _field("email", required=True),
            })
        })
        ops = compute_diff(old, new)
        assert len(ops) == 1
        assert isinstance(ops[0], SetNotNull)

    def test_required_removed_emits_drop_not_null(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "email": _field("email", required=True),
            })
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "email": _field("email", required=False),
            })
        })
        ops = compute_diff(old, new)
        assert len(ops) == 1
        assert isinstance(ops[0], DropNotNull)

    def test_pk_required_change_ignored(self):
        """Primary keys should not generate NOT NULL ops."""
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True, required=False),
            })
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True, required=True),
            })
        })
        ops = compute_diff(old, new)
        assert ops == []


class TestMultipleChanges:
    def test_multiple_changes_at_once(self):
        old = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "old_field": _field("old_field"),
            }),
            "Legacy": _make_entity("Legacy", {"id": _field("id", pk=True)}),
        })
        new = _make_snapshot({
            "Contact": _make_entity("Contact", {
                "id": _field("id", pk=True),
                "new_field": _field("new_field"),
            }),
            "Deal": _make_entity("Deal", {"id": _field("id", pk=True)}),
        })
        ops = compute_diff(old, new, allow_destructive=True)

        op_types = [type(op).__name__ for op in ops]
        assert "CreateEntity" in op_types  # Deal
        assert "DropEntity" in op_types  # Legacy
        assert "AddColumn" in op_types  # new_field
        assert "DropColumn" in op_types  # old_field
