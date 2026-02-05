"""Tests for ViewConfigLoader."""

import pytest
from pathlib import Path

from metaforge.views.loader import ViewConfigLoader
from metaforge.views.types import (
    ConfigScope,
    ConfigSource,
    DataPattern,
    OwnerType,
)


@pytest.fixture
def views_dir(tmp_path):
    """Create a temporary views directory with sample YAML."""
    views_path = tmp_path / "views"
    views_path.mkdir()

    # Write a sample view config
    (views_path / "contact-grid.yaml").write_text("""
view:
  name: Contact Grid
  entityName: Contact
  pattern: query
  style: grid
  data:
    sort:
      - field: fullName
        direction: asc
    pageSize: 25
  styleConfig:
    columns:
      - field: fullName
        pinned: left
      - field: email
      - field: status
    selectable: false
    inlineEdit: false
""")

    # Write a second view config
    (views_path / "company-summary.yaml").write_text("""
view:
  name: Company Summary
  description: Summary view of companies
  entityName: Company
  pattern: aggregate
  style: summaryGrid
  data:
    measures:
      - field: revenue
        aggregate: sum
    groupBy:
      - industry
  styleConfig:
    showTotals: true
""")

    return views_path


@pytest.fixture
def empty_views_dir(tmp_path):
    """Create an empty views directory."""
    views_path = tmp_path / "views"
    views_path.mkdir()
    return views_path


class TestViewConfigLoaderLoad:
    """Tests for loading view configs from YAML."""

    def test_load_all_from_directory(self, views_dir):
        """Should load all YAML files from the views directory."""
        loader = ViewConfigLoader(views_dir)
        loader.load_all()

        configs = loader.list_configs()
        assert len(configs) == 2

    def test_yaml_id_convention(self, views_dir):
        """Config IDs should follow yaml:{file_stem} convention."""
        loader = ViewConfigLoader(views_dir)
        loader.load_all()

        config = loader.get_config("yaml:contact-grid")
        assert config is not None
        assert config.id == "yaml:contact-grid"

    def test_parses_query_view(self, views_dir):
        """Should correctly parse a query pattern view."""
        loader = ViewConfigLoader(views_dir)
        loader.load_all()

        config = loader.get_config("yaml:contact-grid")
        assert config is not None
        assert config.name == "Contact Grid"
        assert config.entity_name == "Contact"
        assert config.pattern == DataPattern.QUERY
        assert config.style == "grid"
        assert config.source == ConfigSource.YAML
        assert config.scope == ConfigScope.GLOBAL
        assert config.owner_type == OwnerType.GLOBAL

    def test_parses_data_config(self, views_dir):
        """Should parse data section into data_config."""
        loader = ViewConfigLoader(views_dir)
        loader.load_all()

        config = loader.get_config("yaml:contact-grid")
        assert config is not None
        assert config.data_config["pageSize"] == 25
        assert config.data_config["sort"][0]["field"] == "fullName"

    def test_parses_style_config(self, views_dir):
        """Should parse styleConfig section."""
        loader = ViewConfigLoader(views_dir)
        loader.load_all()

        config = loader.get_config("yaml:contact-grid")
        assert config is not None
        assert config.style_config["selectable"] is False
        assert len(config.style_config["columns"]) == 3

    def test_parses_aggregate_view(self, views_dir):
        """Should correctly parse an aggregate pattern view."""
        loader = ViewConfigLoader(views_dir)
        loader.load_all()

        config = loader.get_config("yaml:company-summary")
        assert config is not None
        assert config.name == "Company Summary"
        assert config.description == "Summary view of companies"
        assert config.pattern == DataPattern.AGGREGATE
        assert config.style == "summaryGrid"

    def test_get_nonexistent_returns_none(self, views_dir):
        """get_config should return None for unknown IDs."""
        loader = ViewConfigLoader(views_dir)
        loader.load_all()

        assert loader.get_config("yaml:nonexistent") is None


class TestViewConfigLoaderEdgeCases:
    """Tests for edge cases."""

    def test_missing_directory_is_noop(self, tmp_path):
        """load_all should not error if the views directory doesn't exist."""
        loader = ViewConfigLoader(tmp_path / "nonexistent")
        loader.load_all()  # Should not raise
        assert loader.list_configs() == []

    def test_empty_directory(self, empty_views_dir):
        """load_all should work with an empty directory."""
        loader = ViewConfigLoader(empty_views_dir)
        loader.load_all()
        assert loader.list_configs() == []

    def test_non_view_yaml_ignored(self, tmp_path):
        """YAML files without 'view' key should be ignored."""
        views_path = tmp_path / "views"
        views_path.mkdir()
        (views_path / "not-a-view.yaml").write_text("""
something:
  name: Not a view
""")

        loader = ViewConfigLoader(views_path)
        loader.load_all()
        assert loader.list_configs() == []

    def test_empty_yaml_file_ignored(self, tmp_path):
        """Empty YAML files should be ignored."""
        views_path = tmp_path / "views"
        views_path.mkdir()
        (views_path / "empty.yaml").write_text("")

        loader = ViewConfigLoader(views_path)
        loader.load_all()
        assert loader.list_configs() == []
