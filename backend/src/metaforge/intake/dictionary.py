"""Read CSV and TSV data dictionaries into the shared schema model."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from pathlib import PurePath

from .ddl import Column, Ref, Schema, Table, parse_ddl

DOCUMENTED = "DOCUMENTED"
HEADERS = {
    "table": ["table", "table_name", "tablename", "entity", "entity_name", "object", "object_name"],
    "column": ["column", "column_name", "columnname", "field", "field_name", "attribute", "name"],
    "type": ["data_type", "datatype", "type", "column_type", "sql_type", "format"],
    "description": [
        "description",
        "comment",
        "comments",
        "definition",
        "meaning",
        "notes",
        "business_definition",
    ],
    "table_description": ["table_description", "table_comment", "entity_description"],
    "required": ["required", "mandatory", "not_null", "notnull"],
    "nullable": ["nullable", "is_nullable", "null", "allow_null", "allows_null"],
    "key": ["key", "pk", "primary_key", "is_pk", "key_type", "constraint"],
    "references": [
        "references",
        "foreign_key",
        "fk",
        "fk_table",
        "ref_table",
        "references_table",
        "parent_table",
        "lookup",
    ],
    "choices": ["allowed_values", "valid_values", "values", "choices", "enum", "options", "domain"],
}
TRUE = {"y", "yes", "true", "1", "x", "required", "mandatory", "not null"}
_SYSTEM_COLUMNS = {
    "createdat",
    "createdon",
    "createdby",
    "createddate",
    "createdtime",
    "updatedat",
    "updatedon",
    "updatedby",
    "updateddate",
    "modifiedat",
    "modifiedon",
    "modifiedby",
    "modifieddate",
    "lastmodified",
    "lastmodifiedat",
    "lastmodifiedby",
    "lastupdated",
    "lastupdatedby",
    "deletedat",
    "deletedby",
    "isdeleted",
    "insertedat",
    "datecreated",
    "datemodified",
    "rowversion",
    "version",
    "etag",
    "rowguid",
    "tenantid",
    "lastupdate",
    "lastupdatedate",
}


class DictionaryError(ValueError):
    """The input could not be interpreted as a data dictionary."""


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def read_dictionary_rows(filename: str, data: bytes) -> list[tuple[int, dict[str, str]]]:
    """Return normalized dictionary rows and their starting physical line numbers."""
    suffix = PurePath(filename).suffix.lower()
    if suffix not in (".csv", ".tsv"):
        raise DictionaryError(f"{filename}: expected a CSV or TSV data dictionary.")
    try:
        source = io.StringIO(data.decode("utf-8-sig"), newline="")
    except UnicodeDecodeError as exc:
        raise DictionaryError(f"Couldn't read {filename} as UTF-8 text.") from exc

    reader = csv.reader(source, dialect=csv.excel_tab if suffix == ".tsv" else csv.excel)

    def numbered_rows() -> Iterable[tuple[int, list[str]]]:
        while True:
            line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                return
            yield line, row

    try:
        return normalize_dictionary_rows(filename, numbered_rows())
    except csv.Error as exc:
        raise DictionaryError(f"Couldn't read {filename} at line {reader.line_num}: {exc}") from exc


def normalize_dictionary_rows(
    filename: str, cells: Iterable[tuple[int, list[str]]]
) -> list[tuple[int, dict[str, str]]]:
    """Recognize header roles and normalize cells from a tabular source."""
    rows = iter(cells)
    first = next(rows, None)
    if first is None or not first[1]:
        raise DictionaryError(f"{filename} is empty.")
    _, header = first

    roles: dict[int, str] = {}
    for i, name in enumerate(header):
        key = _norm(name)
        role = next((role for role, names in HEADERS.items() if key in names), None)
        if role and role not in roles.values():
            roles[i] = role
    if not {"table", "column"} <= set(roles.values()):
        raise DictionaryError(
            f"{filename} needs a table column and a column-name column "
            "(headers like table_name and column_name)."
        )

    normalized = []
    free_text_last = roles.get(len(header) - 1) in ("description", "table_description")
    for line, row in rows:
        if len(row) > len(header):
            row = _rejoin(row, len(header), free_text_last)
        values = {role: row[i].strip() if i < len(row) else "" for i, role in roles.items()}
        if values["table"] and values["column"]:
            normalized.append((line, values))
    return normalized


def _rejoin(cells: list[str], width: int, free_text_last: bool) -> list[str]:
    """Put back a row a hand-made CSV split at unquoted commas: inside parentheses or quotes
    (ENUM('G','PG'), DECIMAL(4,2)), and in a trailing description."""
    out: list[str] = []
    for cell in cells:
        if out and (out[-1].count("(") > out[-1].count(")") or out[-1].count("'") % 2):
            out[-1] += "," + cell
        else:
            out.append(cell)
    if len(out) > width and free_text_last:
        out = [*out[: width - 1], ",".join(out[width - 1 :])]
    return out


def _sql_column(sql_type: str) -> Column | None:
    """Read a data type the way DDL is read: VARCHAR(45), ENUM('G','PG'), DECIMAL(5,2)."""
    if not sql_type:
        return None
    tables = parse_ddl(f"CREATE TABLE t (value {sql_type});").tables
    return tables[0].columns[0] if tables and tables[0].columns else None


def dictionary_to_schema(rows: Iterable[tuple[int, dict[str, str]]]) -> Schema:
    """Build the shared table and column model from normalized rows."""
    by_table: dict[str, Table] = {}
    raw_refs: dict[tuple[str, str], str] = {}
    for line, r in rows:
        table = by_table.setdefault(r["table"].lower(), Table(r["table"], line))
        if r.get("table_description") and not table.comment:
            table.comment = r["table_description"]
        parsed = _sql_column(r.get("type", ""))
        col = Column(r["column"], DOCUMENTED, [], r.get("type", ""), line)
        if parsed:
            col.type_name, col.type_args, col.raw_type = (
                parsed.type_name,
                parsed.type_args,
                parsed.raw_type,
            )
            col.is_array, col.identity = parsed.is_array, parsed.identity
        col.comment = r.get("description") or None
        description = (col.comment or "").lower()
        if r.get("required"):
            col.not_null = r["required"].strip().lower() in TRUE
        elif r.get("nullable"):
            col.not_null = r["nullable"].strip().lower() in ("n", "no", "false", "0", "not null")
        key = (r.get("key") or "").lower()
        if key in ("u", "uk", "unique", "unique key", "ak", "alternate key"):
            col.unique = True
        if key in TRUE or "pk" in key or "primary" in key or "primary key" in description:
            col.primary_key = True
            table.primary_key.append(col.name)
        if "automatically set" in description or "set automatically" in description:
            col.system = True
        if r.get("choices"):
            col.type_name = "SET" if col.type_name == "SET" else "ENUM"
            col.type_args = [
                v.strip().strip("'\"") for v in re.split(r"[,;|]", r["choices"]) if v.strip()
            ]
        ref = r.get("references") or ""
        if ref or "fk" in key or "foreign" in key:
            raw_refs[(table.name.lower(), col.name.lower())] = (
                ref.split(".")[0].split("(")[0].strip()
            )
        elif "foreign key" in description:
            raw_refs[(table.name.lower(), col.name.lower())] = ""
        table.columns.append(col)
    names = sorted(by_table, key=len, reverse=True)

    def table_for(column: str) -> str | None:
        """Use the longest table-name suffix, e.g. manager_staff_id -> staff."""
        base = re.sub(r"_?id$", "", column.lower())
        return next((t for t in names if base == t or base.endswith("_" + t)), None)

    for table in by_table.values():
        for col in table.columns:
            if col.primary_key or col.name.lower().replace("_", "") in _SYSTEM_COLUMNS:
                continue
            explicit = raw_refs.get((table.name.lower(), col.name.lower()))
            target = (explicit.lower() if explicit else None) or table_for(col.name)
            if target and target in by_table and target != table.name.lower():
                col.references = Ref(by_table[target].name, None, None)
            elif explicit is not None and target:
                col.references = Ref(explicit or target, None, None)
    return Schema(list(by_table.values()), {}, [])


def parse_dictionary(filename: str, data: bytes) -> Schema:
    """Read a CSV or TSV dictionary as tables and columns."""
    rows = read_dictionary_rows(filename, data)
    if not rows:
        raise DictionaryError(f"{filename} contains no table and column rows.")
    return dictionary_to_schema(rows)
