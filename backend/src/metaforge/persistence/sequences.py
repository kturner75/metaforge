"""Sequence management for entity ID generation.

Provides sequential ID generation with format: {ABBREV}-{SEQUENCE}
Example: CMP-00001, CON-00042

Sequences are scoped based on entity scope:
- tenant-scoped entities: sequence per tenant
- global-scoped entities: one global sequence
"""

import sqlite3
from typing import Any


class SequenceService:
    """Manages sequences for entity ID generation."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
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
        """Get the next sequence value and increment atomically.

        Uses INSERT OR REPLACE to handle both new and existing sequences.
        """
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

    def current_value(
        self,
        entity_name: str,
        tenant_id: str | None = None,
    ) -> int:
        """Get the current sequence value without incrementing.

        Returns 0 if no sequence exists yet.
        """
        tenant_key = tenant_id or ""
        cursor = self.conn.execute(
            """
            SELECT next_value - 1 FROM _sequences
            WHERE entity = ? AND tenant_id = ?
            """,
            [entity_name, tenant_key],
        )
        row = cursor.fetchone()
        return row[0] if row else 0

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
        self.conn.execute(
            """
            INSERT OR REPLACE INTO _sequences (entity, tenant_id, next_value)
            VALUES (?, ?, ?)
            """,
            [entity_name, tenant_key, start_value],
        )
        self.conn.commit()
