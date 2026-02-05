"""SQLite persistence adapter."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from metaforge.metadata.loader import EntityModel, FieldDefinition
from metaforge.core.types import get_storage_type
from metaforge.persistence.sequences import SequenceService


class SQLiteAdapter:
    """Simple SQLite persistence adapter."""

    def __init__(self, db_path: Path | str = ":memory:"):
        self.db_path = str(db_path)
        self.conn: sqlite3.Connection | None = None
        self._sequence_service: SequenceService | None = None

    def connect(self) -> None:
        """Establish database connection."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Initialize sequence service
        self._sequence_service = SequenceService(self.conn)

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def initialize_entity(self, entity: EntityModel) -> None:
        """Create table for entity if it doesn't exist."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        columns = []
        for field in entity.fields:
            storage_type = get_storage_type(field.type)
            col_def = f"{field.name} {storage_type}"
            if field.primary_key:
                col_def += " PRIMARY KEY"
            columns.append(col_def)

        table_name = self._table_name(entity.name)
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
        self.conn.execute(sql)
        self.conn.commit()

    def create(
        self,
        entity: EntityModel,
        data: dict[str, Any],
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new record.

        Args:
            entity: Entity metadata
            data: Record data
            tenant_id: Tenant ID for sequence scoping (for tenant-scoped entities)

        Returns:
            The created record with generated ID
        """
        if not self.conn or not self._sequence_service:
            raise RuntimeError("Database not connected")

        # Generate sequence-based ID if not provided
        pk = entity.primary_key
        if pk not in data or data[pk] is None:
            data[pk] = self._sequence_service.next_id(
                entity_name=entity.name,
                abbreviation=entity.abbreviation,
                scope=entity.scope,
                tenant_id=tenant_id,
            )

        # Add audit timestamps
        now = datetime.utcnow().isoformat()
        if "createdAt" in [f.name for f in entity.fields]:
            data.setdefault("createdAt", now)
        if "updatedAt" in [f.name for f in entity.fields]:
            data.setdefault("updatedAt", now)

        # Build INSERT
        field_names = [f.name for f in entity.fields if f.name in data]
        placeholders = ["?" for _ in field_names]
        values = [data[f] for f in field_names]

        table_name = self._table_name(entity.name)
        sql = f"INSERT INTO {table_name} ({', '.join(field_names)}) VALUES ({', '.join(placeholders)})"

        self.conn.execute(sql, values)
        self.conn.commit()

        return self.get(entity, data[pk])

    def get(self, entity: EntityModel, id: str) -> dict[str, Any] | None:
        """Fetch a single record by ID."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        sql = f"SELECT * FROM {table_name} WHERE {pk} = ?"

        cursor = self.conn.execute(sql, [id])
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def update(self, entity: EntityModel, id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing record."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        # Add audit timestamp
        if "updatedAt" in [f.name for f in entity.fields]:
            data["updatedAt"] = datetime.utcnow().isoformat()

        # Don't update primary key; read-only fields can be updated by the system
        # (e.g., computed fields like fullName)
        updatable = [
            f.name for f in entity.fields
            if f.name in data and not f.primary_key
        ]

        if not updatable:
            return self.get(entity, id)

        set_clause = ", ".join([f"{f} = ?" for f in updatable])
        values = [data[f] for f in updatable]
        values.append(id)

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {pk} = ?"

        self.conn.execute(sql, values)
        self.conn.commit()

        return self.get(entity, id)

    def delete(self, entity: EntityModel, id: str) -> bool:
        """Delete a record."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        sql = f"DELETE FROM {table_name} WHERE {pk} = ?"

        cursor = self.conn.execute(sql, [id])
        self.conn.commit()

        return cursor.rowcount > 0

    def handle_delete_relations(
        self,
        entity: EntityModel,
        id: str,
        metadata_loader: Any,
    ) -> list[str]:
        """Handle onDelete behavior for relations pointing to this entity.

        Checks all entities for relation fields that reference this entity,
        and handles based on onDelete setting:
        - restrict: Return error messages if children exist
        - cascade: Delete the child records
        - setNull: Set FK to null in child records

        Args:
            entity: The entity being deleted
            id: The ID of the record being deleted
            metadata_loader: For resolving related entities

        Returns:
            List of error messages (empty if delete can proceed)
        """
        errors: list[str] = []

        # Find all entities with relations to this entity
        for other_entity_name in metadata_loader.list_entities():
            other_entity = metadata_loader.get_entity(other_entity_name)
            if not other_entity:
                continue

            for field in other_entity.fields:
                if field.type != "relation" or not field.relation:
                    continue
                if field.relation.entity != entity.name:
                    continue

                # This field references our entity - check for existing records
                on_delete = field.relation.on_delete

                # Count children
                child_count = self._count_referencing_records(
                    other_entity, field.name, id
                )

                if child_count == 0:
                    continue  # No children, nothing to do

                if on_delete == "restrict":
                    errors.append(
                        f"Cannot delete: {child_count} {other_entity.plural_name} "
                        f"reference this {entity.name}"
                    )

                elif on_delete == "cascade":
                    # Delete all children
                    self._delete_referencing_records(
                        other_entity, field.name, id
                    )

                elif on_delete == "setNull":
                    # Check if field is required
                    if field.validation.required:
                        errors.append(
                            f"Cannot delete: {other_entity.name}.{field.name} "
                            f"is required and cannot be set to null"
                        )
                    else:
                        # Set FK to null
                        self._nullify_referencing_records(
                            other_entity, field.name, id
                        )

        return errors

    def _count_referencing_records(
        self, entity: EntityModel, fk_field: str, fk_value: str
    ) -> int:
        """Count records referencing a specific FK value."""
        if not self.conn:
            return 0

        table_name = self._table_name(entity.name)
        sql = f"SELECT COUNT(*) FROM {table_name} WHERE {fk_field} = ?"

        try:
            result = self.conn.execute(sql, [fk_value]).fetchone()
            return result[0] if result else 0
        except Exception:
            return 0

    def _delete_referencing_records(
        self, entity: EntityModel, fk_field: str, fk_value: str
    ) -> int:
        """Delete all records referencing a specific FK value."""
        if not self.conn:
            return 0

        table_name = self._table_name(entity.name)
        sql = f"DELETE FROM {table_name} WHERE {fk_field} = ?"

        try:
            cursor = self.conn.execute(sql, [fk_value])
            self.conn.commit()
            return cursor.rowcount
        except Exception:
            return 0

    def _nullify_referencing_records(
        self, entity: EntityModel, fk_field: str, fk_value: str
    ) -> int:
        """Set FK to null for all records referencing a specific value."""
        if not self.conn:
            return 0

        table_name = self._table_name(entity.name)
        sql = f"UPDATE {table_name} SET {fk_field} = NULL WHERE {fk_field} = ?"

        try:
            cursor = self.conn.execute(sql, [fk_value])
            self.conn.commit()
            return cursor.rowcount
        except Exception:
            return 0

    def query(
        self,
        entity: EntityModel,
        fields: list[str] | None = None,
        filter: dict | None = None,
        sort: list[dict] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query records with filtering, sorting, and pagination."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        table_name = self._table_name(entity.name)

        # SELECT clause
        if fields:
            select_fields = ", ".join(fields)
        else:
            select_fields = "*"

        # WHERE clause
        where_clause = ""
        where_values: list[Any] = []
        if filter and "conditions" in filter:
            conditions = []
            for cond in filter["conditions"]:
                sql_cond, vals = self._build_condition(cond)
                if sql_cond:
                    conditions.append(sql_cond)
                    where_values.extend(vals)
            if conditions:
                op = filter.get("operator", "and").upper()
                where_clause = f" WHERE {f' {op} '.join(conditions)}"

        # ORDER BY clause
        order_clause = ""
        if sort:
            order_parts = []
            for s in sort:
                direction = "DESC" if s.get("direction") == "desc" else "ASC"
                order_parts.append(f"{s['field']} {direction}")
            order_clause = f" ORDER BY {', '.join(order_parts)}"

        # Pagination
        limit_clause = ""
        if limit:
            limit_clause = f" LIMIT {limit} OFFSET {offset}"

        # Execute query
        sql = f"SELECT {select_fields} FROM {table_name}{where_clause}{order_clause}{limit_clause}"
        cursor = self.conn.execute(sql, where_values)
        rows = [dict(row) for row in cursor.fetchall()]

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM {table_name}{where_clause}"
        total = self.conn.execute(count_sql, where_values).fetchone()[0]

        return {
            "data": rows,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "hasMore": (offset + len(rows)) < total if limit else False,
            },
        }

    ALLOWED_AGGREGATES = {"count", "sum", "avg", "min", "max"}

    def aggregate(
        self,
        entity: EntityModel,
        group_by: list[str] | None = None,
        measures: list[dict] | None = None,
        filter: dict | None = None,
    ) -> dict[str, Any]:
        """Aggregate records with GROUP BY and aggregate functions.

        Args:
            entity: Entity metadata
            group_by: Fields to group by
            measures: List of {"field", "aggregate", "label?"} dicts.
                      aggregate must be one of: count, sum, avg, min, max.
                      For count, field can be "*" to count all rows.
            filter: Optional filter (same format as query())

        Returns:
            {"data": [...], "total": N} where each data item has
            the group_by fields plus measure result columns.
        """
        if not self.conn:
            raise RuntimeError("Database not connected")

        if not measures:
            return {"data": [], "total": 0}

        table_name = self._table_name(entity.name)
        entity_field_names = {f.name for f in entity.fields}

        # Validate group_by fields exist in entity
        if group_by:
            for gf in group_by:
                if gf not in entity_field_names:
                    raise ValueError(f"Unknown field '{gf}' in groupBy")

        # Build SELECT clause
        select_parts: list[str] = list(group_by) if group_by else []

        for m in measures:
            agg = m.get("aggregate", "").lower()
            agg_field = m.get("field", "")
            label = m.get("label") or f"{agg}_{agg_field}"

            if agg not in self.ALLOWED_AGGREGATES:
                raise ValueError(
                    f"Unsupported aggregate function '{agg}'. "
                    f"Allowed: {', '.join(sorted(self.ALLOWED_AGGREGATES))}"
                )

            if agg == "count" and agg_field == "*":
                select_parts.append(f"COUNT(*) AS {label}")
            elif agg == "count":
                select_parts.append(f"COUNT({agg_field}) AS {label}")
            else:
                select_parts.append(f"{agg.upper()}({agg_field}) AS {label}")

        select_clause = ", ".join(select_parts)

        # WHERE clause (reuse _build_condition)
        where_clause = ""
        where_values: list[Any] = []
        if filter and "conditions" in filter:
            conditions = []
            for cond in filter["conditions"]:
                sql_cond, vals = self._build_condition(cond)
                if sql_cond:
                    conditions.append(sql_cond)
                    where_values.extend(vals)
            if conditions:
                op = filter.get("operator", "and").upper()
                where_clause = f" WHERE {f' {op} '.join(conditions)}"

        # GROUP BY clause
        group_clause = ""
        if group_by:
            group_clause = f" GROUP BY {', '.join(group_by)}"

        sql = f"SELECT {select_clause} FROM {table_name}{where_clause}{group_clause}"
        cursor = self.conn.execute(sql, where_values)
        rows = [dict(row) for row in cursor.fetchall()]

        return {"data": rows, "total": len(rows)}

    def _build_condition(self, cond: dict) -> tuple[str, list[Any]]:
        """Build SQL condition from filter condition."""
        field = cond["field"]
        op = cond["operator"]
        value = cond.get("value")

        if op == "eq":
            return f"{field} = ?", [value]
        elif op == "neq":
            return f"{field} != ?", [value]
        elif op == "gt":
            return f"{field} > ?", [value]
        elif op == "gte":
            return f"{field} >= ?", [value]
        elif op == "lt":
            return f"{field} < ?", [value]
        elif op == "lte":
            return f"{field} <= ?", [value]
        elif op == "in":
            placeholders = ", ".join(["?" for _ in value])
            return f"{field} IN ({placeholders})", value
        elif op == "notIn":
            placeholders = ", ".join(["?" for _ in value])
            return f"{field} NOT IN ({placeholders})", value
        elif op == "contains":
            return f"{field} LIKE ?", [f"%{value}%"]
        elif op == "startsWith":
            return f"{field} LIKE ?", [f"{value}%"]
        elif op == "isNull":
            return f"{field} IS NULL", []
        elif op == "isNotNull":
            return f"{field} IS NOT NULL", []
        elif op == "between":
            return f"{field} BETWEEN ? AND ?", [value[0], value[1]]

        return "", []

    def _table_name(self, entity_name: str) -> str:
        """Convert entity name to table name."""
        # Simple snake_case conversion
        result = []
        for i, char in enumerate(entity_name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    def hydrate_relations(
        self,
        records: list[dict[str, Any]],
        entity: EntityModel,
        metadata_loader: Any,
    ) -> list[dict[str, Any]]:
        """Hydrate relation fields with display values.

        For each relation field, looks up the related record and adds
        a `{fieldName}_display` field with the display value.

        Args:
            records: List of records to hydrate
            entity: The entity metadata
            metadata_loader: Metadata loader for resolving related entities

        Returns:
            Records with display values added
        """
        if not records:
            return records

        # Find relation fields
        relation_fields = [
            f for f in entity.fields
            if f.type == "relation" and f.relation
        ]

        if not relation_fields:
            return records

        # For each relation field, batch lookup the display values
        for field in relation_fields:
            related_entity = metadata_loader.get_entity(field.relation.entity)
            if not related_entity:
                continue

            # Collect all unique IDs for this relation
            ids = list({
                r.get(field.name)
                for r in records
                if r.get(field.name) is not None
            })

            if not ids:
                continue

            # Lookup the related records
            display_field = field.relation.display_field
            related_records = self._lookup_display_values(
                related_entity, ids, display_field
            )

            # Map ID -> display value
            display_map = {
                r["id"]: r.get("_display", r.get(display_field, ""))
                for r in related_records
            }

            # Add display values to records
            display_key = f"{field.name}_display"
            for record in records:
                fk_value = record.get(field.name)
                if fk_value and fk_value in display_map:
                    record[display_key] = display_map[fk_value]
                else:
                    record[display_key] = None

        return records

    def _lookup_display_values(
        self,
        entity: EntityModel,
        ids: list[str],
        display_field: str,
    ) -> list[dict[str, Any]]:
        """Lookup display values for a list of IDs.

        Args:
            entity: The entity to lookup
            ids: List of primary key values
            display_field: The field to use for display

        Returns:
            List of records with id and display field
        """
        if not self.conn or not ids:
            return []

        table_name = self._table_name(entity.name)
        pk = entity.primary_key

        # Build query
        placeholders = ", ".join(["?" for _ in ids])
        sql = f"SELECT {pk} as id, {display_field} as _display FROM {table_name} WHERE {pk} IN ({placeholders})"

        try:
            cursor = self.conn.execute(sql, ids)
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            # If display field doesn't exist, return empty
            return []
