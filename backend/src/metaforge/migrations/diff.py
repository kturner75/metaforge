"""Migration diff engine.

Compares two SchemaSnapshots and produces a list of MigrationOps
representing the changes needed to migrate from old to new.
"""

from __future__ import annotations

from metaforge.migrations.snapshot import SchemaSnapshot
from metaforge.migrations.types import (
    AddColumn,
    AlterColumnType,
    CreateEntity,
    DropColumn,
    DropColumnWarning,
    DropEntity,
    DropEntityWarning,
    DropNotNull,
    FieldInfo,
    MigrationOp,
    SetNotNull,
)


def compute_diff(
    old: SchemaSnapshot,
    new: SchemaSnapshot,
    allow_destructive: bool = False,
) -> list[MigrationOp]:
    """Compute the list of migration operations to go from old to new.

    Args:
        old: Previous schema snapshot.
        new: Current schema snapshot (from metadata).
        allow_destructive: If True, emit DROP TABLE/DROP COLUMN ops.
            If False, emit warning comments instead.

    Returns:
        Ordered list of MigrationOps.
    """
    ops: list[MigrationOp] = []

    # 1. New entities (in new but not in old)
    for name, entity in new.entities.items():
        if name not in old.entities:
            fields = [
                FieldInfo(
                    name=f.name,
                    storage_type=f.storage_type,
                    primary_key=f.primary_key,
                    nullable=not f.required and not f.primary_key,
                )
                for f in entity.fields.values()
            ]
            ops.append(
                CreateEntity(
                    table_name=entity.table_name,
                    entity_name=name,
                    fields=fields,
                )
            )

    # 2. Removed entities (in old but not in new)
    for name, entity in old.entities.items():
        if name not in new.entities:
            if allow_destructive:
                fields = [
                    FieldInfo(
                        name=f.name,
                        storage_type=f.storage_type,
                        primary_key=f.primary_key,
                        nullable=not f.required and not f.primary_key,
                    )
                    for f in entity.fields.values()
                ]
                ops.append(
                    DropEntity(
                        table_name=entity.table_name,
                        entity_name=name,
                        fields=fields,
                    )
                )
            else:
                ops.append(
                    DropEntityWarning(
                        table_name=entity.table_name,
                        entity_name=name,
                    )
                )

    # 3. Changed entities (in both old and new)
    for name in old.entities:
        if name in new.entities:
            entity_ops = _diff_entity(
                old.entities[name],
                new.entities[name],
                allow_destructive,
            )
            ops.extend(entity_ops)

    return ops


def _diff_entity(
    old_entity,
    new_entity,
    allow_destructive: bool,
) -> list[MigrationOp]:
    """Diff a single entity between old and new snapshots."""
    ops: list[MigrationOp] = []
    table_name = new_entity.table_name

    # New fields
    for field_name, new_field in new_entity.fields.items():
        if field_name not in old_entity.fields:
            ops.append(
                AddColumn(
                    table_name=table_name,
                    field_info=FieldInfo(
                        name=new_field.name,
                        storage_type=new_field.storage_type,
                        primary_key=new_field.primary_key,
                        nullable=not new_field.required and not new_field.primary_key,
                    ),
                )
            )

    # Removed fields
    for field_name, old_field in old_entity.fields.items():
        if field_name not in new_entity.fields:
            if allow_destructive:
                ops.append(
                    DropColumn(
                        table_name=table_name,
                        field_info=FieldInfo(
                            name=old_field.name,
                            storage_type=old_field.storage_type,
                            primary_key=old_field.primary_key,
                            nullable=not old_field.required and not old_field.primary_key,
                        ),
                    )
                )
            else:
                ops.append(
                    DropColumnWarning(
                        table_name=table_name,
                        field_name=field_name,
                    )
                )

    # Changed fields (type change or constraint change)
    for field_name in old_entity.fields:
        if field_name in new_entity.fields:
            old_field = old_entity.fields[field_name]
            new_field = new_entity.fields[field_name]

            # Type change (storage type)
            if old_field.storage_type != new_field.storage_type:
                ops.append(
                    AlterColumnType(
                        table_name=table_name,
                        field_name=field_name,
                        old_storage_type=old_field.storage_type,
                        new_storage_type=new_field.storage_type,
                    )
                )

            # Required constraint added
            if not old_field.required and new_field.required and not new_field.primary_key:
                ops.append(
                    SetNotNull(
                        table_name=table_name,
                        field_name=field_name,
                        storage_type=new_field.storage_type,
                    )
                )

            # Required constraint removed
            if old_field.required and not new_field.required and not old_field.primary_key:
                ops.append(
                    DropNotNull(
                        table_name=table_name,
                        field_name=field_name,
                        storage_type=new_field.storage_type,
                    )
                )

    return ops
