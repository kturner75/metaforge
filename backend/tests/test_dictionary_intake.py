import pytest

from metaforge.intake import DictionaryError, map_schema, parse_dictionary, read_dictionary_rows


def test_csv_types_comments_and_sources():
    data = b"""table,column,type,description
address,district,VARCHAR(20),Part of the address, such as a state
film,rating,ENUM('G','PG','R'),The rating
film,rental_rate,DECIMAL(4,2),The cost per period
film,description,TEXT,"A longer description
that spans two lines"
film,title,VARCHAR(30),Title
film,created,DATETIME,Automatically set by a trigger
"""
    result = map_schema(parse_dictionary("film.csv", data))
    address, film = result.documents
    assert address["fields"][1]["description"] == "Part of the address, such as a state"
    fields = {f["name"]: f for f in film["fields"]}
    assert [option["value"] for option in fields["rating"]["options"]] == ["G", "PG", "R"]
    assert fields["rentalRate"]["type"] == "currency"
    assert fields["created"]["readOnly"] is True
    assert next(f.source.line for f in result.fields if f.name == "title") == 7


def test_tsv_keys_choices_required_and_references():
    data = (
        "\ufeffEntity\tAttribute\tDatatype\tPK\tReferences\tNullable\tAllowed Values\n"
        "orders\torder_no\tINT\tY\t\tN\t\n"
        "orders\torder_group\tINT\tPK\t\tN\t\n"
        "orders\tstatus\tVARCHAR(10)\t\t\tN\topen; closed\n"
        "lines\torder_ref\tINT\t\torders\tY\t\n"
        "lines\tquantity\tINT\t\t\tN\t\n"
    ).encode()
    schema = parse_dictionary("orders.TSV", data)
    assert schema.tables[0].primary_key == ["order_no", "order_group"]
    orders, lines = map_schema(schema).documents
    assert orders["fields"][0]["primaryKey"] is True
    assert orders["fields"][0]["name"] == "id"
    assert orders["fields"][-1]["validation"] == {"required": True}
    assert [v["value"] for v in orders["fields"][-1]["options"]] == ["open", "closed"]
    assert lines["fields"][1]["relation"] == {"entity": "Order"}
    assert lines["fields"][2]["validation"] == {"required": True}


def test_dictionary_infers_foreign_keys_and_maps_missing_types_to_text():
    data = b"""table,column,type,description
vendor,vendor_id,INT,A surrogate primary key
vendor,name,VARCHAR(20),Organization name
location,vendor_id,INT,A foreign key
location,directions,,Directions to the location
"""
    _, location = map_schema(parse_dictionary("locations.csv", data)).documents
    assert location["fields"][1]["relation"] == {"entity": "Vendor"}
    assert location["fields"][2]["type"] == "string"


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("dict.csv", b"", "is empty"),
        ("dict.csv", b"foo,bar\n1,2", "needs a table column"),
        ("dict.csv", b"table,column\n,", "contains no table and column rows"),
        ("dict.tsv", b"\xff", "UTF-8"),
        ("dict.xlsx", b"", "expected a CSV or TSV"),
    ],
)
def test_invalid_dictionary_reports_the_problem(filename, data, message):
    with pytest.raises(DictionaryError, match=message):
        parse_dictionary(filename, data)


def test_normalized_csv_ignores_rows_without_table_and_column():
    assert read_dictionary_rows("empty.csv", b"table,column\n,\na,b\n") == [
        (3, {"table": "a", "column": "b"})
    ]
