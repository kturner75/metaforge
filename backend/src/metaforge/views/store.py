"""Persistence for saved view configurations.

Uses a system table (_saved_configs) following the _sequences pattern.
Config bodies (data_config, style_config) are stored as JSON text.

The store accepts a SQLAlchemy database URL string and creates its own
engine internally. This makes it dialect-neutral (SQLite and PostgreSQL).
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text

from metaforge.views.types import (
    ConfigScope,
    ConfigSource,
    DataPattern,
    OwnerType,
    SavedConfig,
)


class SavedConfigStore:
    """Manages saved view configurations. Dialect-neutral via SQLAlchemy Core."""

    def __init__(self, database_url: str):
        """Initialize the store.

        Args:
            database_url: SQLAlchemy-compatible database URL.
                          Examples:
                            "sqlite:///data/metaforge.db"
                            "postgresql+psycopg://user:pass@host/db"
        """
        self._engine = create_engine(database_url)
        self._ensure_table()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """Create the _saved_configs table and indexes if they don't exist."""
        with self._engine.connect() as conn:
            conn.execute(text("""
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
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_saved_configs_entity
                ON _saved_configs(entity_name, pattern, style)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_saved_configs_owner
                ON _saved_configs(owner_type, owner_id, tenant_id)
            """))
            conn.commit()

    def _row_to_config(self, row: Any) -> SavedConfig:
        """Convert a database row (Mapping) to a SavedConfig."""
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, config: SavedConfig) -> SavedConfig:
        """Insert a new config. Generates ID and timestamps if not set."""
        now = datetime.now(UTC).isoformat()
        config_id = config.id or uuid.uuid4().hex

        with self._engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO _saved_configs
                        (id, name, description, entity_name, pattern, style,
                         owner_type, owner_id, tenant_id, scope,
                         data_config, style_config, source, version,
                         created_at, updated_at, created_by, updated_by)
                    VALUES
                        (:id, :name, :description, :entity_name, :pattern, :style,
                         :owner_type, :owner_id, :tenant_id, :scope,
                         :data_config, :style_config, :source, :version,
                         :created_at, :updated_at, :created_by, :updated_by)
                """),
                {
                    "id": config_id,
                    "name": config.name,
                    "description": config.description,
                    "entity_name": config.entity_name,
                    "pattern": config.pattern.value,
                    "style": config.style,
                    "owner_type": config.owner_type.value,
                    "owner_id": config.owner_id,
                    "tenant_id": config.tenant_id,
                    "scope": config.scope.value,
                    "data_config": json.dumps(config.data_config),
                    "style_config": json.dumps(config.style_config),
                    "source": config.source.value,
                    "version": config.version,
                    "created_at": config.created_at or now,
                    "updated_at": config.updated_at or now,
                    "created_by": config.created_by,
                    "updated_by": config.updated_by,
                },
            )
            conn.commit()

        return self.get(config_id)  # type: ignore[return-value]

    def get(self, config_id: str) -> SavedConfig | None:
        """Get a config by ID."""
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM _saved_configs WHERE id = :id"),
                {"id": config_id},
            ).mappings().fetchone()

        if not row:
            return None
        return self._row_to_config(row)

    def update(self, config_id: str, updates: dict[str, Any]) -> SavedConfig | None:
        """Partial update of a config. Returns updated config or None."""
        existing = self.get(config_id)
        if not existing:
            return None

        now = datetime.now(UTC).isoformat()

        allowed_fields = {
            "name", "description", "data_config", "style_config", "scope",
        }
        set_parts: list[str] = []
        params: dict[str, Any] = {}

        for field_name, value in updates.items():
            if field_name not in allowed_fields:
                continue
            if field_name in ("data_config", "style_config"):
                value = json.dumps(value)
            set_parts.append(f"{field_name} = :{field_name}")
            params[field_name] = value

        if not set_parts:
            return existing

        # Always bump version and updated_at
        set_parts.append("version = version + 1")
        set_parts.append("updated_at = :updated_at")
        params["updated_at"] = now
        params["config_id"] = config_id

        with self._engine.connect() as conn:
            conn.execute(
                text(
                    f"UPDATE _saved_configs SET {', '.join(set_parts)} WHERE id = :config_id"
                ),
                params,
            )
            conn.commit()

        return self.get(config_id)

    def delete(self, config_id: str) -> bool:
        """Delete a config. Returns True if deleted."""
        with self._engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM _saved_configs WHERE id = :id"),
                {"id": config_id},
            )
            conn.commit()
            return result.rowcount > 0

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
        conditions: list[str] = []
        params: dict[str, Any] = {}

        if entity_name is not None:
            conditions.append("entity_name = :entity_name")
            params["entity_name"] = entity_name
        if pattern is not None:
            conditions.append("pattern = :pattern")
            params["pattern"] = pattern
        if style is not None:
            conditions.append("style = :style")
            params["style"] = style
        if owner_type is not None:
            conditions.append("owner_type = :owner_type")
            params["owner_type"] = owner_type
        if owner_id is not None:
            conditions.append("owner_id = :owner_id")
            params["owner_id"] = owner_id
        if tenant_id is not None:
            conditions.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM _saved_configs{where} ORDER BY name"

        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().fetchall()

        return [self._row_to_config(row) for row in rows]

    def resolve(
        self,
        entity_name: str,
        style: str,
        user_id: str | None = None,
        role: str | None = None,
        tenant_id: str | None = None,
    ) -> SavedConfig | None:
        """Resolve a config using precedence: user → role → tenant → global/yaml."""
        with self._engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT *,
                        CASE
                            WHEN owner_type = 'user' AND owner_id = :user_id THEN 1
                            WHEN owner_type = 'role' AND owner_id = :role THEN 2
                            WHEN scope = 'global' AND tenant_id = :tenant_id THEN 3
                            WHEN scope = 'global' AND tenant_id IS NULL THEN 4
                            ELSE 5
                        END AS precedence
                    FROM _saved_configs
                    WHERE entity_name = :entity_name
                      AND style = :style
                      AND (
                          (owner_type = 'user' AND owner_id = :user_id)
                          OR (owner_type = 'role' AND owner_id = :role)
                          OR (scope = 'global' AND (tenant_id = :tenant_id OR tenant_id IS NULL))
                      )
                    ORDER BY precedence ASC
                    LIMIT 1
                """),
                {
                    "user_id": user_id,
                    "role": role,
                    "tenant_id": tenant_id,
                    "entity_name": entity_name,
                    "style": style,
                },
            ).mappings().fetchone()

        if not row:
            return None
        return self._row_to_config(row)

    def upsert_from_yaml(self, config: SavedConfig) -> SavedConfig:
        """Insert or update a YAML-sourced config."""
        existing = self.get(config.id)
        if existing:
            now = datetime.now(UTC).isoformat()
            with self._engine.connect() as conn:
                conn.execute(
                    text("""
                        UPDATE _saved_configs
                        SET name = :name, description = :description,
                            entity_name = :entity_name,
                            pattern = :pattern, style = :style,
                            data_config = :data_config,
                            style_config = :style_config, updated_at = :updated_at
                        WHERE id = :id AND source = 'yaml'
                    """),
                    {
                        "name": config.name,
                        "description": config.description,
                        "entity_name": config.entity_name,
                        "pattern": config.pattern.value,
                        "style": config.style,
                        "data_config": json.dumps(config.data_config),
                        "style_config": json.dumps(config.style_config),
                        "updated_at": now,
                        "id": config.id,
                    },
                )
                conn.commit()
            return self.get(config.id)  # type: ignore[return-value]
        else:
            return self.create(config)
