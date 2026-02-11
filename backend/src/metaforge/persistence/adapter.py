"""PersistenceAdapter Protocol — shared interface for all database adapters."""

from typing import Any, Protocol, runtime_checkable

from metaforge.metadata.loader import EntityModel


@runtime_checkable
class PersistenceAdapter(Protocol):
    """Interface all persistence adapters must implement.

    Matches the public API of SQLiteAdapter. Adapters for other databases
    (e.g., PostgreSQL) must conform to this protocol.
    """

    # Raw connection handle. Type varies by adapter (sqlite3.Connection,
    # sqlalchemy.engine.Connection, etc.). Used by SavedConfigStore and
    # SequenceService until they are refactored to use the adapter directly.
    conn: Any

    def connect(self) -> None: ...

    def close(self) -> None: ...

    def initialize_entity(self, entity: EntityModel) -> None: ...

    def create(
        self,
        entity: EntityModel,
        data: dict[str, Any],
        tenant_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get(self, entity: EntityModel, id: str) -> dict[str, Any] | None: ...

    def update(
        self, entity: EntityModel, id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def delete(self, entity: EntityModel, id: str) -> bool: ...

    def query(
        self,
        entity: EntityModel,
        fields: list[str] | None = None,
        filter: dict | None = None,
        sort: list[dict] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]: ...

    def aggregate(
        self,
        entity: EntityModel,
        group_by: list[str] | None = None,
        measures: list[dict] | None = None,
        filter: dict | None = None,
    ) -> dict[str, Any]: ...

    def hydrate_relations(
        self,
        records: list[dict[str, Any]],
        entity: EntityModel,
        metadata_loader: Any,
    ) -> list[dict[str, Any]]: ...

    def handle_delete_relations(
        self,
        entity: EntityModel,
        id: str,
        metadata_loader: Any,
    ) -> list[str]: ...
