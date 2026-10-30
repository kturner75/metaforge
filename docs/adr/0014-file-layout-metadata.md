# ADR-0014: File-Layout Metadata (Delimited & Fixed-Width)

## Status
Accepted

## Context

MetaForge is metadata-driven: YAML is the single source of truth for entities,
fields, validations, UI, hooks, screens, and views. Integrations, however, still
arrive as flat files — vendor CSVs, legacy fixed-width extracts, multi-record
feeds with header/trailer lines. Parsing them has historically meant bespoke
application code.

This decision comes out of Engram's document-types design (EN-020, 2026-10-29):
deterministic parsers are foundational MetaForge *metadata*, not application
code, so that AI-assisted configuration and a future manual UI author the **same
definition**. MF-020 adds that definition: a **file layout**.

Two questions were left open by EN-020 and resolved here:
1. How expressive do transforms need to be?
2. Should arbitrary custom code be allowed for edge cases?

## Decision

Introduce a **file layout** as a first-class metadata artifact in
`metadata/layouts/*.yaml`, loaded by `metaforge.layouts.LayoutLoader` (mirroring
the entity/view/screen loaders) and validated by `layout.schema.json`. A layout
describes a file's structure and how it maps to an entity, and the engine works
**both directions**.

### Structure
- **Format** — `delimited` (delimiter, quote, escape, encoding, `hasHeader`) or
  `fixed` (byte `offset`/`width` slices, `recordLength`).
- **Record types** — optional. A `recordType` selector reads a type code per
  line (a column, or a fixed slice) and picks a `data` / `header` / `trailer`
  record layout. A trailer may declare a `recordCountField`.
- **Mapping** — each entry maps one entity field to a cell, with optional
  ordered transforms, `required`, `default`, and `const` (a literal that also
  tells the writer which column/offset it owns, e.g. a record-type marker).

### Reading
Reading produces records carrying exact **provenance** (`CellLocation`: row,
column or byte offset, and the raw substring). It **fails loudly**: missing or
unexpected columns, fixed-width length drift, unknown record-type codes,
trailer-count mismatch, and values that won't coerce each become a located
`ReadIssue`. In strict mode (default) all issues are collected and raised
together as `LayoutReadError`; non-strict callers read `ReadResult.errors`.

### Writing
`write()` is the inverse: it renders typed values, inverts the transform
pipeline (reverse order), and reassembles the layout (including header/trailer
records and a computed trailer count). For a layout using only invertible
transforms, `read(write(records)) == records`.

### Transforms (open question 1 & 2 resolved)
Transforms are **declarative and bidirectional** — a fixed registry of named,
parameterized steps, each with an `apply` (read) and `invert` (write):
`trim`, `pad`, `dateFormat`, `impliedDecimals`, `lookup`, `upper`, `lower`,
`replace`, `default`, `number`. Steps that cannot be reversed (`trim`, case
changes) invert as the identity and are documented as lossy.

For the long tail, a mapping may use an **expression escape hatch** (`expression`
for read, `writeExpression` for write) that reuses the existing expression DSL
(ADR-0002) with the raw cell bound to `value`. A read-only `expression` without a
`writeExpression` raises loudly on write rather than guessing. **No arbitrary
custom code is executed** — the escape hatch is the sandboxed DSL, keeping
layouts safe to author via AI or a UI and portable across the stack.

### Surface (this iteration)
Engine + loader + JSON schema + startup/reload wiring (`api/app.py`,
`mcp/bootstrap.py`) + tests. No new REST or MCP tools yet; those can layer on the
loaded `LayoutLoader` later.

## Consequences

**Easier**
- Flat-file integrations become configuration, not code, authored the same way
  by a human, a UI, or an AI agent.
- Provenance makes import review and error-queue triage precise (EN-020's
  "fail to the owner's queue").
- Bidirectional layouts let the same definition drive both import and export
  (MF-022's synthetic-data round-trips).

**More difficult / deferred**
- Transforms that are not reversible make `write` lossy; authors must supply a
  `writeExpression` (or accept identity) for those fields.
- Embedded newlines inside quoted delimited fields are not split specially; the
  reader assumes one physical line per record.
- No REST/MCP surface yet, so callers use the Python engine directly for now.

## Related ADRs
- [ADR-0002](0002-expression-language-dsl.md) — Expression Language DSL (reused by the escape hatch)
- [ADR-0011](0011-navigation-screen-metadata.md) — Navigation & Screen Metadata (loader pattern)
- [ADR-0013](0013-entity-design-sandbox.md) — Entity Design Sandbox (metadata-first authoring)
