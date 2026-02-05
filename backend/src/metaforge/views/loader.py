"""Load view configurations from YAML files."""

from pathlib import Path

import yaml

from metaforge.views.types import (
    ConfigScope,
    ConfigSource,
    DataPattern,
    OwnerType,
    SavedConfig,
)


class ViewConfigLoader:
    """Loads view configuration from metadata/views/*.yaml files."""

    def __init__(self, views_path: Path):
        self.views_path = views_path
        self.configs: dict[str, SavedConfig] = {}

    def load_all(self) -> None:
        """Load all view configs from YAML files."""
        if not self.views_path.exists():
            return

        for yaml_file in self.views_path.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if data and "view" in data:
                    config = self._parse_view_config(data["view"], yaml_file.stem)
                    self.configs[config.id] = config

    def _parse_view_config(self, data: dict, file_stem: str) -> SavedConfig:
        """Parse a view YAML into a SavedConfig."""
        data_section = data.get("data", {})
        return SavedConfig(
            id=f"yaml:{file_stem}",
            name=data["name"],
            description=data.get("description"),
            entity_name=data.get("entityName"),
            pattern=DataPattern(data["pattern"]),
            style=data["style"],
            owner_type=OwnerType.GLOBAL,
            owner_id=None,
            tenant_id=None,
            scope=ConfigScope.GLOBAL,
            data_config=data_section,
            style_config=data.get("styleConfig", {}),
            source=ConfigSource.YAML,
        )

    def get_config(self, config_id: str) -> SavedConfig | None:
        """Get a config by ID."""
        return self.configs.get(config_id)

    def list_configs(self) -> list[SavedConfig]:
        """List all loaded configs."""
        return list(self.configs.values())
