# ADR-0017: Shared schema intake

## Status

Proposed

## Context

Engram and mfgen each carry a DDL parser and rules for mapping SQL columns
to metadata. They need the same interpretation of keys, checks, choices and
field types. Engram also uses its modeler to resolve ambiguous field types.

## Decision

Put SQL DDL parsing and deterministic mapping in MetaForge's light core.
Hosts can use `metaforge.intake.map_ddl` with DDL text, or
`map_schema` with the parser's table and column model. The mapper returns
entity documents and field provenance, including source lines, ranked types
and import notes. Hosts decide how to store or present the documents.

The first candidate is the default. When multiple candidates are available,
a host can supply a callback to select one. The callback can inspect the SQL
type, table and column names, and comments. Engram owns its model calls,
enrichment, and change sets. mfgen can use the default mapping and attach
generation-specific settings such as decimal places from the provenance.

Keep the parser identical to Engram's during migration. Use the current
supplier-onboarding YAML as a parity fixture for mfgen. CSV and TSV data
dictionary intake can use the same table and column model when it is added.

## Consequences

Hosts can share intake without depending on the MetaForge server. Each host
can switch independently. Once both have switched, MetaForge is the place to
fix and test SQL parsing and mapping.
