from pathlib import Path

import pytest
import yaml

from metaforge.intake import TypeChoice, map_ddl, map_schema, parse_ddl
from metaforge.metadata.validator import validate_yaml_file

SUPPLIER = Path(__file__).parent / "fixtures" / "supplier_onboarding"


def test_supplier_onboarding_matches_mfgen(tmp_path):
    result = map_ddl((SUPPLIER / "schema.sql").read_text(encoding="utf-8"))
    sources = {(field.entity, field.name): field for field in result.fields}
    expected_by_name = {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in (SUPPLIER / "expected").glob("*.yaml")
    }

    assert set(expected_by_name) == {
        "Equipment",
        "Location",
        "Manufacturer",
        "Vendor",
        "VendorContact",
    }
    for name, expected in expected_by_name.items():
        for field in expected["fields"]:
            # mfgen attaches this host extension from the mapper's provenance.
            extensions = field.pop("extensions", {})
            places = extensions.get("mfgen", {}).get("places")
            assert sources[name, field["name"]].decimal_places == places

    assert {doc["entity"]: doc for doc in result.documents} == expected_by_name
    assert result.notes == ["vendors.tax_id: UNIQUE is not carried (no uniqueness rule yet)"]

    for doc in result.documents:
        path = tmp_path / f"{doc['entity']}.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        assert validate_yaml_file(path, "entity.schema.json") == []


def test_parser_keeps_line_numbers_and_understands_three_dialects():
    schema = parse_ddl("""-- header
CREATE TABLE public."Vendors" (
  id SERIAL PRIMARY KEY,
  terms VARCHAR(10) NOT NULL DEFAULT 'net_30' CHECK (terms IN ('net_15','net_30'))
);
CREATE TABLE `sites` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `vendor_id` INT NOT NULL COMMENT 'Owner',
  PRIMARY KEY (`id`),
  CONSTRAINT fk FOREIGN KEY (`vendor_id`) REFERENCES Vendors (id) ON DELETE CASCADE
) COMMENT='Places';
CREATE TABLE [dbo].[machines] (
  [id] INT IDENTITY(1,1) PRIMARY KEY, [notes] NVARCHAR(MAX), tags TEXT[]
);
ALTER TABLE machines ADD CONSTRAINT m FOREIGN KEY (id) REFERENCES sites (id);
""")
    vendors, sites, machines = schema.tables
    assert (vendors.name, vendors.line, vendors.columns[1].line) == ("Vendors", 2, 4)
    terms = vendors.columns[1]
    assert (
        terms.not_null and terms.has_default and terms.checks == ["terms IN ('net_15', 'net_30')"]
    )
    assert sites.comment == "Places" and sites.primary_key == ["id"] and sites.columns[0].identity
    assert (
        sites.columns[1].references.on_delete == "CASCADE" and sites.columns[1].comment == "Owner"
    )
    assert machines.columns[0].identity and machines.columns[1].type_args == ["MAX"]
    assert machines.columns[2].is_array and machines.columns[2].raw_type == "TEXT[]"
    assert machines.columns[0].references.table == "sites"


@pytest.mark.parametrize(
    ("sql_type", "candidates"),
    [
        ("BOOLEAN", ("checkbox",)),
        ("TINYINT(1)", ("checkbox",)),
        ("DATE", ("date",)),
        ("TIMESTAMP WITH TIME ZONE", ("datetime", "date")),
        ("BIGINT", ("number",)),
        ("MONEY", ("currency",)),
        ("NUMERIC(12,2)", ("currency", "number", "percent")),
        ("NUMERIC(4,3)", ("number", "percent", "currency")),
        ("VARCHAR(255)", ("string", "email", "phone", "url", "address")),
        ("VARCHAR(400)", ("description", "string", "address")),
        ("TEXT", ("description", "string", "address")),
        ("JSONB", ("description",)),
        ("BYTEA", ("attachment",)),
        ("UUID", ("string",)),
    ],
)
def test_ranked_sql_types(sql_type, candidates):
    result = map_ddl(f"CREATE TABLE samples (id INT PRIMARY KEY, value {sql_type});")
    assert result.fields[1].source.candidates == candidates
    assert result.documents[0]["fields"][1]["type"] == candidates[0]


def test_choose_receives_only_ambiguous_columns_and_updates_field():
    schema = parse_ddl("""CREATE TABLE vendors (
    vendor_id INT PRIMARY KEY,
    direct_line VARCHAR(30) NOT NULL,
    billing_email VARCHAR(255),
    terms VARCHAR(10) CHECK (terms IN ('net_15','net_30'))
);
COMMENT ON TABLE vendors IS 'Supplier';
COMMENT ON COLUMN vendors.direct_line IS 'Call this number';
""")
    asked: list[TypeChoice] = []

    def choose(choice: TypeChoice) -> str:
        asked.append(choice)
        return "phone"

    result = map_schema(schema, choose=choose)

    assert len(asked) == 1
    choice = asked[0]
    assert (choice.table, choice.column, choice.line) == ("vendors", "direct_line", 3)
    assert (choice.table_comment, choice.column_comment) == ("Supplier", "Call this number")
    assert choice.sql_type == choice.reason == "VARCHAR(30)"
    assert [f["type"] for f in result.documents[0]["fields"]] == [
        "id",
        "phone",
        "email",
        "picklist",
    ]
    assert result.documents[0]["fields"][1]["validation"] == {"required": True, "maxLength": 30}
    assert result.fields[1].source == choice

    with pytest.raises(ValueError, match=r"vendors\.direct_line: 'date' is not one of"):
        map_schema(schema, choose=lambda _: "date")


def test_keys_limits_and_notes_are_preserved_in_the_draft():
    result = map_ddl("""CREATE TABLE entries (
    id INT,
    synthetic_id INT,
    rowid INT,
    rowid_value INT,
    owner_id INT REFERENCES owners(id) ON DELETE SET NULL,
    code CHAR(8) UNIQUE,
    qty INT CHECK (qty > 0 AND qty < 5),
    amount NUMERIC(18,4),
    PRIMARY KEY (id, code)
);""")
    fields = {f["name"]: f for f in result.documents[0]["fields"]}
    assert fields["syntheticId2"] == {"name": "syntheticId2", "type": "id", "primaryKey": True}
    assert fields["rowidValue2"]["type"] == "number"
    assert fields["ownerId"]["relation"] == {"entity": "Owner", "onDelete": "setNull"}
    assert fields["qty"]["validation"] == {"min": 1, "max": 4}
    assert "validation" not in fields["amount"]

    source = {field.name: field for field in result.fields}
    assert source["amount"].decimal_places == 4
    assert "no max recorded" in source["amount"].notes[0]
    assert source["syntheticId2"].source.column is None
    assert "composite primary key" in source["syntheticId2"].source.reason
    assert "SQLite aliases" in source["rowidValue2"].notes[0]
    assert "which is not in this DDL" in source["ownerId"].notes[0]


@pytest.mark.parametrize(
    ("ddl", "error"),
    [
        ("CREATE INDEX idx ON vendors (id);", "no CREATE TABLE"),
        ("CREATE TABLE Vendor (id INT); CREATE TABLE vendors (id INT);", "both map to entity"),
        ('CREATE TABLE things (item_name INT, "item name" INT);', "multiple columns map to field"),
        ('CREATE TABLE "___" (id INT);', "no usable characters"),
    ],
)
def test_unmappable_input_has_an_actionable_error(ddl, error):
    with pytest.raises(ValueError, match=error):
        map_ddl(ddl)
