"""Compare resolved metadata for schema version and recipe impact reports."""

from dataclasses import dataclass
from typing import Any, Literal

from .loader import FieldDefinition, MetadataLoader

ChangeKind = Literal["added", "removed", "changed"]


@dataclass(frozen=True)
class MetadataChange:
    """A change to an entity, field, or field property in a resolved schema."""

    kind: ChangeKind
    entity: str
    field: str | None = None
    property: str | None = None
    before: Any = None
    after: Any = None


def _field_properties(field: FieldDefinition) -> dict[str, Any]:
    relation = field.relation
    return {
        "type": field.type,
        "required": field.validation.required,
        "options": tuple(option["value"] for option in (field.options or ())),
        "relation": (relation.entity, relation.display_field, relation.on_delete)
        if relation
        else None,
    }


def diff_metadata(before: MetadataLoader, after: MetadataLoader) -> list[MetadataChange]:
    """Return schema changes in entity and field name order.

    Additions and removals of entities include all their fields implicitly.
    Option changes carry the old and new ordered values so callers can
    distinguish additions, removals, and reordered choices.
    """
    changes: list[MetadataChange] = []
    for name in sorted(before.entities.keys() | after.entities.keys()):
        old_entity = before.entities.get(name)
        new_entity = after.entities.get(name)
        if old_entity is None:
            changes.append(MetadataChange("added", name))
            continue
        if new_entity is None:
            changes.append(MetadataChange("removed", name))
            continue
        old_fields = {field.name: field for field in old_entity.fields}
        new_fields = {field.name: field for field in new_entity.fields}
        for field_name in sorted(old_fields.keys() | new_fields.keys()):
            old_field = old_fields.get(field_name)
            new_field = new_fields.get(field_name)
            if old_field is None:
                changes.append(MetadataChange("added", name, field_name))
            elif new_field is None:
                changes.append(MetadataChange("removed", name, field_name))
            else:
                old_properties = _field_properties(old_field)
                new_properties = _field_properties(new_field)
                for key, old in old_properties.items():
                    new = new_properties[key]
                    if old != new:
                        changes.append(MetadataChange("changed", name, field_name, key, old, new))
    return changes
