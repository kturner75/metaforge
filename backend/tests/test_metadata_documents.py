import pytest
import yaml

from metaforge.metadata.diff import MetadataChange, diff_metadata
from metaforge.metadata.loader import MetadataLoader


def test_documents_match_file_resolution_and_reload_from_own_snapshot(tmp_path):
    block = {
        "block": "State",
        "fields": [{"name": "Status", "type": "picklist", "options": [{"value": "open"}]}],
    }
    customer = {
        "entity": "Customer",
        "includes": [{"block": "State", "prefix": "billing"}],
        "fields": [{"name": "name", "type": "name"}],
    }
    draft = {"entity": "Proposed", "fields": [{"name": "title", "type": "string"}]}
    for folder, doc in [("entities", customer), ("blocks", block), ("drafts", draft)]:
        directory = tmp_path / folder
        directory.mkdir()
        (directory / "doc.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    file_loader = MetadataLoader(tmp_path)
    file_loader.load_all()
    document_loader = MetadataLoader.from_documents(iter([customer]), [block], drafts=[draft])
    assert document_loader.entities == file_loader.entities
    assert document_loader.blocks == file_loader.blocks

    block["fields"][0]["options"][0]["value"] = "closed"
    entity = document_loader.entities["Customer"]
    assert entity.fields[0].options == [{"value": "open"}]
    entity.fields[0].options.clear()
    document_loader.reload()
    assert document_loader.entities == file_loader.entities


def test_document_loader_validates_abbreviations():
    with pytest.raises(ValueError, match="Duplicate abbreviation 'CUS'"):
        MetadataLoader.from_documents([{"entity": "Customer"}, {"entity": "CustomerGroup"}])


def test_metadata_diff_covers_entity_field_and_property_changes():
    common_block = {"block": "Audit", "fields": [{"name": "updatedAt", "type": "datetime"}]}
    before = MetadataLoader.from_documents(
        [
            {"entity": "Tag"},
            {
                "entity": "Vendor",
                "includes": [{"block": "Audit"}],
                "fields": [
                    {"name": "code", "type": "string"},
                    {"name": "rating", "type": "string"},
                    {"name": "region", "type": "relation", "relation": {"entity": "Office"}},
                    {"name": "status", "type": "picklist", "options": [{"value": "open"}]},
                ],
            },
        ],
        [common_block],
    )
    after = MetadataLoader.from_documents(
        [
            {"entity": "Site"},
            {
                "entity": "Vendor",
                "includes": [{"block": "Audit"}],
                "fields": [
                    {"name": "name", "type": "name"},
                    {"name": "rating", "type": "number", "validation": {"required": True}},
                    {"name": "region", "type": "relation", "relation": {"entity": "Region"}},
                    {
                        "name": "status",
                        "type": "picklist",
                        "options": [{"value": "open"}, {"value": "closed"}],
                    },
                ],
            },
        ],
        [common_block],
    )
    assert diff_metadata(before, after) == [
        MetadataChange("added", "Site"),
        MetadataChange("removed", "Tag"),
        MetadataChange("removed", "Vendor", "code"),
        MetadataChange("added", "Vendor", "name"),
        MetadataChange("changed", "Vendor", "rating", "type", "string", "number"),
        MetadataChange("changed", "Vendor", "rating", "required", False, True),
        MetadataChange(
            "changed",
            "Vendor",
            "region",
            "relation",
            ("Office", "name", "restrict"),
            ("Region", "name", "restrict"),
        ),
        MetadataChange("changed", "Vendor", "status", "options", ("open",), ("open", "closed")),
    ]
    assert diff_metadata(before, before) == []
