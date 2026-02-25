"""Tests for metadata hot-reload: MetadataLoader.reload(), ViewConfigLoader.reload(),
ScreenConfigLoader.reload(), and POST /api/admin/metadata/reload endpoint."""

import os
import textwrap
from pathlib import Path

import pytest
import yaml

from metaforge.metadata.loader import MetadataLoader
from metaforge.screens.loader import ScreenConfigLoader
from metaforge.views.loader import ViewConfigLoader


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_entity(directory: Path, filename: str, name: str, abbrev: str) -> Path:
    """Write a minimal entity YAML file and return its path."""
    path = directory / filename
    path.write_text(
        textwrap.dedent(f"""\
            entity: {name}
            abbreviation: {abbrev}
            displayName: {name}
            pluralName: {name}s
            fields:
              - name: id
                type: id
                displayName: ID
                primaryKey: true
              - name: name
                type: name
                displayName: Name
        """)
    )
    return path


def _write_view(directory: Path, filename: str, view_name: str) -> Path:
    """Write a minimal view YAML file and return its path."""
    path = directory / filename
    path.write_text(
        textwrap.dedent(f"""\
            view:
              name: {view_name}
              entityName: Widget
              pattern: query
              style: grid
        """)
    )
    return path


def _write_screen(directory: Path, filename: str, slug: str, name: str) -> Path:
    """Write a minimal screen YAML file and return its path."""
    path = directory / filename
    path.write_text(
        textwrap.dedent(f"""\
            screen:
              slug: {slug}
              name: {name}
              type: entity
        """)
    )
    return path


# ── MetadataLoader.reload() ───────────────────────────────────────────────────


class TestMetadataLoaderReload:
    """MetadataLoader.reload() re-scans YAML files correctly."""

    @pytest.fixture
    def entities_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "entities"
        d.mkdir(parents=True)
        return d

    @pytest.fixture
    def loader(self, tmp_path: Path, entities_dir: Path) -> MetadataLoader:
        _write_entity(entities_dir, "widget.yaml", "Widget", "WGT")
        loader = MetadataLoader(tmp_path)
        loader.load_all()
        return loader

    def test_reload_picks_up_new_entity(self, loader, entities_dir):
        """A YAML file added after initial load appears after reload."""
        assert loader.get_entity("Gadget") is None

        _write_entity(entities_dir, "gadget.yaml", "Gadget", "GDT")
        loader.reload()

        assert loader.get_entity("Gadget") is not None

    def test_reload_removes_deleted_entity(self, loader, entities_dir):
        """An entity whose YAML was deleted disappears after reload."""
        assert loader.get_entity("Widget") is not None

        (entities_dir / "widget.yaml").unlink()
        loader.reload()

        assert loader.get_entity("Widget") is None

    def test_reload_reflects_updated_entity(self, loader, entities_dir):
        """Changes to a YAML file are visible after reload."""
        assert loader.get_entity("Widget").display_name == "Widget"

        # Overwrite with a new displayName
        _write_entity(entities_dir, "widget.yaml", "Widget", "WGT")
        # Patch the display name manually by rewriting the YAML
        (entities_dir / "widget.yaml").write_text(
            textwrap.dedent("""\
                entity: Widget
                abbreviation: WGT
                displayName: Super Widget
                pluralName: Super Widgets
                fields:
                  - name: id
                    type: id
                    displayName: ID
                    primaryKey: true
                  - name: name
                    type: name
                    displayName: Name
            """)
        )
        loader.reload()

        assert loader.get_entity("Widget").display_name == "Super Widget"

    def test_reload_clears_previous_state_completely(self, loader, entities_dir):
        """reload() does not accumulate stale entries alongside new ones."""
        initial_count = len(loader.list_entities())

        # Remove the original entity and add a different one
        (entities_dir / "widget.yaml").unlink()
        _write_entity(entities_dir, "gadget.yaml", "Gadget", "GDT")
        loader.reload()

        assert len(loader.list_entities()) == initial_count
        assert loader.get_entity("Widget") is None
        assert loader.get_entity("Gadget") is not None

    def test_reload_is_idempotent_when_nothing_changes(self, loader):
        """Calling reload() twice without file changes yields the same result."""
        entities_before = set(loader.list_entities())
        loader.reload()
        entities_after = set(loader.list_entities())

        assert entities_before == entities_after

    def test_reload_also_rescans_drafts_dir(self, tmp_path):
        """Entities in metadata/drafts/ are picked up by reload()."""
        entities_dir = tmp_path / "entities"
        entities_dir.mkdir()
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()

        _write_entity(entities_dir, "widget.yaml", "Widget", "WGT")

        loader = MetadataLoader(tmp_path)
        loader.load_all()
        assert loader.get_entity("Draft") is None

        _write_entity(drafts_dir, "draft.yaml", "Draft", "DFT")
        loader.reload()

        draft_entity = loader.get_entity("Draft")
        assert draft_entity is not None
        assert draft_entity.is_draft is True


# ── ViewConfigLoader.reload() ─────────────────────────────────────────────────


class TestViewConfigLoaderReload:
    """ViewConfigLoader.reload() re-scans YAML view files correctly."""

    @pytest.fixture
    def views_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "views"
        d.mkdir()
        return d

    @pytest.fixture
    def loader(self, views_dir: Path) -> ViewConfigLoader:
        _write_view(views_dir, "widget-grid.yaml", "Widget Grid")
        loader = ViewConfigLoader(views_dir)
        loader.load_all()
        return loader

    def test_reload_picks_up_new_view(self, loader, views_dir):
        """A YAML file added after initial load appears after reload."""
        assert loader.get_config("yaml:widget-list") is None

        _write_view(views_dir, "widget-list.yaml", "Widget List")
        loader.reload()

        assert loader.get_config("yaml:widget-list") is not None

    def test_reload_removes_deleted_view(self, loader, views_dir):
        """A config whose YAML was deleted disappears after reload."""
        assert loader.get_config("yaml:widget-grid") is not None

        (views_dir / "widget-grid.yaml").unlink()
        loader.reload()

        assert loader.get_config("yaml:widget-grid") is None

    def test_reload_reflects_updated_view(self, loader, views_dir):
        """Changes to a YAML file are visible after reload."""
        assert loader.get_config("yaml:widget-grid").name == "Widget Grid"

        # Overwrite with a new name
        _write_view(views_dir, "widget-grid.yaml", "Updated Grid")
        loader.reload()

        assert loader.get_config("yaml:widget-grid").name == "Updated Grid"

    def test_reload_is_idempotent_when_nothing_changes(self, loader):
        """Calling reload() twice without file changes yields the same result."""
        count_before = len(loader.list_configs())
        loader.reload()
        assert len(loader.list_configs()) == count_before


# ── ScreenConfigLoader.reload() ───────────────────────────────────────────────


class TestScreenConfigLoaderReload:
    """ScreenConfigLoader.reload() re-scans YAML screen files correctly."""

    @pytest.fixture
    def screens_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "screens"
        d.mkdir()
        return d

    @pytest.fixture
    def loader(self, screens_dir: Path) -> ScreenConfigLoader:
        _write_screen(screens_dir, "widgets.yaml", "widgets", "Widgets")
        loader = ScreenConfigLoader(screens_dir)
        loader.load_all()
        return loader

    def test_reload_picks_up_new_screen(self, loader, screens_dir):
        """A YAML file added after initial load appears after reload."""
        assert loader.get_screen("gadgets") is None

        _write_screen(screens_dir, "gadgets.yaml", "gadgets", "Gadgets")
        loader.reload()

        assert loader.get_screen("gadgets") is not None

    def test_reload_removes_deleted_screen(self, loader, screens_dir):
        """A screen whose YAML was deleted disappears after reload."""
        assert loader.get_screen("widgets") is not None

        (screens_dir / "widgets.yaml").unlink()
        loader.reload()

        assert loader.get_screen("widgets") is None

    def test_reload_reflects_updated_screen(self, loader, screens_dir):
        """Changes to a YAML file are visible after reload."""
        assert loader.get_screen("widgets").name == "Widgets"

        _write_screen(screens_dir, "widgets.yaml", "widgets", "All Widgets")
        loader.reload()

        assert loader.get_screen("widgets").name == "All Widgets"

    def test_reload_is_idempotent_when_nothing_changes(self, loader):
        """Calling reload() twice without file changes yields the same result."""
        count_before = len(loader.list_screens())
        loader.reload()
        assert len(loader.list_screens()) == count_before


# ── POST /api/admin/metadata/reload ──────────────────────────────────────────


@pytest.fixture
def client(tmp_path):
    """FastAPI TestClient with isolated SQLite DB and auth disabled."""
    saved_db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["METAFORGE_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["METAFORGE_DISABLE_AUTH"] = "1"

    original_cwd = Path.cwd()
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)

    from metaforge.api.app import app
    from fastapi.testclient import TestClient

    try:
        with TestClient(app) as c:
            yield c
    finally:
        os.chdir(original_cwd)
        os.environ.pop("METAFORGE_DB_PATH", None)
        os.environ.pop("METAFORGE_DISABLE_AUTH", None)
        if saved_db_url is not None:
            os.environ["DATABASE_URL"] = saved_db_url


class TestReloadEndpoint:
    """POST /api/admin/metadata/reload returns a reload summary."""

    def test_reload_returns_200(self, client):
        response = client.post("/api/admin/metadata/reload")
        assert response.status_code == 200

    def test_reload_response_has_reloaded_flag(self, client):
        data = client.post("/api/admin/metadata/reload").json()
        assert data["reloaded"] is True

    def test_reload_response_contains_counts(self, client):
        data = client.post("/api/admin/metadata/reload").json()
        assert isinstance(data["entities"], int)
        assert isinstance(data["views"], int)
        assert isinstance(data["screens"], int)

    def test_reload_entity_count_matches_metadata(self, client):
        """Entity count in the reload response matches /api/metadata."""
        reload_data = client.post("/api/admin/metadata/reload").json()
        metadata_data = client.get("/api/metadata").json()

        assert reload_data["entities"] == len(metadata_data["entities"])

    def test_reload_twice_is_stable(self, client):
        """Calling reload twice returns the same counts."""
        first = client.post("/api/admin/metadata/reload").json()
        second = client.post("/api/admin/metadata/reload").json()

        assert first["entities"] == second["entities"]
        assert first["views"] == second["views"]
        assert first["screens"] == second["screens"]
