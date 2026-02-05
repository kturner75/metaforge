"""View configuration types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DataPattern(str, Enum):
    QUERY = "query"
    AGGREGATE = "aggregate"
    RECORD = "record"
    COMPOSE = "compose"


class OwnerType(str, Enum):
    USER = "user"
    ROLE = "role"
    GLOBAL = "global"


class ConfigScope(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    ROLE = "role"
    GLOBAL = "global"


class ConfigSource(str, Enum):
    YAML = "yaml"
    DATABASE = "database"


@dataclass
class SavedConfig:
    """A saved view/component configuration."""

    id: str
    name: str
    pattern: DataPattern
    style: str
    data_config: dict[str, Any]
    style_config: dict[str, Any]
    entity_name: str | None = None
    description: str | None = None
    owner_type: OwnerType = OwnerType.GLOBAL
    owner_id: str | None = None
    tenant_id: str | None = None
    scope: ConfigScope = ConfigScope.GLOBAL
    source: ConfigSource = ConfigSource.DATABASE
    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response dict."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entityName": self.entity_name,
            "pattern": self.pattern.value,
            "style": self.style,
            "ownerType": self.owner_type.value,
            "ownerId": self.owner_id,
            "tenantId": self.tenant_id,
            "scope": self.scope.value,
            "dataConfig": self.data_config,
            "styleConfig": self.style_config,
            "source": self.source.value,
            "version": self.version,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "createdBy": self.created_by,
            "updatedBy": self.updated_by,
        }
