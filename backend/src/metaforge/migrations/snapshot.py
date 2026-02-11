"""Schema snapshot — captures the current state of all entity schemas.

The snapshot is the reference point for computing migration diffs.
It is serialized to JSON and committed to source control.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from metaforge.core.types import get_storage_type
from metaforge.metadata.loader import MetadataLoader


@dataclass
class FieldSnapshot:
    """Snapshot of a single field's schema-relevant properties."""

    name: str
    type: str  # MetaForge field type (e.g., "name", "email", "number")
    storage_type: str  # SQL type (TEXT, INTEGER, REAL)
    required: bool = False
    primary_key: bool = False
    max_length: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "storage_type": self.storage_type,
        }
        if self.required:
            d["required"] = True
        if self.primary_key:
            d["primary_key"] = True
        if self.max_length is not None:
            d["max_length"] = self.max_length
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldSnapshot:
        return cls(
            name=data["name"],
            type=data["type"],
            storage_type=data["storage_type"],
            required=data.get("required", False),
            primary_key=data.get("primary_key", False),
            max_length=data.get("max_length"),
        )


@dataclass
class EntitySnapshot:
    """Snapshot of a single entity's schema."""

    name: str
    table_name: str
    scope: str
    fields: dict[str, FieldSnapshot] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "table_name": self.table_name,
            "scope": self.scope,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntitySnapshot:
        fields = {
            k: FieldSnapshot.from_dict(v) for k, v in data.get("fields", {}).items()
        }
        return cls(
            name=data["name"],
            table_name=data["table_name"],
            scope=data["scope"],
            fields=fields,
        )


@dataclass
class SchemaSnapshot:
    """Complete snapshot of the schema derived from metadata."""

    version: int = 0
    entities: dict[str, EntitySnapshot] = field(default_factory=dict)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "entities": {k: v.to_dict() for k, v in self.entities.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchemaSnapshot:
        entities = {
            k: EntitySnapshot.from_dict(v) for k, v in data.get("entities", {}).items()
        }
        return cls(
            version=data.get("version", 0),
            generated_at=data.get("generated_at", ""),
            entities=entities,
        )

    @classmethod
    def empty(cls) -> SchemaSnapshot:
        return cls(version=0, entities={}, generated_at="")


def _table_name(entity_name: str) -> str:
    """Convert CamelCase entity name to snake_case table name.

    Same logic as SQLiteAdapter._table_name().
    """
    result = []
    for i, char in enumerate(entity_name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def create_snapshot_from_metadata(loader: MetadataLoader) -> SchemaSnapshot:
    """Create a SchemaSnapshot from the current metadata.

    Args:
        loader: MetadataLoader with all entities loaded.

    Returns:
        A SchemaSnapshot representing the current metadata state.
    """
    entities: dict[str, EntitySnapshot] = {}

    for entity_name in loader.list_entities():
        entity = loader.get_entity(entity_name)
        if not entity:
            continue

        fields: dict[str, FieldSnapshot] = {}
        for f in entity.fields:
            fields[f.name] = FieldSnapshot(
                name=f.name,
                type=f.type,
                storage_type=get_storage_type(f.type),
                required=f.validation.required if f.validation else False,
                primary_key=f.primary_key,
                max_length=f.validation.max_length if f.validation else None,
            )

        entities[entity_name] = EntitySnapshot(
            name=entity_name,
            table_name=_table_name(entity_name),
            scope=entity.scope,
            fields=fields,
        )

    return SchemaSnapshot(
        version=0,  # Set by the caller when saving
        entities=entities,
        generated_at=datetime.utcnow().isoformat(),
    )


def save_snapshot(snapshot: SchemaSnapshot, path: Path) -> None:
    """Save a snapshot to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(snapshot.to_dict(), f, indent=2)
        f.write("\n")


def load_snapshot(path: Path) -> SchemaSnapshot:
    """Load a snapshot from a JSON file.

    Returns an empty snapshot if the file doesn't exist.
    """
    if not path.exists():
        return SchemaSnapshot.empty()

    with open(path) as f:
        data = json.load(f)

    return SchemaSnapshot.from_dict(data)
