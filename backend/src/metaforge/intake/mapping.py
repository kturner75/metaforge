"""Map parsed SQL schema to MetaForge entity documents."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from .ddl import Column, Ref, Schema, Table, parse_ddl
from .dictionary import DOCUMENTED

# Names that settle a column's kind without a model, as in Engram's importer.
_NAME_RULES = [
    (re.compile(r"e_?mail", re.I), "email"),
    (re.compile(r"phone|fax|mobile|cell(?!ar)", re.I), "phone"),
    (re.compile(r"url|website|web_?site|homepage|link$", re.I), "url"),
    (re.compile(r"(^|_)(pct|percent|percentage)($|_)|Pct$|Percent$", re.I), "percent"),
]

_CHAR_TYPES = {
    "CHAR",
    "VARCHAR",
    "NCHAR",
    "NVARCHAR",
    "CHARACTER",
    "CHARACTER VARYING",
    "VARCHAR2",
    "NVARCHAR2",
    "NATIONAL CHARACTER VARYING",
    "STRING",
    "CITEXT",
    "TINYTEXT",
}

_LONG_TEXT_TYPES = {"TEXT", "CLOB", "NTEXT", "LONGTEXT", "MEDIUMTEXT"}

_INT_TYPES = {
    "SMALLINT",
    "INT",
    "INTEGER",
    "BIGINT",
    "TINYINT",
    "MEDIUMINT",
    "SERIAL",
    "BIGSERIAL",
    "SMALLSERIAL",
    "YEAR",
}

_FLOAT_TYPES = {"REAL", "FLOAT", "DOUBLE", "DOUBLE PRECISION", "FLOAT4", "FLOAT8"}

_BINARY_TYPES = {"BYTEA", "BLOB", "LONGBLOB", "MEDIUMBLOB", "VARBINARY", "BINARY", "IMAGE"}

_DECIMAL_TYPES = {"DECIMAL", "NUMERIC", "DEC", "NUMBER"}

_SAME_FOR_MANY = {
    "equipment",
    "information",
    "staff",
    "data",
    "software",
    "hardware",
    "inventory",
    "personnel",
    "series",
}

# Columns the system fills, not people. Compared without underscores, lower case.
_SYSTEM_TIMESTAMPS = {
    "createdat",
    "createdon",
    "createddate",
    "createdtime",
    "updatedat",
    "updatedon",
    "updateddate",
    "modifiedat",
    "modifiedon",
    "modifieddate",
    "lastmodified",
    "lastmodifiedat",
    "lastupdated",
    "lastupdatedate",
    "insertedat",
    "datecreated",
    "datemodified",
    "lastupdate",
}
_SYSTEM_USERS = {
    "createdby",
    "updatedby",
    "modifiedby",
    "deletedby",
    "lastmodifiedby",
    "lastupdatedby",
}

# SQLite reserves these as aliases for the internal row id, and matches column
# names case-insensitively: a field called rowId would shadow the alias in any
# unquoted use, and once made ORDER BY rowid sort by its random values. The
# importer renames such fields (see _entity).
_SQLITE_ALIASES = {"rowid", "oid", "_rowid_"}

_ON_DELETE = {
    "CASCADE": "cascade",
    "SET NULL": "setNull",
}


@dataclass(frozen=True)
class TypeChoice:
    """The SQL source and ranked MetaForge types for one imported column."""

    table: str
    table_comment: str | None
    column: str | None
    column_comment: str | None
    sql_type: str | None
    line: int
    candidates: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class MappedField:
    """Provenance and SQL details that do not belong in the entity document."""

    entity: str
    name: str
    source: TypeChoice
    decimal_places: int | None = None
    notes: tuple[str, ...] = ()


@dataclass
class IntakeResult:
    documents: list[dict]
    fields: list[MappedField]
    notes: list[str]


def _words(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])", " ", name)
    return [w for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def _singular(word: str) -> str:
    low = word.lower()
    if low in _SAME_FOR_MANY or low.endswith(("ss", "us", "is")) or len(low) < 4:
        return word
    if low.endswith("ies"):
        return word[:-3] + "y"
    if low.endswith(("sses", "xes", "ches", "shes", "zes")):
        return word[:-2]
    if low.endswith("s"):
        return word[:-1]
    return word


def _plural(word: str) -> str:
    low = word.lower()
    if low in _SAME_FOR_MANY or low.endswith(("ss", "us", "is")):
        return word
    if low.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    if low.endswith("y") and len(low) > 1 and low[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def table_to_entity(table: str) -> str:
    """``vendor_contacts`` -> ``VendorContact``; ``equipment`` -> ``Equipment``."""
    words = _words(table)
    if not words:
        raise ValueError(f"table {table!r} has no usable characters for an entity name")
    if words[0][0].isdigit():
        words.insert(0, "Table")
    words[-1] = _singular(words[-1])
    return "".join(w[:1].upper() + w[1:] for w in words)


def column_to_field(column: str) -> str:
    """``legal_name`` -> ``legalName``; ``id`` stays ``id``."""
    words = _words(column)
    if not words:
        raise ValueError(f"column {column!r} has no usable characters for a field name")
    if words[0][0].isdigit():
        words.insert(0, "field")
    first = words[0].lower()
    rest = "".join(
        w[:1].upper() + w[1:].lower() if w.isupper() else w[:1].upper() + w[1:] for w in words[1:]
    )
    return first + rest


def humanize(name: str) -> str:
    """``paymentTerms`` -> ``Payment Terms``; ``net_30`` -> ``Net 30``."""
    return " ".join(w[:1].upper() + w[1:] for w in _words(name))


def _abbreviation(entity: str, used: set[str]) -> str:
    """A 2-5 character uppercase abbreviation, unique among ``used``.

    The first three letters of the name: Company -> COM, VendorContact ->
    VEN. Collisions extend the name, then take a number: Customer -> CUS,
    CustomerOrder -> CUST.
    """
    letters = re.sub(r"[^A-Za-z0-9]", "", entity).upper()
    for n in (3, 4, 5):
        if len(letters) >= n and letters[:n] not in used:
            return letters[:n]
    base = letters[:4] or "E"
    n = 2
    while f"{base}{n}" in used:
        n += 1
    return f"{base}{n}"


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------


def _checks_for(table: Table, col: Column) -> list[str]:
    name = re.escape(col.name)
    return [c for c in [*col.checks, *table.checks] if re.search(rf"\b{name}\b", c, re.I)]


def _in_list(checks: list[str], col: Column) -> list[str] | None:
    for c in checks:
        m = re.fullmatch(rf"\s*{re.escape(col.name)}\s+IN\s*\((.*)\)\s*", c, re.I | re.S)
        if m:
            values = re.findall(r"'((?:[^']|'')*)'", m.group(1))
            if values:
                return [v.replace("''", "'") for v in values]
    return None


def _range(checks: list[str], col: Column) -> dict[str, float]:
    out: dict[str, float] = {}
    n = re.escape(col.name)
    num = r"(-?\d+(?:\.\d+)?)"
    integer = col.type_name in _INT_TYPES
    for c in checks:
        parts = [c] if "BETWEEN" in c.upper() else re.split(r"\bAND\b(?![^(]*\))", c, flags=re.I)
        for part in parts:
            if m := re.search(rf"\b{n}\s+BETWEEN\s+{num}\s+AND\s+{num}", part, re.I):
                out["min"], out["max"] = float(m.group(1)), float(m.group(2))
            elif m := re.search(rf"\b{n}\s*(>=|>)\s*{num}", part, re.I):
                value = float(m.group(2))
                if m.group(1) == ">" and integer:
                    # Strict on an integer column: the smallest value above
                    # v is floor(v) + 1, so `qty > 0` means min 1, not 0.
                    value = float(math.floor(value) + 1)
                out["min"] = value
            elif m := re.search(rf"\b{n}\s*(<=|<)\s*{num}", part, re.I):
                value = float(m.group(2))
                if m.group(1) == "<" and integer:
                    value = float(math.ceil(value) - 1)
                out["max"] = value
    return {k: (int(v) if v.is_integer() else v) for k, v in out.items()}


def _max_length(col: Column) -> int | None:
    if col.type_name in _CHAR_TYPES and col.type_args and col.type_args[0].isdigit():
        return int(col.type_args[0])
    return None


def _decimal_places(col: Column) -> int | None:
    """The scale of a fixed-point column, when it needs the decimal generator.

    Scale 2 maps to currency (whose decimal default already uses 2 places)
    and scale 0 is integer-like, so only other scales are reported.
    """
    if col.type_name not in _DECIMAL_TYPES:
        return None
    nums = [int(a) for a in col.type_args if a.isdigit()]
    if len(nums) < 2 or nums[1] in (0, 2):
        return None
    return nums[1]


def _precision_max(col: Column) -> float | None:
    """The largest value a fixed-point column holds, from (precision, scale).

    NUMERIC(4, 3) holds up to 9.999. Computed with Decimal, so the cap is
    exact before it becomes a float. Past 15 digits of precision a float
    can't hold the cap without rounding up past it (NUMERIC(18, 4) is
    99999999999999.9999; float gives 100000000000000.0), so no cap is
    reported there. Only reported where _decimal_places is.
    """
    places = _decimal_places(col)
    if places is None:
        return None
    nums = [int(a) for a in col.type_args if a.isdigit()]
    if nums[0] > 15:
        return None
    return float(Decimal(10) ** (nums[0] - places) - Decimal(1).scaleb(-places))


def _primary_key(table: Table) -> list[str]:
    """The table's key columns: the declared constraint, else the columns
    marked primary key inline."""
    return table.primary_key or [c.name for c in table.columns if c.primary_key]


def _is_surrogate_key(table: Table, col: Column) -> bool:
    keys = _primary_key(table)
    if len(keys) != 1 or keys[0].lower() != col.name.lower():
        return False
    singular_table = _singular(" ".join(_words(table.name))).replace(" ", "_").lower()
    return (
        col.identity
        or col.type_name in ("UUID", "UNIQUEIDENTIFIER")
        or col.name.lower()
        in ("id", f"{table.name.lower()}_id", f"{singular_table}_id", f"{singular_table}id")
    )


def _is_name_field(col: Column) -> bool:
    """Only an exact name field (``name``, ``first_name``, ...) gets the
    ``name`` type. Anything else ending in _name (``site_name``,
    ``product_name``) stays a string: the ``name`` type would fill it with a
    person's name."""
    return col.name.lower().replace("_", "") in ("name", "firstname", "lastname", "fullname")


def _candidates(table: Table, col: Column) -> tuple[tuple[str, ...], str, list[str] | None]:
    """Rank allowed types, retaining the deterministic import default."""
    sql_type, args = col.type_name, col.type_args
    raw = col.raw_type or sql_type
    if sql_type in ("ENUM", "SET"):
        kind = "multi_picklist" if sql_type == "SET" or col.is_array else "picklist"
        return (kind,), raw, list(args)
    if values := _in_list(_checks_for(table, col), col):
        kind = "multi_picklist" if col.is_array else "picklist"
        return (kind,), "CHECK list", values

    for pattern, kind in _NAME_RULES:
        if not pattern.search(col.name):
            continue
        if kind in ("email", "phone", "url") and (
            sql_type in _CHAR_TYPES or sql_type in _LONG_TEXT_TYPES
        ):
            return (kind,), f"{raw}, inferred from the column name", None
        if kind == "percent" and sql_type in _INT_TYPES | _FLOAT_TYPES | _DECIMAL_TYPES:
            return (kind,), f"{raw}, inferred from the column name", None

    kinds, reason = rank_sql_types(col)
    if kinds[0] == "string" and sql_type in _CHAR_TYPES and _is_name_field(col):
        return ("name", *kinds), f"{raw}, inferred from the column name", None
    return kinds, reason, None


def rank_sql_types(col: Column) -> tuple[tuple[str, ...], str]:
    """Return types allowed by SQL alone, with the default first and its basis."""
    sql_type, args = col.type_name, col.type_args
    raw = col.raw_type or sql_type
    nums = [int(arg) for arg in args if arg.isdigit()]
    if sql_type == DOCUMENTED:
        return ("string",), "Dictionary row without a SQL type"
    if sql_type in ("ENUM", "SET"):
        return ("multi_picklist" if sql_type == "SET" or col.is_array else "picklist",), raw
    if col.is_array:
        kinds = ("description",)
    elif sql_type in ("BOOLEAN", "BOOL", "BIT") or (sql_type == "TINYINT" and nums[:1] == [1]):
        kinds = ("checkbox",)
    elif sql_type == "DATE":
        kinds = ("date",)
    elif sql_type.startswith(("TIMESTAMP", "DATETIME", "SMALLDATETIME", "DATETIMEOFFSET")):
        kinds = ("datetime", "date")
    elif sql_type.startswith("TIME"):
        kinds = ("string",)
    elif sql_type in _INT_TYPES or sql_type.startswith(
        ("INT ", "INTEGER ", "BIGINT ", "SMALLINT ", "TINYINT ")
    ):
        kinds = ("number",)
    elif sql_type in ("MONEY", "SMALLMONEY"):
        kinds = ("currency",)
    elif sql_type in _DECIMAL_TYPES and nums[1:2] == [2]:
        kinds = ("currency", "number", "percent")
    elif sql_type in _DECIMAL_TYPES | _FLOAT_TYPES:
        kinds = ("number", "percent", "currency")
    elif sql_type in ("UUID", "UNIQUEIDENTIFIER"):
        kinds = ("string",)
    elif sql_type in ("JSON", "JSONB", "XML"):
        kinds = ("description",)
    elif sql_type in _BINARY_TYPES:
        kinds = ("attachment",)
    elif (
        sql_type in _LONG_TEXT_TYPES
        or "MAX" in (a.upper() for a in args)
        or (nums and nums[0] > 255)
    ):
        kinds = ("description", "string", "address")
    elif sql_type in _CHAR_TYPES:
        kinds = ("string", "email", "phone", "url", "address")
    else:
        return ("string",), f"{raw} (unknown SQL type; mapped to string)"
    return kinds, raw


def _source(table: Table, col: Column, candidates: tuple[str, ...], reason: str) -> TypeChoice:
    return TypeChoice(
        table.name,
        table.comment,
        col.name,
        col.comment,
        col.raw_type or col.type_name,
        col.line,
        candidates,
        reason,
    )


def _relation_field(target_entity: str, ref: Ref) -> dict:
    relation: dict = {"entity": target_entity}
    action = _ON_DELETE.get((ref.on_delete or "").upper(), "restrict")
    if action != "restrict":
        relation["onDelete"] = action
    return relation


def _field(
    table: Table,
    col: Column,
    entities: dict[str, str],
    notes: list[str],
    choose: Callable[[TypeChoice], str] | None,
) -> tuple[dict, TypeChoice, int | None]:
    """One column as a MetaForge field mapping."""
    keys = _primary_key(table)
    is_pk = col.name.lower() in {k.lower() for k in keys}
    single_pk = len(keys) == 1
    name = (
        "id" if is_pk and single_pk and _is_surrogate_key(table, col) else column_to_field(col.name)
    )
    fd: dict = {"name": name}

    target = None
    places = None
    if col.references:
        target = entities.get(col.references.table.lower())
        if target is None:
            notes.append(
                f"{table.name}.{col.name}: references table '{col.references.table}', "
                "which is not in this DDL; kept as a relation to it"
            )
            target = table_to_entity(col.references.table)

    if is_pk and single_pk:
        source = _source(table, col, ("id",), "Primary key")
        fd["type"] = "id"
        fd["primaryKey"] = True
        if target is not None:
            notes.append(
                f"{table.name}.{col.name}: primary key and foreign key at once; "
                "kept as the id, the reference to it is not carried"
            )
    elif target is not None:
        source = _source(table, col, ("relation",), f"Foreign key to {col.references.table}")
        fd["type"] = "relation"
        fd["displayName"] = target
        fd["relation"] = _relation_field(target, col.references)
    else:
        candidates, reason, values = _candidates(table, col)
        source = _source(table, col, candidates, reason)
        kind = choose(source) if choose is not None and len(candidates) > 1 else candidates[0]
        if kind not in candidates:
            raise ValueError(
                f"{table.name}.{col.name}: {kind!r} is not one of {', '.join(candidates)}"
            )
        fd["type"] = kind
        if values is not None:
            fd["options"] = [
                {"value": v, "label": humanize(v) if re.fullmatch(r"[a-z0-9_]+", v) else v}
                for v in values
            ]
        places = _decimal_places(col)

    if col.comment:
        fd["description"] = col.comment

    flat = col.name.lower().replace("_", "")
    if flat in _SYSTEM_TIMESTAMPS:
        fd["auto"] = "now"
        fd["readOnly"] = True
    elif flat in _SYSTEM_USERS:
        fd["auto"] = "context.userId"
        fd["readOnly"] = True
    elif flat == "tenantid":
        fd["auto"] = "context.tenantId"
        fd["readOnly"] = True
    elif flat in ("rowversion", "rowguid") or col.system:
        # A database-managed concurrency token: nothing to generate.
        fd["readOnly"] = True

    # System-filled fields carry no validation: the host fills them, so a
    # NOT NULL in the DDL says nothing about what a user must enter.
    validation: dict = {}
    if "auto" not in fd and not fd.get("readOnly"):
        if col.not_null and not (is_pk and single_pk):
            validation["required"] = True
        if fd["type"] in ("string", "name", "description", "email", "phone", "url", "address"):
            if (length := _max_length(col)) is not None:
                validation["maxLength"] = length
        if fd["type"] in ("number", "currency", "percent"):
            validation.update(_range(_checks_for(table, col), col))
            if (cap := _precision_max(col)) is not None:
                # The column itself caps the value, whatever the CHECKs say.
                validation["max"] = min(validation["max"], cap) if "max" in validation else cap
            elif _decimal_places(col) is not None:
                # A cap applies but the precision is too wide to record one.
                notes.append(
                    f"{table.name}.{col.name}: no max recorded; the NUMERIC cap "
                    "is too wide to hold exactly as a number"
                )
    if validation:
        fd["validation"] = validation

    if col.unique and not is_pk:
        notes.append(f"{table.name}.{col.name}: UNIQUE is not carried (no uniqueness rule yet)")
    return fd, source, places


def _entity(
    table: Table,
    entities: dict[str, str],
    used_abbrev: set[str],
    notes: list[str],
    choose: Callable[[TypeChoice], str] | None,
) -> tuple[dict, list[MappedField]]:
    name = entities[table.name.lower()]
    abbrev = _abbreviation(name, used_abbrev)
    used_abbrev.add(abbrev)
    words = _words(name)
    data: dict = {
        "entity": name,
        "abbreviation": abbrev,
        "displayName": humanize(name),
        "pluralName": " ".join([*words[:-1], _plural(words[-1])]),
    }
    if table.comment:
        data["description"] = table.comment

    keys = _primary_key(table)
    fields = []
    field_sources = []
    for col in table.columns:
        field_notes: list[str] = []
        fd, source, places = _field(table, col, entities, field_notes, choose)
        fields.append(fd)
        field_sources.append((source, places, field_notes))
    # Rename fields that collide with SQLite's row-id aliases before the
    # synthetic key is chosen, so the key's name check sees the final names.
    taken = {f["name"].lower() for f in fields}
    for fd, (_, _, field_notes) in zip(fields, field_sources, strict=True):
        if fd["name"].lower() not in _SQLITE_ALIASES:
            continue
        base = fd["name"] + "Value"
        new = base
        n = 2
        while new.lower() in taken:
            new = f"{base}{n}"
            n += 1
        field_notes.append(
            f"{table.name}: field '{fd['name']}' renamed to '{new}'; "
            "'rowid', 'oid' and '_rowid_' are SQLite aliases"
        )
        taken.add(new.lower())
        fd["name"] = new
    mapped_fields = []
    taken.clear()
    for fd, (source, places, field_notes) in zip(fields, field_sources, strict=True):
        field_name = fd["name"].lower()
        if field_name in taken:
            raise ValueError(f"table {table.name!r}: multiple columns map to field {fd['name']!r}")
        taken.add(field_name)
        notes.extend(field_notes)
        mapped_fields.append(MappedField(name, fd["name"], source, places, tuple(field_notes)))

    if len(keys) != 1:
        why = "no primary key" if not keys else f"composite primary key ({', '.join(keys)})"
        key_name = "id"
        if key_name in taken:
            # syntheticId, not rowId: rowId is a SQLite alias (see above).
            key_name = "syntheticId"
            n = 2
            while key_name.lower() in taken:
                key_name = f"syntheticId{n}"
                n += 1
        note = f"{table.name}: {why}; added {key_name} as the synthetic key"
        if key_name != "id":
            note += " ('id' is taken)"
        notes.append(note)
        fields.insert(0, {"name": key_name, "type": "id", "primaryKey": True})
        source = TypeChoice(table.name, table.comment, None, None, None, table.line, ("id",), why)
        mapped_fields.insert(0, MappedField(name, key_name, source, notes=(note,)))
    data["fields"] = fields
    return data, mapped_fields


def map_schema(
    schema: Schema, *, choose: Callable[[TypeChoice], str] | None = None
) -> IntakeResult:
    """Build entity documents and provenance without writing files.

    For ambiguous types, ``choose`` can select one of the ranked candidates.
    Without a callback, the first candidate wins. Structural types and
    recognized semantic column names are already settled.
    """
    if not schema.tables:
        raise ValueError("no CREATE TABLE statements found in the DDL")
    # Two tables can map to one entity (`vendor` and `vendors` both become
    # Vendor). Fail before writing anything rather than letting the second
    # file silently overwrite the first. The comparison is case-insensitive:
    # Vendor.yaml and VENDOR.yaml are one file on macOS and Windows.
    seen: dict[str, str] = {}
    entities: dict[str, str] = {}
    for table in schema.tables:
        entity = table_to_entity(table.name)
        if entity.lower() in seen:
            raise ValueError(
                f"tables '{seen[entity.lower()]}' and '{table.name}' both map to "
                f"entity '{entity}'; rename one of them"
            )
        seen[entity.lower()] = table.name
        entities[table.name.lower()] = entity
    used_abbrev: set[str] = set()
    notes = list(schema.notes)
    documents = []
    fields = []
    for table in schema.tables:
        document, mapped_fields = _entity(table, entities, used_abbrev, notes, choose)
        documents.append(document)
        fields.extend(mapped_fields)
    return IntakeResult(documents, fields, notes)


def map_ddl(text: str, *, choose: Callable[[TypeChoice], str] | None = None) -> IntakeResult:
    """Parse SQL DDL and build MetaForge entity documents."""
    return map_schema(parse_ddl(text), choose=choose)
