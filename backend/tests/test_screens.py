"""Tests for screen configuration system — loader, types, and navigation API."""

import textwrap
from pathlib import Path

import pytest
import yaml

from metaforge.screens.types import ScreenConfig, ScreenNav
from metaforge.screens.loader import ScreenConfigLoader
from metaforge.screens.endpoints import (
    _auto_screen_for_entity,
    _build_all_screens,
    _build_navigation,
    _filter_by_permissions,
)
from metaforge.validation import UserContext


# ── Fixtures ──


@pytest.fixture
def tmp_screens_dir(tmp_path: Path) -> Path:
    """Create a temp directory with sample screen YAML files."""
    screens_dir = tmp_path / "screens"
    screens_dir.mkdir()

    # Entity screen
    contacts_yaml = {
        "screen": {
            "name": "Contacts",
            "slug": "contacts",
            "type": "entity",
            "entityName": "Contact",
            "nav": {"section": "CRM", "order": 1, "icon": "users"},
            "views": {
                "list": "yaml:contact-grid",
                "detail": "yaml:contact-detail",
                "create": "yaml:contact-form",
                "edit": "yaml:contact-form",
            },
        }
    }
    (screens_dir / "contacts.yaml").write_text(yaml.dump(contacts_yaml))

    # Dashboard screen
    dashboard_yaml = {
        "screen": {
            "name": "Sales Dashboard",
            "slug": "sales-dashboard",
            "type": "dashboard",
            "nav": {"section": "Analytics", "order": 1, "icon": "bar-chart"},
            "views": {"default": "yaml:sales-dashboard"},
        }
    }
    (screens_dir / "sales-dashboard.yaml").write_text(yaml.dump(dashboard_yaml))

    # Admin screen with requiredRole
    admin_yaml = {
        "screen": {
            "name": "User Management",
            "slug": "admin-users",
            "type": "admin",
            "entityName": "User",
            "nav": {
                "section": "Admin",
                "order": 1,
                "icon": "shield",
                "requiredRole": "admin",
            },
            "views": {"list": "yaml:user-grid"},
        }
    }
    (screens_dir / "admin-users.yaml").write_text(yaml.dump(admin_yaml))

    return screens_dir


@pytest.fixture
def loaded_screens(tmp_screens_dir: Path) -> ScreenConfigLoader:
    """Return a loader with all temp screens loaded."""
    loader = ScreenConfigLoader(tmp_screens_dir)
    loader.load_all()
    return loader


# ── ScreenConfig & ScreenNav ──


class TestScreenTypes:
    def test_screen_config_to_dict(self):
        nav = ScreenNav(section="CRM", order=1, icon="users", label="Contacts")
        screen = ScreenConfig(
            slug="contacts",
            name="Contacts",
            type="entity",
            entity_name="Contact",
            nav=nav,
            views={"list": "yaml:contact-grid"},
        )
        d = screen.to_dict()
        assert d["slug"] == "contacts"
        assert d["name"] == "Contacts"
        assert d["type"] == "entity"
        assert d["entityName"] == "Contact"
        assert d["nav"]["section"] == "CRM"
        assert d["nav"]["order"] == 1
        assert d["nav"]["icon"] == "users"
        assert d["nav"]["label"] == "Contacts"
        assert d["views"]["list"] == "yaml:contact-grid"

    def test_screen_config_to_dict_label_defaults_to_name(self):
        nav = ScreenNav(section="CRM", order=1)
        screen = ScreenConfig(slug="x", name="My Screen", type="entity", nav=nav)
        d = screen.to_dict()
        assert d["nav"]["label"] == "My Screen"

    def test_screen_config_to_dict_required_role(self):
        nav = ScreenNav(section="Admin", order=1, required_role="admin")
        screen = ScreenConfig(slug="x", name="Admin", type="admin", nav=nav)
        d = screen.to_dict()
        assert d["nav"]["requiredRole"] == "admin"


# ── ScreenConfigLoader ──


class TestScreenConfigLoader:
    def test_loads_all_yaml_screens(self, loaded_screens: ScreenConfigLoader):
        screens = loaded_screens.list_screens()
        assert len(screens) == 3
        slugs = {s.slug for s in screens}
        assert slugs == {"contacts", "sales-dashboard", "admin-users"}

    def test_entity_screen_parsed_correctly(self, loaded_screens: ScreenConfigLoader):
        screen = loaded_screens.get_screen("contacts")
        assert screen is not None
        assert screen.name == "Contacts"
        assert screen.type == "entity"
        assert screen.entity_name == "Contact"
        assert screen.nav.section == "CRM"
        assert screen.nav.order == 1
        assert screen.nav.icon == "users"
        assert screen.views["list"] == "yaml:contact-grid"
        assert screen.views["detail"] == "yaml:contact-detail"
        assert screen.source == "yaml"

    def test_dashboard_screen_parsed_correctly(self, loaded_screens: ScreenConfigLoader):
        screen = loaded_screens.get_screen("sales-dashboard")
        assert screen is not None
        assert screen.type == "dashboard"
        assert screen.entity_name is None
        assert screen.views["default"] == "yaml:sales-dashboard"

    def test_admin_screen_with_required_role(self, loaded_screens: ScreenConfigLoader):
        screen = loaded_screens.get_screen("admin-users")
        assert screen is not None
        assert screen.type == "admin"
        assert screen.nav.required_role == "admin"

    def test_get_unknown_slug_returns_none(self, loaded_screens: ScreenConfigLoader):
        assert loaded_screens.get_screen("nonexistent") is None

    def test_empty_dir_loads_no_screens(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        loader = ScreenConfigLoader(empty_dir)
        loader.load_all()
        assert loader.list_screens() == []

    def test_missing_dir_loads_no_screens(self, tmp_path: Path):
        loader = ScreenConfigLoader(tmp_path / "does-not-exist")
        loader.load_all()
        assert loader.list_screens() == []

    def test_non_screen_yaml_ignored(self, tmp_path: Path):
        screens_dir = tmp_path / "screens"
        screens_dir.mkdir()
        # YAML file without 'screen' key
        (screens_dir / "readme.yaml").write_text(yaml.dump({"readme": "test"}))
        loader = ScreenConfigLoader(screens_dir)
        loader.load_all()
        assert loader.list_screens() == []

    def test_defaults_for_missing_fields(self, tmp_path: Path):
        screens_dir = tmp_path / "screens"
        screens_dir.mkdir()
        # Minimal screen with only required fields
        minimal = {
            "screen": {
                "name": "Minimal",
                "slug": "minimal",
                "nav": {"section": "Test"},
            }
        }
        (screens_dir / "minimal.yaml").write_text(yaml.dump(minimal))
        loader = ScreenConfigLoader(screens_dir)
        loader.load_all()
        screen = loader.get_screen("minimal")
        assert screen is not None
        assert screen.type == "entity"  # default
        assert screen.entity_name is None
        assert screen.nav.order == 0
        assert screen.nav.icon is None
        assert screen.nav.label is None
        assert screen.views == {}


# ── Permission filtering ──


class TestPermissionFiltering:
    def _make_user(self, role: str = "user") -> UserContext:
        return UserContext(
            user_id="u1",
            tenant_id="t1",
            roles=[role],
        )

    def test_no_required_role_visible_to_all(self):
        screen = ScreenConfig(
            slug="x", name="X", type="entity",
            nav=ScreenNav(section="A"),
        )
        result = _filter_by_permissions([screen], self._make_user("readonly"))
        assert len(result) == 1

    def test_required_role_hides_from_lower_role(self):
        screen = ScreenConfig(
            slug="x", name="X", type="admin",
            nav=ScreenNav(section="A", required_role="admin"),
        )
        result = _filter_by_permissions([screen], self._make_user("user"))
        assert len(result) == 0

    def test_required_role_shows_to_matching_role(self):
        screen = ScreenConfig(
            slug="x", name="X", type="admin",
            nav=ScreenNav(section="A", required_role="admin"),
        )
        result = _filter_by_permissions([screen], self._make_user("admin"))
        assert len(result) == 1

    def test_required_role_shows_to_higher_role(self):
        screen = ScreenConfig(
            slug="x", name="X", type="entity",
            nav=ScreenNav(section="A", required_role="user"),
        )
        result = _filter_by_permissions([screen], self._make_user("admin"))
        assert len(result) == 1

    def test_no_user_context_hides_restricted_screens(self):
        screen = ScreenConfig(
            slug="x", name="X", type="admin",
            nav=ScreenNav(section="A", required_role="admin"),
        )
        result = _filter_by_permissions([screen], None)
        assert len(result) == 0

    def test_no_user_context_shows_unrestricted_screens(self):
        screen = ScreenConfig(
            slug="x", name="X", type="entity",
            nav=ScreenNav(section="A"),
        )
        result = _filter_by_permissions([screen], None)
        assert len(result) == 1


# ── Navigation building ──


class TestNavigationBuilding:
    def test_groups_screens_by_section(self):
        screens = [
            ScreenConfig(slug="a", name="A", type="entity", nav=ScreenNav(section="S1", order=1)),
            ScreenConfig(slug="b", name="B", type="entity", nav=ScreenNav(section="S2", order=1)),
            ScreenConfig(slug="c", name="C", type="entity", nav=ScreenNav(section="S1", order=2)),
        ]
        sections = _build_navigation(screens)
        assert len(sections) == 2
        assert sections[0]["name"] == "S1"
        assert len(sections[0]["screens"]) == 2
        assert sections[1]["name"] == "S2"

    def test_sorts_sections_by_min_order(self):
        screens = [
            ScreenConfig(slug="a", name="A", type="entity", nav=ScreenNav(section="Later", order=10)),
            ScreenConfig(slug="b", name="B", type="entity", nav=ScreenNav(section="First", order=1)),
        ]
        sections = _build_navigation(screens)
        assert sections[0]["name"] == "First"
        assert sections[1]["name"] == "Later"

    def test_sorts_screens_within_section_by_order(self):
        screens = [
            ScreenConfig(slug="b", name="B", type="entity", nav=ScreenNav(section="S", order=2)),
            ScreenConfig(slug="a", name="A", type="entity", nav=ScreenNav(section="S", order=1)),
        ]
        sections = _build_navigation(screens)
        assert sections[0]["screens"][0]["slug"] == "a"
        assert sections[0]["screens"][1]["slug"] == "b"

    def test_screen_item_has_expected_fields(self):
        screens = [
            ScreenConfig(
                slug="contacts", name="Contacts", type="entity",
                nav=ScreenNav(section="CRM", order=1, icon="users", label="My Contacts"),
            ),
        ]
        sections = _build_navigation(screens)
        item = sections[0]["screens"][0]
        assert item["slug"] == "contacts"
        assert item["label"] == "My Contacts"
        assert item["icon"] == "users"
        assert item["type"] == "entity"

    def test_empty_screens_returns_empty(self):
        assert _build_navigation([]) == []


# ── Auto-generation ──


class TestAutoScreenGeneration:
    def test_auto_screen_for_entity(self):
        """Test the auto-generation helper function directly."""

        # Create a mock metadata loader
        class MockMetadataLoader:
            def list_entities(self):
                return ["Contact", "Company"]

            def get_entity(self, name):
                class E:
                    plural_name = f"{name}s"
                return E()

        ml = MockMetadataLoader()
        auto = _auto_screen_for_entity("Contact", ml)
        assert auto.slug == "contacts"
        assert auto.name == "Contacts"
        assert auto.type == "entity"
        assert auto.entity_name == "Contact"
        assert auto.nav.section == "Entities"
        assert auto.nav.order == 99
        assert auto.views == {}
        assert auto.source == "auto"

    def test_build_all_screens_includes_uncovered_entities(self, tmp_path: Path):
        """Entities without screen YAML get auto-generated screens."""

        class MockMetadataLoader:
            def list_entities(self):
                return ["Contact", "Company", "Category"]

            def get_entity(self, name):
                class E:
                    plural_name = f"{name}s"  # simplified
                return E()

        # Only Contact has a screen YAML
        screens_dir = tmp_path / "screens"
        screens_dir.mkdir()
        contact_yaml = {
            "screen": {
                "name": "Contacts",
                "slug": "contacts",
                "type": "entity",
                "entityName": "Contact",
                "nav": {"section": "CRM", "order": 1},
            }
        }
        (screens_dir / "contacts.yaml").write_text(yaml.dump(contact_yaml))

        loader = ScreenConfigLoader(screens_dir)
        loader.load_all()
        ml = MockMetadataLoader()

        all_screens = _build_all_screens(loader, ml)
        slugs = {s.slug for s in all_screens}
        assert "contacts" in slugs  # from YAML
        assert "companys" in slugs  # auto-generated (simplified plural)
        assert "categorys" in slugs  # auto-generated

    def test_system_entities_not_auto_generated(self, tmp_path: Path):
        """User, Tenant, TenantMembership should not get auto-generated screens."""

        class MockMetadataLoader:
            def list_entities(self):
                return ["User", "Tenant", "TenantMembership", "Contact"]

            def get_entity(self, name):
                class E:
                    plural_name = f"{name}s"
                return E()

        screens_dir = tmp_path / "screens"
        screens_dir.mkdir()
        loader = ScreenConfigLoader(screens_dir)
        loader.load_all()
        ml = MockMetadataLoader()

        all_screens = _build_all_screens(loader, ml)
        slugs = {s.slug for s in all_screens}
        assert "users" not in slugs
        assert "tenants" not in slugs
        assert "tenantmemberships" not in slugs
        assert "contacts" in slugs  # auto-generated for Contact
