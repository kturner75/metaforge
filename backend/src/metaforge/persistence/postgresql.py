"""PostgreSQL persistence adapter.

Uses psycopg v3 (psycopg[binary]>=3.1.0) for database access.
Mirrors SQLiteAdapter method-for-method with PostgreSQL-specific SQL:
  - %s placeholders instead of ?
  - DATE_TRUNC() instead of strftime()
  - INSERT ... ON CONFLICT DO UPDATE for sequences
  - dict_row cursor factory for dict-based row access

Identifier quoting strategy
----------------------------
PostgreSQL folds unquoted identifiers to lowercase. MetaForge uses
camelCase field names (e.g. ``firstName``, ``createdAt``), so every
table name and column name in DDL and DML must be double-quoted to
preserve the original casing and avoid conflicts with reserved words
such as ``user``, ``order``, ``group``, and ``default``.

Helper methods:
  ``_table_name(entity_name)`` → ``"snake_case_name"``
  ``_col(name)``               → ``"name"`` (quoted column identifier)
  ``_select_cols(entity)``     → comma-separated list of
                                  ``"col" AS "col"`` expressions so that
                                  dict_row always yields the original
                                  camelCase keys even though PostgreSQL
                                  stores column names in lowercase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from metaforge.core.types import get_storage_type
from metaforge.metadata.loader import EntityModel
from metaforge.persistence.sequences import SequenceService


def _col(name: str) -> str:
    """Return a double-quoted PostgreSQL column identifier.

    Example: _col("firstName") → '"firstName"'
    """
    return f'"{name}"'


class PostgreSQLAdapter:
    """PostgreSQL persistence adapter using psycopg v3."""

    def __init__(self, url: str):
        # Accept both postgresql:// and postgresql+psycopg:// URLs.
        # psycopg.connect() wants a plain libpq DSN or postgres:// URL,
        # so strip the +psycopg driver suffix when present.
        self.url = url.replace("postgresql+psycopg://", "postgresql://")
        self.conn: Any = None
        self._sequence_service: SequenceService | None = None

    def connect(self) -> None:
        """Establish database connection."""
        import psycopg
        from psycopg.rows import dict_row

        self.conn = psycopg.connect(self.url, row_factory=dict_row)
        self.conn.autocommit = False
        # Initialize sequence service
        self._sequence_service = SequenceService(self.conn, dialect="postgresql")

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    # ------------------------------------------------------------------
    # Identifier helpers
    # ------------------------------------------------------------------

    def _table_name(self, entity_name: str) -> str:
        """Convert entity name to a double-quoted snake_case table name.

        Quoting prevents conflicts with PostgreSQL reserved words
        (e.g. 'user', 'order', 'group') while preserving exact case.
        """
        result = []
        for i, char in enumerate(entity_name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        snake = "".join(result)
        return f'"{snake}"'

    def _select_cols(self, entity: EntityModel) -> str:
        """Build a SELECT column list that preserves camelCase key names.

        PostgreSQL stores column names in lowercase so ``SELECT *``
        returns lowercased keys. By aliasing each column back to its
        original name we ensure dict_row returns ``{"firstName": ...}``
        instead of ``{"firstname": ...}``.

        Example output::
            "id" AS "id", "firstName" AS "firstName", "createdAt" AS "createdAt"
        """
        parts = [f'{_col(f.name)} AS {_col(f.name)}' for f in entity.fields]
        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Entity initialization
    # ------------------------------------------------------------------

    def initialize_entity(self, entity: EntityModel) -> None:
        """Create table for entity if it doesn't exist."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        columns = []
        for field in entity.fields:
            storage_type = get_storage_type(field.type)
            # Map SQLite storage types to PostgreSQL equivalents
            pg_type = _sqlite_to_pg_type(storage_type)
            col_def = f"{_col(field.name)} {pg_type}"
            if field.primary_key:
                col_def += " PRIMARY KEY"
            columns.append(col_def)

        table_name = self._table_name(entity.name)
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
        self.conn.execute(sql)
        self.conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

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
            tenant_id: Tenant ID for sequence scoping

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

        # Build INSERT with quoted column names
        field_names = [f.name for f in entity.fields if f.name in data]
        quoted_cols = ", ".join(_col(n) for n in field_names)
        placeholders = ", ".join("%s" for _ in field_names)
        values = [data[f] for f in field_names]

        table_name = self._table_name(entity.name)
        sql = f"INSERT INTO {table_name} ({quoted_cols}) VALUES ({placeholders})"

        self.conn.execute(sql, values)
        self.conn.commit()

        return self.get(entity, data[pk])  # type: ignore[return-value]

    def get(self, entity: EntityModel, id: str) -> dict[str, Any] | None:
        """Fetch a single record by ID."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        select_cols = self._select_cols(entity)
        sql = f"SELECT {select_cols} FROM {table_name} WHERE {_col(pk)} = %s"

        cursor = self.conn.execute(sql, [id])
        row = cursor.fetchone()

        return dict(row) if row else None

    def update(self, entity: EntityModel, id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing record."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        # Add audit timestamp
        if "updatedAt" in [f.name for f in entity.fields]:
            data["updatedAt"] = datetime.utcnow().isoformat()

        updatable = [
            f.name for f in entity.fields
            if f.name in data and not f.primary_key
        ]

        if not updatable:
            return self.get(entity, id)

        set_clause = ", ".join([f"{_col(f)} = %s" for f in updatable])
        values = [data[f] for f in updatable]
        values.append(id)

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {_col(pk)} = %s"

        self.conn.execute(sql, values)
        self.conn.commit()

        return self.get(entity, id)

    def delete(self, entity: EntityModel, id: str) -> bool:
        """Delete a record."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        sql = f"DELETE FROM {table_name} WHERE {_col(pk)} = %s"

        cursor = self.conn.execute(sql, [id])
        self.conn.commit()

        return cursor.rowcount > 0

    # -----------------------------------------------------------------
    # Transaction management for hook system
    # -----------------------------------------------------------------

    def create_no_commit(
        self,
        entity: EntityModel,
        data: dict[str, Any],
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new record without committing."""
        if not self.conn or not self._sequence_service:
            raise RuntimeError("Database not connected")

        pk = entity.primary_key
        if pk not in data or data[pk] is None:
            data[pk] = self._sequence_service.next_id(
                entity_name=entity.name,
                abbreviation=entity.abbreviation,
                scope=entity.scope,
                tenant_id=tenant_id,
            )

        now = datetime.utcnow().isoformat()
        if "createdAt" in [f.name for f in entity.fields]:
            data.setdefault("createdAt", now)
        if "updatedAt" in [f.name for f in entity.fields]:
            data.setdefault("updatedAt", now)

        field_names = [f.name for f in entity.fields if f.name in data]
        quoted_cols = ", ".join(_col(n) for n in field_names)
        placeholders = ", ".join("%s" for _ in field_names)
        values = [data[f] for f in field_names]

        table_name = self._table_name(entity.name)
        sql = f"INSERT INTO {table_name} ({quoted_cols}) VALUES ({placeholders})"

        self.conn.execute(sql, values)
        # No commit — caller manages transaction

        return self.get(entity, data[pk])  # type: ignore[return-value]

    def update_no_commit(
        self, entity: EntityModel, id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a record without committing."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        if "updatedAt" in [f.name for f in entity.fields]:
            data["updatedAt"] = datetime.utcnow().isoformat()

        updatable = [
            f.name for f in entity.fields
            if f.name in data and not f.primary_key
        ]

        if not updatable:
            return self.get(entity, id)

        set_clause = ", ".join([f"{_col(f)} = %s" for f in updatable])
        values = [data[f] for f in updatable]
        values.append(id)

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {_col(pk)} = %s"

        self.conn.execute(sql, values)
        # No commit — caller manages transaction

        return self.get(entity, id)

    def delete_no_commit(self, entity: EntityModel, id: str) -> bool:
        """Delete a record without committing."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        table_name = self._table_name(entity.name)
        pk = entity.primary_key
        sql = f"DELETE FROM {table_name} WHERE {_col(pk)} = %s"

        cursor = self.conn.execute(sql, [id])
        # No commit — caller manages transaction

        return cursor.rowcount > 0

    def commit(self) -> None:
        """Commit the current transaction."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        self.conn.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        self.conn.rollback()

    # ------------------------------------------------------------------
    # Relation handling
    # ------------------------------------------------------------------

    def handle_delete_relations(
        self,
        entity: EntityModel,
        id: str,
        metadata_loader: Any,
    ) -> list[str]:
        """Handle onDelete behavior for relations pointing to this entity."""
        errors: list[str] = []

        for other_entity_name in metadata_loader.list_entities():
            other_entity = metadata_loader.get_entity(other_entity_name)
            if not other_entity:
                continue

            for field in other_entity.fields:
                if field.type != "relation" or not field.relation:
                    continue
                if field.relation.entity != entity.name:
                    continue

                on_delete = field.relation.on_delete
                child_count = self._count_referencing_records(
                    other_entity, field.name, id
                )

                if child_count == 0:
                    continue

                if on_delete == "restrict":
                    errors.append(
                        f"Cannot delete: {child_count} {other_entity.plural_name} "
                        f"reference this {entity.name}"
                    )

                elif on_delete == "cascade":
                    self._delete_referencing_records(other_entity, field.name, id)

                elif on_delete == "setNull":
                    if field.validation.required:
                        errors.append(
                            f"Cannot delete: {other_entity.name}.{field.name} "
                            f"is required and cannot be set to null"
                        )
                    else:
                        self._nullify_referencing_records(other_entity, field.name, id)

        return errors

    def _count_referencing_records(
        self, entity: EntityModel, fk_field: str, fk_value: str
    ) -> int:
        """Count records referencing a specific FK value."""
        if not self.conn:
            return 0

        table_name = self._table_name(entity.name)
        sql = f"SELECT COUNT(*) FROM {table_name} WHERE {_col(fk_field)} = %s"

        try:
            result = self.conn.execute(sql, [fk_value]).fetchone()
            # psycopg dict_row returns a dict; COUNT(*) key is "count"
            if result is None:
                return 0
            if isinstance(result, dict):
                return list(result.values())[0]
            return result[0]
        except Exception:
            return 0

    def _delete_referencing_records(
        self, entity: EntityModel, fk_field: str, fk_value: str
    ) -> int:
        """Delete all records referencing a specific FK value."""
        if not self.conn:
            return 0

        table_name = self._table_name(entity.name)
        sql = f"DELETE FROM {table_name} WHERE {_col(fk_field)} = %s"

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
        sql = (
            f"UPDATE {table_name}"
            f" SET {_col(fk_field)} = NULL"
            f" WHERE {_col(fk_field)} = %s"
        )

        try:
            cursor = self.conn.execute(sql, [fk_value])
            self.conn.commit()
            return cursor.rowcount
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

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

        # SELECT clause — always use explicit aliases to preserve camelCase
        if fields:
            select_fields = ", ".join(
                f"{_col(f)} AS {_col(f)}" for f in fields
            )
        else:
            select_fields = self._select_cols(entity)

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
                order_parts.append(f"{_col(s['field'])} {direction}")
            order_clause = f" ORDER BY {', '.join(order_parts)}"

        # Pagination
        limit_clause = ""
        if limit:
            limit_clause = f" LIMIT {limit} OFFSET {offset}"

        sql = (
            f"SELECT {select_fields} FROM {table_name}"
            f"{where_clause}{order_clause}{limit_clause}"
        )
        cursor = self.conn.execute(sql, where_values)
        rows = [dict(row) for row in cursor.fetchall()]

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM {table_name}{where_clause}"
        count_row = self.conn.execute(count_sql, where_values).fetchone()
        if isinstance(count_row, dict):
            total = list(count_row.values())[0]
        else:
            total = count_row[0]

        return {
            "data": rows,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "hasMore": (offset + len(rows)) < total if limit else False,
            },
        }

    # ------------------------------------------------------------------
    # Aggregate
    # ------------------------------------------------------------------

    ALLOWED_AGGREGATES = {"count", "sum", "avg", "min", "max"}

    # PostgreSQL DATE_TRUNC level names
    DATE_TRUNC_LEVELS: dict[str, str] = {
        "day": "day",
        "week": "week",
        "month": "month",
        "year": "year",
    }

    def aggregate(
        self,
        entity: EntityModel,
        group_by: list[str] | None = None,
        measures: list[dict] | None = None,
        filter: dict | None = None,
        date_trunc: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Aggregate records with GROUP BY and aggregate functions.

        Args:
            entity: Entity metadata
            group_by: Fields to group by
            measures: List of {"field", "aggregate", "label?"} dicts.
            filter: Optional filter
            date_trunc: Optional mapping of field names to truncation levels
                        (day, week, month, year). Uses DATE_TRUNC() on PostgreSQL.

        Returns:
            {"data": [...], "total": N}
        """
        if not self.conn:
            raise RuntimeError("Database not connected")

        if not measures:
            return {"data": [], "total": 0}

        table_name = self._table_name(entity.name)
        entity_field_names = {f.name for f in entity.fields}

        # Validate date_trunc levels
        if date_trunc:
            for field, level in date_trunc.items():
                if level not in self.DATE_TRUNC_LEVELS:
                    raise ValueError(
                        f"Unsupported dateTrunc level '{level}' for field '{field}'. "
                        f"Allowed: {', '.join(sorted(self.DATE_TRUNC_LEVELS))}"
                    )

        # Validate group_by fields
        if group_by:
            for gf in group_by:
                if gf not in entity_field_names:
                    raise ValueError(f"Unknown field '{gf}' in groupBy")

        # Build SELECT and GROUP BY parts, quoting column references
        select_parts: list[str] = []
        group_parts: list[str] = []
        if group_by:
            for gf in group_by:
                trunc_level = (date_trunc or {}).get(gf)
                if trunc_level:
                    pg_level = self.DATE_TRUNC_LEVELS[trunc_level]
                    # Cast to timestamp for DATE_TRUNC; TEXT columns need explicit cast
                    expr = f"DATE_TRUNC('{pg_level}', {_col(gf)}::timestamp)"
                    # Return as text to match SQLite strftime output format
                    if trunc_level == "day":
                        select_parts.append(
                            f"TO_CHAR({expr}, 'YYYY-MM-DD') AS {_col(gf)}"
                        )
                    elif trunc_level == "week":
                        select_parts.append(
                            f'TO_CHAR({expr}, \'YYYY-"W"IW\') AS {_col(gf)}'
                        )
                    elif trunc_level == "month":
                        select_parts.append(
                            f"TO_CHAR({expr}, 'YYYY-MM') AS {_col(gf)}"
                        )
                    elif trunc_level == "year":
                        select_parts.append(
                            f"TO_CHAR({expr}, 'YYYY') AS {_col(gf)}"
                        )
                    group_parts.append(expr)
                else:
                    select_parts.append(f"{_col(gf)} AS {_col(gf)}")
                    group_parts.append(_col(gf))

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
                select_parts.append(f"COUNT(*) AS {_col(label)}")
            elif agg == "count":
                select_parts.append(f"COUNT({_col(agg_field)}) AS {_col(label)}")
            else:
                select_parts.append(
                    f"{agg.upper()}({_col(agg_field)}) AS {_col(label)}"
                )

        select_clause = ", ".join(select_parts)

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

        # GROUP BY clause
        group_clause = f" GROUP BY {', '.join(group_parts)}" if group_parts else ""

        # ORDER BY
        order_clause = f" ORDER BY {', '.join(group_parts)}" if group_parts else ""

        sql = (
            f"SELECT {select_clause} FROM {table_name}"
            f"{where_clause}{group_clause}{order_clause}"
        )
        cursor = self.conn.execute(sql, where_values)
        rows = [dict(row) for row in cursor.fetchall()]

        return {"data": rows, "total": len(rows)}

    # ------------------------------------------------------------------
    # Filter conditions
    # ------------------------------------------------------------------

    def _build_condition(self, cond: dict) -> tuple[str, list[Any]]:
        """Build SQL condition from filter condition dict.

        Column names are double-quoted to preserve camelCase and avoid
        clashes with reserved words.
        """
        field = _col(cond["field"])
        op = cond["operator"]
        value = cond.get("value")

        if op == "eq":
            return f"{field} = %s", [value]
        elif op == "neq":
            return f"{field} != %s", [value]
        elif op == "gt":
            return f"{field} > %s", [value]
        elif op == "gte":
            return f"{field} >= %s", [value]
        elif op == "lt":
            return f"{field} < %s", [value]
        elif op == "lte":
            return f"{field} <= %s", [value]
        elif op == "in":
            placeholders = ", ".join(["%s" for _ in value])
            return f"{field} IN ({placeholders})", value
        elif op == "notIn":
            placeholders = ", ".join(["%s" for _ in value])
            return f"{field} NOT IN ({placeholders})", value
        elif op == "contains":
            return f"{field} LIKE %s", [f"%{value}%"]
        elif op == "startsWith":
            return f"{field} LIKE %s", [f"{value}%"]
        elif op == "isNull":
            return f"{field} IS NULL", []
        elif op == "isNotNull":
            return f"{field} IS NOT NULL", []
        elif op == "between":
            return f"{field} BETWEEN %s AND %s", [value[0], value[1]]

        return "", []

    # ------------------------------------------------------------------
    # Relation hydration
    # ------------------------------------------------------------------

    def hydrate_relations(
        self,
        records: list[dict[str, Any]],
        entity: EntityModel,
        metadata_loader: Any,
    ) -> list[dict[str, Any]]:
        """Hydrate relation fields with display values."""
        if not records:
            return records

        relation_fields = [
            f for f in entity.fields
            if f.type == "relation" and f.relation
        ]

        if not relation_fields:
            return records

        for field in relation_fields:
            related_entity = metadata_loader.get_entity(field.relation.entity)
            if not related_entity:
                continue

            ids = list({
                r.get(field.name)
                for r in records
                if r.get(field.name) is not None
            })

            if not ids:
                continue

            display_field = field.relation.display_field
            related_records = self._lookup_display_values(
                related_entity, ids, display_field
            )

            display_map = {
                r["id"]: r.get("_display", r.get(display_field, ""))
                for r in related_records
            }

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
        """Lookup display values for a list of IDs."""
        if not self.conn or not ids:
            return []

        table_name = self._table_name(entity.name)
        pk = entity.primary_key

        placeholders = ", ".join(["%s" for _ in ids])
        sql = (
            f"SELECT {_col(pk)} AS {_col('id')},"
            f" {_col(display_field)} AS {_col('_display')}"
            f" FROM {table_name} WHERE {_col(pk)} IN ({placeholders})"
        )

        try:
            cursor = self.conn.execute(sql, ids)
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []


# ------------------------------------------------------------------
# Type mapping helper
# ------------------------------------------------------------------

def _sqlite_to_pg_type(sqlite_type: str) -> str:
    """Map SQLite column types to PostgreSQL equivalents.

    SQLite uses TEXT, INTEGER, REAL as storage types.
    PostgreSQL uses TEXT, INTEGER, DOUBLE PRECISION.
    """
    mapping = {
        "TEXT": "TEXT",
        "INTEGER": "INTEGER",
        "REAL": "DOUBLE PRECISION",
        "NUMERIC": "NUMERIC",
        "BLOB": "BYTEA",
    }
    return mapping.get(sqlite_type.upper(), "TEXT")
