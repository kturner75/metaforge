"""Screen and navigation API endpoints."""

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request

from metaforge.metadata.loader import MetadataLoader
from metaforge.screens.loader import ScreenConfigLoader
from metaforge.screens.types import ScreenConfig, ScreenNav
from metaforge.auth.permissions import has_role_or_higher
from metaforge.validation import UserContext


def _get_user_context(request: Request) -> UserContext | None:
    """Extract user context from request state."""
    return getattr(request.state, "user_context", None)


def _auto_screen_for_entity(entity_name: str, metadata_loader: MetadataLoader) -> ScreenConfig:
    """Generate a default screen for an entity that has no screen YAML."""
    entity = metadata_loader.get_entity(entity_name)
    plural = entity.plural_name if entity else f"{entity_name}s"
    slug = plural.lower().replace(" ", "-")

    return ScreenConfig(
        slug=slug,
        name=plural,
        type="entity",
        entity_name=entity_name,
        nav=ScreenNav(
            section="Entities",
            order=99,
            label=plural,
        ),
        views={},
        source="auto",
    )


def _build_all_screens(
    screen_loader: ScreenConfigLoader,
    metadata_loader: MetadataLoader,
) -> list[ScreenConfig]:
    """Build the complete list of screens: YAML-defined + auto-generated for uncovered entities."""
    screens = list(screen_loader.list_screens())

    # Collect entity names already covered by screen YAML
    covered_entities = {s.entity_name for s in screens if s.entity_name}

    # Skip internal/system entities from auto-generation
    skip_entities = {"User", "Tenant", "TenantMembership"}

    # Auto-generate screens for entities without screen YAML
    for entity_name in metadata_loader.list_entities():
        if entity_name not in covered_entities and entity_name not in skip_entities:
            screens.append(_auto_screen_for_entity(entity_name, metadata_loader))

    return screens


def _filter_by_permissions(
    screens: list[ScreenConfig],
    user_context: UserContext | None,
) -> list[ScreenConfig]:
    """Filter screens by the user's role."""
    result = []
    for screen in screens:
        required = screen.nav.required_role
        if required:
            if not has_role_or_higher(user_context, required):
                continue
        result.append(screen)
    return result


def _build_navigation(screens: list[ScreenConfig]) -> list[dict[str, Any]]:
    """Group screens into navigation sections, sorted by order."""
    sections: dict[str, list[ScreenConfig]] = {}
    for screen in screens:
        section_name = screen.nav.section
        if section_name not in sections:
            sections[section_name] = []
        sections[section_name].append(screen)

    # Sort screens within each section by order
    for section_screens in sections.values():
        section_screens.sort(key=lambda s: s.nav.order)

    # Sort sections by the minimum order of their screens
    sorted_sections = sorted(
        sections.items(),
        key=lambda pair: min(s.nav.order for s in pair[1]) if pair[1] else 999,
    )

    return [
        {
            "name": name,
            "screens": [
                {
                    "slug": s.slug,
                    "label": s.nav.label or s.name,
                    "icon": s.nav.icon,
                    "type": s.type,
                }
                for s in section_screens
            ],
        }
        for name, section_screens in sorted_sections
    ]


def create_screens_router(
    get_screen_loader: Callable[[], ScreenConfigLoader | None],
    get_metadata_loader: Callable[[], MetadataLoader | None],
) -> APIRouter:
    """Create the screens/navigation router with injected dependencies."""
    router = APIRouter(prefix="/api", tags=["screens"])

    @router.get("/navigation")
    async def get_navigation(http_request: Request) -> dict[str, Any]:
        """Return the navigation tree for the current user, filtered by permissions."""
        screen_loader = get_screen_loader()
        metadata_loader = get_metadata_loader()
        if not screen_loader or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        user_context = _get_user_context(http_request)
        all_screens = _build_all_screens(screen_loader, metadata_loader)
        visible_screens = _filter_by_permissions(all_screens, user_context)
        sections = _build_navigation(visible_screens)

        # Default screen: first screen of the first section
        default_screen = "contacts"
        if sections and sections[0]["screens"]:
            default_screen = sections[0]["screens"][0]["slug"]

        return {
            "sections": sections,
            "defaultScreen": default_screen,
        }

    @router.get("/screens/{slug}")
    async def get_screen(slug: str) -> dict[str, Any]:
        """Return the full screen definition for a given slug."""
        screen_loader = get_screen_loader()
        metadata_loader = get_metadata_loader()
        if not screen_loader or not metadata_loader:
            raise HTTPException(500, "Service not initialized")

        screen = screen_loader.get_screen(slug)

        # Fall back to auto-generated screen
        if not screen:
            for entity_name in metadata_loader.list_entities():
                auto = _auto_screen_for_entity(entity_name, metadata_loader)
                if auto.slug == slug:
                    screen = auto
                    break

        if not screen:
            raise HTTPException(404, f"Screen not found: {slug}")

        return {"data": screen.to_dict()}

    return router
