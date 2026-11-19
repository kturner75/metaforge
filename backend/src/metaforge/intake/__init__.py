"""Deterministic schema intake for MetaForge hosts."""

from .ddl import Column, Ref, Schema, Table, parse_ddl
from .dictionary import (
    DictionaryError,
    dictionary_to_schema,
    normalize_dictionary_rows,
    parse_dictionary,
    read_dictionary_rows,
)
from .mapping import IntakeResult, MappedField, TypeChoice, map_ddl, map_schema, rank_sql_types

__all__ = [
    "Column",
    "DictionaryError",
    "IntakeResult",
    "MappedField",
    "Ref",
    "Schema",
    "Table",
    "TypeChoice",
    "dictionary_to_schema",
    "map_ddl",
    "map_schema",
    "normalize_dictionary_rows",
    "parse_ddl",
    "parse_dictionary",
    "rank_sql_types",
    "read_dictionary_rows",
]
