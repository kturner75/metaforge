"""Sequence management for entity ID generation.

Provides sequential ID generation with format: {ABBREV}-{SEQUENCE}
Example: CMP-00001, CON-00042

Sequences are scoped based on entity scope:
- tenant-scoped entities: sequence per tenant
- global-scoped entities: one global sequence

Supports both SQLite and PostgreSQL dialects.
"""

from typing import Any


class SequenceService:
    """Manages sequences for entity ID generation."""

    def __init__(self, conn: Any, dialect: str = "sqlite"):
        """Initialize the sequence service.

        Args:
            conn: Database connection (sqlite3.Connection or psycopg.Connection).
            dialect: Database dialect — "sqlite" or "postgresql".
        """
        self.conn = conn
        self.dialect = dialect
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the sequences table if it doesn't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS _sequences (
                entity TEXT NOT NULL,
                tenant_id TEXT,
                next_value INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (entity, tenant_id)
            )
        """)
        self.conn.commit()

    def next_id(
        self,
        entity_name: str,
        abbreviation: str,
        scope: str,
        tenant_id: str | None = None,
    ) -> str:
        """Generate the next ID for an entity.

        Args:
            entity_name: The entity name (used as sequence key)
            abbreviation: The entity abbreviation (used in ID format)
            scope: "tenant" or "global"
            tenant_id: The tenant ID (required for tenant-scoped entities)

        Returns:
            Formatted ID like "CMP-00001"
        """
        # For global scope, always use None for tenant_id
        effective_tenant = tenant_id if scope == "tenant" else None

        # Get and increment sequence in a transaction
        sequence_value = self._get_and_increment(entity_name, effective_tenant)

        # Format: ABBREV-NNNNN (5 digits, zero-padded)
        return f"{abbreviation}-{sequence_value:05d}"

    def _get_and_increment(
        self,
        entity_name: str,
        tenant_id: str | None,
    ) -> int:
        """Get the next sequence value and increment atomically."""
        if self.dialect == "postgresql":
            return self._get_and_increment_postgresql(entity_name, tenant_id)
        return self._get_and_increment_sqlite(entity_name, tenant_id)

    def _get_and_increment_sqlite(
        self,
        entity_name: str,
        tenant_id: str | None,
    ) -> int:
        """SQLite implementation using SELECT + UPDATE/INSERT pattern."""
        # Use empty string for NULL tenant to simplify the query
        tenant_key = tenant_id or ""

        # Try to get existing value
        cursor = self.conn.execute(
            """
            SELECT next_value FROM _sequences
            WHERE entity = ? AND tenant_id = ?
            """,
            [entity_name, tenant_key],
        )
        row = cursor.fetchone()

        if row:
            current_value = row[0]
            # Increment
            self.conn.execute(
                """
                UPDATE _sequences
                SET next_value = next_value + 1
                WHERE entity = ? AND tenant_id = ?
                """,
                [entity_name, tenant_key],
            )
        else:
            # Insert new sequence starting at 1
            current_value = 1
            self.conn.execute(
                """
                INSERT INTO _sequences (entity, tenant_id, next_value)
                VALUES (?, ?, 2)
                """,
                [entity_name, tenant_key],
            )

        self.conn.commit()
        return current_value

    def _get_and_increment_postgresql(
        self,
        entity_name: str,
        tenant_id: str | None,
    ) -> int:
        """PostgreSQL implementation using INSERT ... ON CONFLICT DO UPDATE RETURNING.

        Atomic upsert avoids TOCTOU races; RETURNING gives us the value
        that was current before the increment so we return it to the caller.
        """
        tenant_key = tenant_id or ""

        # Atomically upsert + increment + return old value in one statement.
        # next_value is always the NEXT value to use; we read it, then bump it.
        # We return next_value BEFORE the increment (next_value - 1 after bump
        # equals the value we should use).
        result = self.conn.execute(
            """
            INSERT INTO _sequences (entity, tenant_id, next_value)
            VALUES (%s, %s, 2)
            ON CONFLICT (entity, tenant_id) DO UPDATE
                SET next_value = _sequences.next_value + 1
            RETURNING next_value - 1 AS current_value
            """,
            [entity_name, tenant_key],
        ).fetchone()

        self.conn.commit()

        if result is None:
            raise RuntimeError("Sequence upsert returned no rows")

        # psycopg dict_row returns a dict
        if isinstance(result, dict):
            return result["current_value"]
        return result[0]

    def current_value(
        self,
        entity_name: str,
        tenant_id: str | None = None,
    ) -> int:
        """Get the current sequence value without incrementing.

        Returns 0 if no sequence exists yet.
        """
        tenant_key = tenant_id or ""
        if self.dialect == "postgresql":
            placeholder = "%s"
        else:
            placeholder = "?"

        cursor = self.conn.execute(
            f"""
            SELECT next_value - 1 FROM _sequences
            WHERE entity = {placeholder} AND tenant_id = {placeholder}
            """,
            [entity_name, tenant_key],
        )
        row = cursor.fetchone()
        if row is None:
            return 0
        if isinstance(row, dict):
            return list(row.values())[0]
        return row[0]

    def reset(
        self,
        entity_name: str,
        tenant_id: str | None = None,
        start_value: int = 1,
    ) -> None:
        """Reset a sequence to a specific value.

        Use with caution - can cause ID collisions if records exist.
        """
        tenant_key = tenant_id or ""
        if self.dialect == "postgresql":
            self.conn.execute(
                """
                INSERT INTO _sequences (entity, tenant_id, next_value)
                VALUES (%s, %s, %s)
                ON CONFLICT (entity, tenant_id) DO UPDATE
                    SET next_value = EXCLUDED.next_value
                """,
                [entity_name, tenant_key, start_value],
            )
        else:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO _sequences (entity, tenant_id, next_value)
                VALUES (?, ?, ?)
                """,
                [entity_name, tenant_key, start_value],
            )
        self.conn.commit()
