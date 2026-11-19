"""Read SQL DDL into tables and columns, keeping the line each came from.

Covers what database exports commonly hold, in Postgres, MySQL and SQL Server
spellings: CREATE TABLE (columns, keys, foreign keys, CHECK, NOT NULL,
DEFAULT, identity), CREATE TYPE ... AS ENUM, COMMENT ON TABLE/COLUMN, inline
COMMENT, and ALTER TABLE ... ADD FOREIGN KEY. Anything else (indexes, inserts,
grants) is ignored. This is not a SQL parser; it reads definitions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TOKEN = re.compile(r"""
    (?P<str>'(?:[^']|'')*')
  | (?P<qid>"(?:[^"]|"")*"|`[^`]*`|\[[^\]]+\])
  | (?P<num>-?\d+(?:\.\d+)?)
  | (?P<word>[A-Za-z_][A-Za-z0-9_$#]*)
  | (?P<op><=|>=|<>|!=|::|[(),.;=<>*+\-/\[\]])
""", re.X)

# Words that end a column's type and start its constraints.
CONSTRAINT_WORDS = {"NOT", "NULL", "DEFAULT", "PRIMARY", "UNIQUE", "REFERENCES", "CHECK", "CONSTRAINT", "COMMENT",
                    "AUTO_INCREMENT", "AUTOINCREMENT", "IDENTITY", "GENERATED", "COLLATE", "ON"}
TYPE_CONTINUES = {"PRECISION", "VARYING", "CHARACTER", "CHAR", "VARCHAR", "WITH", "WITHOUT", "TIME", "ZONE", "UNSIGNED",
                  "SIGNED", "ZEROFILL", "LARGE", "OBJECT"}
TABLE_CONSTRAINTS = {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "KEY", "INDEX", "FULLTEXT", "SPATIAL", "EXCLUDE"}


@dataclass
class Ref:
    table: str
    column: str | None
    on_delete: str | None  # "CASCADE", "SET NULL", ...


@dataclass
class Column:
    name: str
    type_name: str  # upper-case base type: VARCHAR, NUMERIC, TIMESTAMP, ENUM, user type name...
    type_args: list[str]  # (12, 2) -> ["12", "2"]; ENUM('a','b') -> ["a", "b"]
    raw_type: str  # as written, for explanations: "VARCHAR(255)"
    line: int
    not_null: bool = False
    has_default: bool = False
    primary_key: bool = False
    unique: bool = False
    identity: bool = False  # SERIAL, IDENTITY, AUTO_INCREMENT, GENERATED ... AS IDENTITY
    is_array: bool = False
    system: bool = False  # documented as filled in by the system
    suggested_kind: str | None = None  # a form reader's suggestion, for a column with no SQL type
    label: str | None = None  # the label as written on a form, kept as is instead of made from the name
    references: Ref | None = None
    checks: list[str] = field(default_factory=list)
    comment: str | None = None


@dataclass
class Table:
    name: str
    line: int
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    comment: str | None = None

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name.lower() == name.lower()), None)


@dataclass
class Schema:
    tables: list[Table]
    enums: dict[str, list[str]]  # lower-case type name -> values
    notes: list[str]

    def table(self, name: str) -> Table | None:
        return next((t for t in self.tables if t.name.lower() == name.lower()), None)


@dataclass
class Tok:
    kind: str
    value: str
    line: int

    @property
    def upper(self) -> str:
        return self.value.upper() if self.kind == "word" else self.value


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _blank_routines(text: str) -> str:
    """Blank MySQL DELIMITER blocks (procedures, functions, triggers), keeping newlines."""
    return re.sub(r"(?ims)^[ \t]*DELIMITER[ \t]+(?!;[ \t]*$)\S+[ \t]*$.*?^[ \t]*DELIMITER[ \t]+;[ \t]*$",
                  lambda m: _blank(m.group()), text)


def _blank_comments(text: str) -> str:
    """Remove -- and /* */ comments, keeping every newline so line numbers hold. MySQL's
    versioned comments (/*!50705 location GEOMETRY */) are code, so their contents are kept."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            j = i + 1
            while j < n and not (text[j] == "'" and (j + 1 >= n or text[j + 1] != "'")):
                j += 2 if text[j] == "'" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("--", i) or ch == "#" and (i == 0 or text[i - 1] == "\n"):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*!", i):
            m = re.match(r"/\*!\d*", text[i:])
            j = text.find("*/", i)
            j = n if j < 0 else j
            out.append(" " * len(m.group()) + text[i + len(m.group()):j] + "  ")
            i = min(j + 2, n)
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(_blank(text[i:j]))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _tokens(text: str) -> list[Tok]:
    toks, line, pos = [], 1, 0
    for m in TOKEN.finditer(text):
        line += text.count("\n", pos, m.start())
        pos = m.start()
        kind = m.lastgroup or "op"
        value = m.group()
        if kind == "qid":
            value = value[1:-1].replace('""', '"')
            kind = "word"
        elif kind == "str":
            value = value[1:-1].replace("''", "'")
        toks.append(Tok(kind, value, line))
    return toks


def _statements(toks: list[Tok]) -> list[list[Tok]]:
    out, cur = [], []
    for t in toks:
        if t.kind == "op" and t.value == ";":
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def _name(toks: list[Tok], i: int) -> tuple[str, int]:
    """A possibly qualified name (schema.table) starting at i; returns its last part."""
    name = toks[i].value
    i += 1
    while i + 1 < len(toks) and toks[i].value == "." and toks[i + 1].kind == "word":
        name = toks[i + 1].value
        i += 2
    return name, i


def _group(toks: list[Tok], i: int) -> tuple[list[Tok], int]:
    """The tokens inside the parentheses that open at i, and the index after the closing one."""
    depth, j = 0, i
    while j < len(toks):
        if toks[j].value == "(" and toks[j].kind == "op":
            depth += 1
        elif toks[j].value == ")" and toks[j].kind == "op":
            depth -= 1
            if depth == 0:
                return toks[i + 1:j], j + 1
        j += 1
    return toks[i + 1:], len(toks)


def _split(toks: list[Tok]) -> list[list[Tok]]:
    parts, cur, depth = [], [], 0
    for t in toks:
        if t.kind == "op" and t.value == "(":
            depth += 1
        elif t.kind == "op" and t.value == ")":
            depth -= 1
        if t.kind == "op" and t.value == "," and depth == 0:
            parts.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        parts.append(cur)
    return parts


def _text(toks: list[Tok], type_spacing: bool = False) -> str:
    """Tokens back to text. Types are written VARCHAR(255); expressions keep a space: IN ('a')."""
    out = ""
    for t in toks:
        v = f"'{t.value}'" if t.kind == "str" else t.value
        if out and not (v in (")", ",", ".", "::", "[", "]") or out.endswith(("(", ".", "::", "["))
                        or type_spacing and v == "(" and out[-1:].isalnum()):
            out += " "
        out += v
    return out


def _ref(toks: list[Tok], i: int) -> tuple[Ref, int]:
    """REFERENCES table [(col)] [ON DELETE action] [ON UPDATE action], starting after REFERENCES."""
    table, i = _name(toks, i)
    column = None
    if i < len(toks) and toks[i].value == "(":
        inner, i = _group(toks, i)
        column = inner[0].value if inner else None
    on_delete = None
    while i + 2 < len(toks) and toks[i].upper == "ON":
        action_start = i + 2
        j = action_start
        words = []
        while j < len(toks) and toks[j].upper in ("CASCADE", "SET", "NULL", "DEFAULT", "RESTRICT", "NO", "ACTION"):
            words.append(toks[j].upper)
            j += 1
        if toks[i + 1].upper == "DELETE":
            on_delete = " ".join(words) or None
        i = j
    return Ref(table, column, on_delete), i


def _column(item: list[Tok], enums: dict[str, list[str]]) -> Column:
    name = item[0].value
    i = 1
    # The type is its first word plus any words that continue it: DOUBLE PRECISION, CHARACTER VARYING,
    # TIMESTAMP WITH TIME ZONE, INT UNSIGNED.
    words = [item[i].value] if i < len(item) and item[i].kind == "word" else []
    i += len(words)
    while i < len(item) and item[i].kind == "word" and item[i].upper in TYPE_CONTINUES:
        words.append(item[i].value)
        i += 1
    args: list[str] = []
    if i < len(item) and item[i].value == "(":
        inner, i = _group(item, i)
        args = [t.value for t in inner if t.kind in ("num", "str", "word")]
        while i < len(item) and item[i].upper in ("UNSIGNED", "SIGNED", "ZEROFILL", "WITH", "WITHOUT", "TIME", "ZONE"):
            words.append(item[i].value)
            i += 1
    is_array = False
    while i + 1 < len(item) and item[i].value == "[" and item[i + 1].value == "]":
        is_array, i = True, i + 2
    while i < len(item) and item[i].upper == "ARRAY":
        is_array, i = True, i + 1
    type_name = " ".join(w.upper() for w in words) or "TEXT"
    raw_type = _text(item[1:i], type_spacing=True)
    col = Column(name, type_name, args, raw_type, item[0].line, is_array=is_array)
    if type_name in ("SERIAL", "BIGSERIAL", "SMALLSERIAL"):
        col.identity = True
    if type_name.lower() in enums:
        col.type_name, col.type_args = "ENUM", enums[type_name.lower()]
    while i < len(item):
        w = item[i].upper
        if w == "NOT" and i + 1 < len(item) and item[i + 1].upper == "NULL":
            col.not_null, i = True, i + 2
        elif w == "DEFAULT":
            col.has_default = True
            i += 1
            if i < len(item) and item[i].value == "(":
                _, i = _group(item, i)
            else:
                i += 1
                while i < len(item) and item[i].kind == "op" and item[i].value in ("::", "(", "."):
                    if item[i].value == "(":
                        _, i = _group(item, i)
                    else:
                        i += 2
        elif w == "PRIMARY":
            col.primary_key, i = True, i + 2
        elif w == "UNIQUE":
            col.unique, i = True, i + 1
        elif w in ("AUTO_INCREMENT", "AUTOINCREMENT"):
            col.identity, i = True, i + 1
        elif w == "IDENTITY":
            col.identity, i = True, i + 1
            if i < len(item) and item[i].value == "(":
                _, i = _group(item, i)
        elif w == "GENERATED":
            j = i
            while j < len(item) and item[j].upper not in ("IDENTITY", "STORED"):
                j += 1
            if j < len(item) and item[j].upper == "IDENTITY":
                col.identity = True
            elif j < len(item):
                col.has_default = True  # a computed column: nobody enters it
            i = j + 1
            if i < len(item) and item[i].value == "(":
                _, i = _group(item, i)
        elif w == "REFERENCES":
            col.references, i = _ref(item, i + 1)
        elif w == "CHECK" and i + 1 < len(item) and item[i + 1].value == "(":
            inner, i = _group(item, i + 1)
            col.checks.append(_text(inner))
        elif w == "COMMENT" and i + 1 < len(item) and item[i + 1].kind == "str":
            col.comment, i = item[i + 1].value, i + 2
        else:
            i += 1
    return col


def _create_table(stmt: list[Tok], enums: dict[str, list[str]], notes: list[str]) -> Table | None:
    i = next((k for k, t in enumerate(stmt) if t.upper == "TABLE"), None)
    if i is None:
        return None
    i += 1
    while i < len(stmt) and stmt[i].upper in ("IF", "NOT", "EXISTS"):
        i += 1
    if i >= len(stmt):
        return None
    name, i = _name(stmt, i)
    table = Table(name, stmt[0].line)
    if i >= len(stmt) or stmt[i].value != "(":
        notes.append(f"Line {table.line}: {name} has no column list (CREATE TABLE ... AS?); skipped.")
        return None
    body, after = _group(stmt, i)
    for item in _split(body):
        if not item:
            continue
        if item[0].kind == "word" and item[0].upper in TABLE_CONSTRAINTS:
            _table_constraint(table, item)
        elif item[0].kind == "word":
            table.columns.append(_column(item, enums))
    rest = stmt[after:]
    for k, t in enumerate(rest):
        if t.upper == "COMMENT" and k + 1 < len(rest):
            nxt = rest[k + 2] if rest[k + 1].value == "=" and k + 2 < len(rest) else rest[k + 1]
            if nxt.kind == "str":
                table.comment = nxt.value
    for name in table.primary_key:
        col = table.column(name)
        if col:
            col.primary_key = True
    return table


def _table_constraint(table: Table, item: list[Tok]) -> None:
    i = 0
    if item[0].upper == "CONSTRAINT":
        i = 2
    if i >= len(item):
        return
    w = item[i].upper
    if w == "PRIMARY":
        j = next((k for k in range(i, len(item)) if item[k].value == "("), None)
        if j is not None:
            inner, _ = _group(item, j)
            table.primary_key = [t.value for t in inner if t.kind == "word"]
    elif w == "FOREIGN":
        j = next((k for k in range(i, len(item)) if item[k].value == "("), None)
        if j is None:
            return
        inner, k = _group(item, j)
        cols = [t.value for t in inner if t.kind == "word"]
        while k < len(item) and item[k].upper != "REFERENCES":
            k += 1
        if k < len(item) and len(cols) == 1:
            ref, _ = _ref(item, k + 1)
            col = table.column(cols[0])
            if col:
                col.references = ref
    elif w == "CHECK" and i + 1 < len(item) and item[i + 1].value == "(":
        inner, _ = _group(item, i + 1)
        table.checks.append(_text(inner))
    elif w == "UNIQUE":
        j = next((k for k in range(i, len(item)) if item[k].value == "("), None)
        if j is not None:
            inner, _ = _group(item, j)
            cols = [t.value for t in inner if t.kind == "word"]
            if len(cols) == 1 and table.column(cols[0]):
                table.column(cols[0]).unique = True


def parse_ddl(text: str) -> Schema:
    toks = _tokens(_blank_comments(_blank_routines(text)))
    enums: dict[str, list[str]] = {}
    tables: list[Table] = []
    notes: list[str] = []
    comments: list[tuple[str, str, str | None, str]] = []  # (kind, table, column, text)
    alters: list[list[Tok]] = []
    for stmt in _statements(toks):
        words = [t.upper for t in stmt[:6] if t.kind == "word"]
        if words[:1] == ["CREATE"] and "TYPE" in words and any(t.upper == "ENUM" for t in stmt):
            k = next(k for k, t in enumerate(stmt) if t.upper == "TYPE")
            name, _ = _name(stmt, k + 1)
            j = next(k for k, t in enumerate(stmt) if t.upper == "ENUM")
            inner, _ = _group(stmt, j + 1)
            enums[name.lower()] = [t.value for t in inner if t.kind == "str"]
        elif words[:1] == ["CREATE"] and "TABLE" in words and not {"TEMPORARY", "TEMP"} & set(words):
            table = _create_table(stmt, enums, notes)
            if table:
                tables.append(table)
        elif words[:2] == ["COMMENT", "ON"] and len(stmt) > 3:
            kind = stmt[2].upper
            parts, k = [stmt[3].value], 4
            while k + 1 < len(stmt) and stmt[k].value == ".":
                parts.append(stmt[k + 1].value)
                k += 2
            text_tok = next((t for t in stmt[k:] if t.kind == "str"), None)
            if text_tok and kind == "TABLE":
                comments.append(("table", parts[-1], None, text_tok.value))
            elif text_tok and kind == "COLUMN" and len(parts) >= 2:
                comments.append(("column", parts[-2], parts[-1], text_tok.value))
        elif words[:2] == ["ALTER", "TABLE"]:
            alters.append(stmt)
    schema = Schema(tables, enums, notes)
    for kind, tname, cname, text_ in comments:
        table = schema.table(tname)
        if table and kind == "table":
            table.comment = text_
        elif table and cname and table.column(cname):
            table.column(cname).comment = text_
    for stmt in alters:
        k = 2
        while k < len(stmt) and stmt[k].upper in ("ONLY", "IF", "EXISTS"):
            k += 1
        if k >= len(stmt):
            continue
        tname, k = _name(stmt, k)
        table = schema.table(tname)
        if not table:
            continue
        for part in _split(stmt[k:]):
            if part and part[0].upper == "ADD":
                _table_constraint(table, part[1:])
    return schema
