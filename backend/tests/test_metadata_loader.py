"""Tests for MetadataLoader — entity and draft loading."""

import pytest
from pathlib import Path

from metaforge.metadata.loader import MetadataLoader


MINIMAL_ENTITY_YAML = """\
entity: Widget
abbreviation: WGT
fields:
  - name: id
    type: id
    primaryKey: true
  - name: name
    type: name
"""

SECOND_ENTITY_YAML = """\
entity: Gadget
abbreviation: GDG
fields:
  - name: id
    type: id
    primaryKey: true
  - name: title
    type: name
"""


@pytest.fixture
def metadata_dir(tmp_path):
    """Metadata root with entities/ and drafts/ subdirectories."""
    (tmp_path / "entities").mkdir()
    (tmp_path / "drafts").mkdir()
    (tmp_path / "blocks").mkdir()
    return tmp_path


class TestEntityLoading:
    """Core entity loading from entities/ directory."""

    def test_loads_entity_from_entities_dir(self, metadata_dir):
        (metadata_dir / "entities" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        assert "Widget" in loader.list_entities()

    def test_entity_is_not_draft(self, metadata_dir):
        (metadata_dir / "entities" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        entity = loader.get_entity("Widget")
        assert entity is not None
        assert entity.is_draft is False

    def test_missing_entities_dir_is_noop(self, tmp_path):
        loader = MetadataLoader(tmp_path)
        loader.load_all()  # Should not raise
        assert loader.list_entities() == []

    def test_non_entity_yaml_ignored(self, metadata_dir):
        (metadata_dir / "entities" / "not-an-entity.yaml").write_text("something: true\n")

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        assert loader.list_entities() == []


class TestDraftLoading:
    """Draft entity loading from drafts/ directory."""

    def test_loads_entity_from_drafts_dir(self, metadata_dir):
        (metadata_dir / "drafts" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        assert "Widget" in loader.list_entities()

    def test_draft_entity_has_is_draft_true(self, metadata_dir):
        (metadata_dir / "drafts" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        entity = loader.get_entity("Widget")
        assert entity is not None
        assert entity.is_draft is True

    def test_missing_drafts_dir_is_noop(self, metadata_dir):
        (metadata_dir / "drafts").rmdir()
        (metadata_dir / "entities" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()  # Should not raise

        # Regular entity still loads fine
        assert "Widget" in loader.list_entities()
        assert loader.get_entity("Widget").is_draft is False

    def test_empty_drafts_dir_loads_zero_drafts(self, metadata_dir):
        # drafts/ exists but is empty
        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        assert loader.list_entities() == []

    def test_non_entity_yaml_in_drafts_ignored(self, metadata_dir):
        (metadata_dir / "drafts" / "not-an-entity.yaml").write_text("something: true\n")

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        assert loader.list_entities() == []


class TestMixedLoading:
    """Draft and non-draft entities coexist in the registry."""

    def test_draft_and_regular_entities_coexist(self, metadata_dir):
        (metadata_dir / "entities" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)
        (metadata_dir / "drafts" / "gadget.yaml").write_text(SECOND_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        assert set(loader.list_entities()) == {"Widget", "Gadget"}

    def test_draft_flag_is_per_entity(self, metadata_dir):
        (metadata_dir / "entities" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)
        (metadata_dir / "drafts" / "gadget.yaml").write_text(SECOND_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        assert loader.get_entity("Widget").is_draft is False
        assert loader.get_entity("Gadget").is_draft is True

    def test_draft_entity_fields_load_correctly(self, metadata_dir):
        (metadata_dir / "drafts" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)

        loader = MetadataLoader(metadata_dir)
        loader.load_all()

        entity = loader.get_entity("Widget")
        assert entity is not None
        field_names = [f.name for f in entity.fields]
        assert "id" in field_names
        assert "name" in field_names

    def test_draft_entity_abbreviation_included_in_uniqueness_check(self, metadata_dir):
        """Abbreviation uniqueness is enforced across both dirs."""
        # Both have abbreviation WGT
        (metadata_dir / "entities" / "widget.yaml").write_text(MINIMAL_ENTITY_YAML)
        conflicting = SECOND_ENTITY_YAML.replace("GDG", "WGT")
        (metadata_dir / "drafts" / "gadget.yaml").write_text(conflicting)

        loader = MetadataLoader(metadata_dir)
        with pytest.raises(ValueError, match="Duplicate abbreviation"):
            loader.load_all()
