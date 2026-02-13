"""Screen configuration types."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScreenNav:
    """Navigation placement for a screen."""

    section: str  # e.g., "CRM", "Analytics", "Admin"
    order: int = 0  # sort order within section
    icon: str | None = None  # icon identifier (e.g., "users", "building")
    label: str | None = None  # override display name (defaults to screen.name)
    required_role: str | None = None  # minimum role to see this screen


@dataclass
class ScreenConfig:
    """A routable screen definition."""

    slug: str  # URL path segment
    name: str  # display name
    type: str  # "entity" | "dashboard" | "admin" | "custom"
    nav: ScreenNav
    entity_name: str | None = None  # only for entity/admin types
    views: dict[str, str] = field(default_factory=dict)  # mode → config ID
    source: str = "yaml"  # "yaml" | "auto"

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response dict."""
        return {
            "slug": self.slug,
            "name": self.name,
            "type": self.type,
            "entityName": self.entity_name,
            "nav": {
                "section": self.nav.section,
                "order": self.nav.order,
                "icon": self.nav.icon,
                "label": self.nav.label or self.name,
                "requiredRole": self.nav.required_role,
            },
            "views": self.views,
        }
