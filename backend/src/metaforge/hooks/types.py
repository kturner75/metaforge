"""Hook system types for MetaForge.

Defines the core data structures for the entity lifecycle hook system:
- HookDefinition: metadata describing when/how a hook should run
- HookContext: runtime state passed to hook functions
- HookResult: return value from hook functions
"""

from dataclasses import dataclass, field
from typing import Any

from metaforge.validation.types import Operation, UserContext


@dataclass
class HookDefinition:
    """Definition of a hook from entity metadata.

    Attributes:
        name: Registered hook name (e.g., "computeContractValue")
        on: Operations this hook applies to (create, update, delete)
        when: Optional expression condition (evaluated before running)
        description: Human-readable description
    """

    name: str
    on: list[Operation] = field(
        default_factory=lambda: [Operation.CREATE, Operation.UPDATE]
    )
    when: str | None = None
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HookDefinition":
        """Create HookDefinition from YAML/JSON dict."""
        operations = data.get("on", ["create", "update"])
        if isinstance(operations, str):
            operations = [operations]

        return cls(
            name=data["name"],
            on=[Operation(op) for op in operations],
            when=data.get("when"),
            description=data.get("description", ""),
        )


@dataclass
class HookContext:
    """Runtime context passed to every hook function.

    Attributes:
        entity_name: Name of the entity being operated on
        operation: The current operation (create, update, delete)
        record: Current record state (post-defaults, post-validation)
        original: Previous record state (update only, None for create)
        changes: Dict of changed fields (update only, None for create)
        user_context: Auth context (userId, tenantId, roles)
        services: Service accessor for hooks needing DB access
    """

    entity_name: str
    operation: Operation
    record: dict[str, Any]
    original: dict[str, Any] | None = None
    changes: dict[str, Any] | None = None
    user_context: UserContext | None = None
    services: Any = None  # HookServices instance (avoids circular import)


@dataclass
class HookResult:
    """Return value from beforeSave and afterSave hooks.

    Attributes:
        update: Fields to merge into the record
        abort: Error message to abort the save (rolls back transaction)
    """

    update: dict[str, Any] | None = None
    abort: str | None = None


def compute_changes(
    record: dict[str, Any], original: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Compute a diff of changed fields between record and original.

    Returns None if original is None (create operations).
    Returns a dict of {field: new_value} for fields that differ.
    """
    if original is None:
        return None

    changes: dict[str, Any] = {}
    for key, value in record.items():
        if key in original and original[key] != value:
            changes[key] = value
        elif key not in original:
            changes[key] = value

    return changes
