"""Migration operation types.

Each operation knows how to render itself as Alembic op.* Python code
for both upgrade and downgrade directions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Map MetaForge storage types to SQLAlchemy type expressions for migration code.
ALEMBIC_TYPE_MAP = {
    "TEXT": "sa.Text()",
    "INTEGER": "sa.Integer()",
    "REAL": "sa.Float()",
}


def _sa_type(storage_type: str) -> str:
    """Get SQLAlchemy type expression string for a storage type."""
    return ALEMBIC_TYPE_MAP.get(storage_type, "sa.Text()")


@dataclass
class FieldInfo:
    """Minimal field info needed for migration operations."""

    name: str
    storage_type: str
    primary_key: bool = False
    nullable: bool = True


@dataclass
class MigrationOp:
    """Base class for migration operations."""

    destructive: bool = False

    def render_upgrade(self) -> list[str]:
        raise NotImplementedError

    def render_downgrade(self) -> list[str]:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


@dataclass
class CreateEntity(MigrationOp):
    """CREATE TABLE for a new entity."""

    table_name: str = ""
    entity_name: str = ""
    fields: list[FieldInfo] = field(default_factory=list)

    def render_upgrade(self) -> list[str]:
        lines = ["    op.create_table("]
        lines.append(f"        '{self.table_name}',")
        for f in self.fields:
            pk = ", primary_key=True" if f.primary_key else ""
            nullable = f", nullable={f.nullable}" if not f.primary_key else ""
            lines.append(
                f"        sa.Column('{f.name}', {_sa_type(f.storage_type)}{pk}{nullable}),"
            )
        lines.append("    )")
        return lines

    def render_downgrade(self) -> list[str]:
        return [f"    op.drop_table('{self.table_name}')"]

    def describe(self) -> str:
        return f"Create table '{self.table_name}' ({len(self.fields)} columns)"


@dataclass
class DropEntity(MigrationOp):
    """DROP TABLE for a removed entity."""

    table_name: str = ""
    entity_name: str = ""
    fields: list[FieldInfo] = field(default_factory=list)
    destructive: bool = True

    def render_upgrade(self) -> list[str]:
        return [f"    op.drop_table('{self.table_name}')"]

    def render_downgrade(self) -> list[str]:
        # Recreate table on downgrade
        lines = ["    op.create_table("]
        lines.append(f"        '{self.table_name}',")
        for f in self.fields:
            pk = ", primary_key=True" if f.primary_key else ""
            nullable = f", nullable={f.nullable}" if not f.primary_key else ""
            lines.append(
                f"        sa.Column('{f.name}', {_sa_type(f.storage_type)}{pk}{nullable}),"
            )
        lines.append("    )")
        return lines

    def describe(self) -> str:
        return f"Drop table '{self.table_name}'"


@dataclass
class DropEntityWarning(MigrationOp):
    """Warning comment for a removed entity when --allow-destructive is not set."""

    table_name: str = ""
    entity_name: str = ""

    def render_upgrade(self) -> list[str]:
        return [
            f"    # WARNING: Entity '{self.entity_name}' was removed from metadata.",
            f"    # To drop table '{self.table_name}', re-run with --allow-destructive.",
            "    # Existing data will be permanently lost.",
            "    pass",
        ]

    def render_downgrade(self) -> list[str]:
        return ["    pass"]

    def describe(self) -> str:
        return f"WARNING: Entity '{self.entity_name}' removed (use --allow-destructive to drop)"


@dataclass
class AddColumn(MigrationOp):
    """ADD COLUMN for a new field."""

    table_name: str = ""
    field_info: FieldInfo = field(default_factory=lambda: FieldInfo("", "TEXT"))

    def render_upgrade(self) -> list[str]:
        nullable = f", nullable={self.field_info.nullable}"
        return [
            f"    op.add_column('{self.table_name}', "
            f"sa.Column('{self.field_info.name}', "
            f"{_sa_type(self.field_info.storage_type)}{nullable}))"
        ]

    def render_downgrade(self) -> list[str]:
        return [
            f"    op.drop_column('{self.table_name}', '{self.field_info.name}')"
        ]

    def describe(self) -> str:
        return (
            f"Add column '{self.field_info.name}' ({self.field_info.storage_type}) "
            f"to '{self.table_name}'"
        )


@dataclass
class DropColumn(MigrationOp):
    """DROP COLUMN for a removed field."""

    table_name: str = ""
    field_info: FieldInfo = field(default_factory=lambda: FieldInfo("", "TEXT"))
    destructive: bool = True

    def render_upgrade(self) -> list[str]:
        return [
            f"    op.drop_column('{self.table_name}', '{self.field_info.name}')"
        ]

    def render_downgrade(self) -> list[str]:
        nullable = f", nullable={self.field_info.nullable}"
        return [
            f"    op.add_column('{self.table_name}', "
            f"sa.Column('{self.field_info.name}', "
            f"{_sa_type(self.field_info.storage_type)}{nullable}))"
        ]

    def describe(self) -> str:
        return f"Drop column '{self.field_info.name}' from '{self.table_name}'"


@dataclass
class DropColumnWarning(MigrationOp):
    """Warning for removed column when --allow-destructive is not set."""

    table_name: str = ""
    field_name: str = ""

    def render_upgrade(self) -> list[str]:
        return [
            f"    # WARNING: Field '{self.field_name}' was removed from entity metadata.",
            f"    # To drop column from '{self.table_name}', re-run with --allow-destructive.",
            "    # Existing data in this column will be permanently lost.",
            "    pass",
        ]

    def render_downgrade(self) -> list[str]:
        return ["    pass"]

    def describe(self) -> str:
        return (
            f"WARNING: Field '{self.field_name}' removed from '{self.table_name}' "
            f"(use --allow-destructive to drop)"
        )


@dataclass
class AlterColumnType(MigrationOp):
    """ALTER COLUMN TYPE for a field type change."""

    table_name: str = ""
    field_name: str = ""
    old_storage_type: str = ""
    new_storage_type: str = ""

    def render_upgrade(self) -> list[str]:
        return [
            f"    op.alter_column('{self.table_name}', '{self.field_name}',",
            f"        type_={_sa_type(self.new_storage_type)},",
            f"        existing_type={_sa_type(self.old_storage_type)})",
        ]

    def render_downgrade(self) -> list[str]:
        return [
            f"    op.alter_column('{self.table_name}', '{self.field_name}',",
            f"        type_={_sa_type(self.old_storage_type)},",
            f"        existing_type={_sa_type(self.new_storage_type)})",
        ]

    def describe(self) -> str:
        return (
            f"Change column '{self.field_name}' in '{self.table_name}' "
            f"from {self.old_storage_type} to {self.new_storage_type}"
        )


@dataclass
class SetNotNull(MigrationOp):
    """Set a column to NOT NULL."""

    table_name: str = ""
    field_name: str = ""
    storage_type: str = ""

    def render_upgrade(self) -> list[str]:
        return [
            f"    op.alter_column('{self.table_name}', '{self.field_name}',",
            "        nullable=False,",
            f"        existing_type={_sa_type(self.storage_type)})",
        ]

    def render_downgrade(self) -> list[str]:
        return [
            f"    op.alter_column('{self.table_name}', '{self.field_name}',",
            "        nullable=True,",
            f"        existing_type={_sa_type(self.storage_type)})",
        ]

    def describe(self) -> str:
        return f"Set '{self.field_name}' in '{self.table_name}' to NOT NULL"


@dataclass
class DropNotNull(MigrationOp):
    """Remove NOT NULL constraint from a column."""

    table_name: str = ""
    field_name: str = ""
    storage_type: str = ""

    def render_upgrade(self) -> list[str]:
        return [
            f"    op.alter_column('{self.table_name}', '{self.field_name}',",
            "        nullable=True,",
            f"        existing_type={_sa_type(self.storage_type)})",
        ]

    def render_downgrade(self) -> list[str]:
        return [
            f"    op.alter_column('{self.table_name}', '{self.field_name}',",
            "        nullable=False,",
            f"        existing_type={_sa_type(self.storage_type)})",
        ]

    def describe(self) -> str:
        return f"Drop NOT NULL from '{self.field_name}' in '{self.table_name}'"
