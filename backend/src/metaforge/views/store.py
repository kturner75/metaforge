"""Persistence for saved view configurations.

Uses a system table (_saved_configs) following the _sequences pattern.
Config bodies (data_config, style_config) are stored as JSON text.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from metaforge.views.types import (
    ConfigScope,
    ConfigSource,
    DataPattern,
    OwnerType,
    SavedConfig,
)


class SavedConfigStore:
    """Manages saved view configurations in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the _saved_configs table if it doesn't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS _saved_configs (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                description     TEXT,
                entity_name     TEXT,
                pattern         TEXT NOT NULL,
                style           TEXT NOT NULL,
                owner_type      TEXT NOT NULL DEFAULT 'global',
                owner_id        TEXT,
                tenant_id       TEXT,
                scope           TEXT NOT NULL DEFAULT 'global',
                data_config     TEXT NOT NULL,
                style_config    TEXT NOT NULL,
                source          TEXT NOT NULL DEFAULT 'database',
                version         INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT,
                updated_at      TEXT,
                created_by      TEXT,
                updated_by      TEXT
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_saved_configs_entity
            ON _saved_configs(entity_name, pattern, style)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_saved_configs_owner
            ON _saved_configs(owner_type, owner_id, tenant_id)
        """)
        self.conn.commit()

    def _row_to_config(self, row: sqlite3.Row) -> SavedConfig:
        """Convert a database row to a SavedConfig."""
        return SavedConfig(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            entity_name=row["entity_name"],
            pattern=DataPattern(row["pattern"]),
            style=row["style"],
            owner_type=OwnerType(row["owner_type"]),
            owner_id=row["owner_id"],
            tenant_id=row["tenant_id"],
            scope=ConfigScope(row["scope"]),
            data_config=json.loads(row["data_config"]),
            style_config=json.loads(row["style_config"]),
            source=ConfigSource(row["source"]),
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=row["created_by"],
            updated_by=row["updated_by"],
        )

    def create(self, config: SavedConfig) -> SavedConfig:
        """Insert a new config. Generates ID and timestamps if not set."""
        now = datetime.now(timezone.utc).isoformat()
        config_id = config.id or uuid.uuid4().hex

        self.conn.execute(
            """
            INSERT INTO _saved_configs
                (id, name, description, entity_name, pattern, style,
                 owner_type, owner_id, tenant_id, scope,
                 data_config, style_config, source, version,
                 created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                config_id,
                config.name,
                config.description,
                config.entity_name,
                config.pattern.value,
                config.style,
                config.owner_type.value,
                config.owner_id,
                config.tenant_id,
                config.scope.value,
                json.dumps(config.data_config),
                json.dumps(config.style_config),
                config.source.value,
                config.version,
                config.created_at or now,
                config.updated_at or now,
                config.created_by,
                config.updated_by,
            ],
        )
        self.conn.commit()
        return self.get(config_id)  # type: ignore[return-value]

    def get(self, config_id: str) -> SavedConfig | None:
        """Get a config by ID."""
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT * FROM _saved_configs WHERE id = ?",
            [config_id],
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_config(row)

    def update(self, config_id: str, updates: dict[str, Any]) -> SavedConfig | None:
        """Partial update of a config. Returns updated config or None."""
        existing = self.get(config_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()

        # Build SET clause from provided updates
        allowed_fields = {
            "name", "description", "data_config", "style_config", "scope",
        }
        set_parts: list[str] = []
        values: list[Any] = []

        for field_name, value in updates.items():
            if field_name not in allowed_fields:
                continue
            if field_name in ("data_config", "style_config"):
                value = json.dumps(value)
            set_parts.append(f"{field_name} = ?")
            values.append(value)

        if not set_parts:
            return existing

        # Always bump version and updated_at
        set_parts.append("version = version + 1")
        set_parts.append("updated_at = ?")
        values.append(now)

        values.append(config_id)

        self.conn.execute(
            f"UPDATE _saved_configs SET {', '.join(set_parts)} WHERE id = ?",
            values,
        )
        self.conn.commit()
        return self.get(config_id)

    def delete(self, config_id: str) -> bool:
        """Delete a config. Returns True if deleted."""
        cursor = self.conn.execute(
            "DELETE FROM _saved_configs WHERE id = ?",
            [config_id],
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list(
        self,
        entity_name: str | None = None,
        pattern: str | None = None,
        style: str | None = None,
        owner_type: str | None = None,
        owner_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[SavedConfig]:
        """List configs with optional filters."""
        self.conn.row_factory = sqlite3.Row
        conditions: list[str] = []
        values: list[Any] = []

        if entity_name is not None:
            conditions.append("entity_name = ?")
            values.append(entity_name)
        if pattern is not None:
            conditions.append("pattern = ?")
            values.append(pattern)
        if style is not None:
            conditions.append("style = ?")
            values.append(style)
        if owner_type is not None:
            conditions.append("owner_type = ?")
            values.append(owner_type)
        if owner_id is not None:
            conditions.append("owner_id = ?")
            values.append(owner_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            values.append(tenant_id)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        cursor = self.conn.execute(
            f"SELECT * FROM _saved_configs{where} ORDER BY name",
            values,
        )
        return [self._row_to_config(row) for row in cursor.fetchall()]

    def resolve(
        self,
        entity_name: str,
        style: str,
        user_id: str | None = None,
        role: str | None = None,
        tenant_id: str | None = None,
    ) -> SavedConfig | None:
        """Resolve a config using precedence: user → role → tenant → global/yaml.

        Returns the highest-precedence config matching the criteria.
        """
        self.conn.row_factory = sqlite3.Row

        # Build a query that scores each row by precedence
        # 1 = user personal (highest), 2 = role, 3 = tenant, 4 = global/yaml (lowest)
        cursor = self.conn.execute(
            """
            SELECT *,
                CASE
                    WHEN owner_type = 'user' AND owner_id = ? THEN 1
                    WHEN owner_type = 'role' AND owner_id = ? THEN 2
                    WHEN scope = 'global' AND tenant_id = ? THEN 3
                    WHEN scope = 'global' AND tenant_id IS NULL THEN 4
                    ELSE 5
                END AS precedence
            FROM _saved_configs
            WHERE entity_name = ?
              AND style = ?
              AND (
                  (owner_type = 'user' AND owner_id = ?)
                  OR (owner_type = 'role' AND owner_id = ?)
                  OR (scope = 'global' AND (tenant_id = ? OR tenant_id IS NULL))
              )
            ORDER BY precedence ASC
            LIMIT 1
            """,
            [
                user_id, role, tenant_id,
                entity_name, style,
                user_id, role, tenant_id,
            ],
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_config(row)

    def upsert_from_yaml(self, config: SavedConfig) -> SavedConfig:
        """Insert or update a YAML-sourced config.

        If a database-sourced config already exists with the same
        entity_name + style + global scope, the YAML config is still
        stored (it serves as the fallback) but won't override user configs.
        """
        existing = self.get(config.id)
        if existing:
            # Update the YAML source record
            now = datetime.now(timezone.utc).isoformat()
            self.conn.execute(
                """
                UPDATE _saved_configs
                SET name = ?, description = ?, entity_name = ?,
                    pattern = ?, style = ?, data_config = ?,
                    style_config = ?, updated_at = ?
                WHERE id = ? AND source = 'yaml'
                """,
                [
                    config.name,
                    config.description,
                    config.entity_name,
                    config.pattern.value,
                    config.style,
                    json.dumps(config.data_config),
                    json.dumps(config.style_config),
                    now,
                    config.id,
                ],
            )
            self.conn.commit()
            return self.get(config.id)  # type: ignore[return-value]
        else:
            return self.create(config)
