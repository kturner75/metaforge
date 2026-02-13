"""Load screen configurations from YAML files."""

from pathlib import Path

import yaml

from metaforge.screens.types import ScreenConfig, ScreenNav


class ScreenConfigLoader:
    """Loads screen configuration from metadata/screens/*.yaml files."""

    def __init__(self, screens_path: Path):
        self.screens_path = screens_path
        self.screens: dict[str, ScreenConfig] = {}

    def load_all(self) -> None:
        """Load all screen configs from YAML files."""
        if not self.screens_path.exists():
            return

        for yaml_file in self.screens_path.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if data and "screen" in data:
                    config = self._parse_screen(data["screen"])
                    self.screens[config.slug] = config

    def _parse_screen(self, data: dict) -> ScreenConfig:
        """Parse a screen YAML into a ScreenConfig."""
        nav_data = data.get("nav", {})
        nav = ScreenNav(
            section=nav_data.get("section", "Entities"),
            order=nav_data.get("order", 0),
            icon=nav_data.get("icon"),
            label=nav_data.get("label"),
            required_role=nav_data.get("requiredRole"),
        )

        return ScreenConfig(
            slug=data["slug"],
            name=data["name"],
            type=data.get("type", "entity"),
            entity_name=data.get("entityName"),
            nav=nav,
            views=data.get("views", {}),
            source="yaml",
        )

    def get_screen(self, slug: str) -> ScreenConfig | None:
        """Get a screen by slug."""
        return self.screens.get(slug)

    def list_screens(self) -> list[ScreenConfig]:
        """List all loaded screens."""
        return list(self.screens.values())
