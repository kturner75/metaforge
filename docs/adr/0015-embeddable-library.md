# ADR-0015: MetaForge as an Embeddable Library

## Status
Proposed

## Context

On 2026-10-09, MF-003 ("app separation") was rescoped. Instead of a framework that owns the app, MetaForge becomes an extension layer that a host application embeds. The first host is Engram, which owns its own database, authentication, campaigns, claims and provenance. Engram needs MetaForge only for typed schemas, validation rules, defaults, the expression DSL and file layouts.

[`docs/design/app-separation.md`](../design/app-separation.md) covers the owns-the-app path (project resolver, `metaforge.yaml`, system entity overlay, `metaforge serve`) and leaves embedding as an open question in its last section.

Today MetaForge cannot be embedded cleanly:

- **Heavy install.** `backend/pyproject.toml` pulls server dependencies into every install: sqlalchemy, psycopg, alembic, passlib, `bcrypt<4`, pyjwt, fastmcp, faker. The modules a host needs (`metaforge.metadata`, `metaforge.validation`, `metaforge.layouts`, `metaforge.core`) import none of them; they need only pyyaml and jsonschema.
- **Schemas missing from the wheel.** The JSON Schemas in `metadata/schemas/` are not declared as package data, so a git or wheel install drops them.
- **No database-free validation call.** `EntityLifecycle.prepare` is async, and `EntityLifecycleFactory` requires a `PersistenceAdapter`.
- **No field-reference helper.** Hosts that order rules or compute conditional requirements must reimplement an AST walk.
- **Fixed directory names.** `MetadataLoader` looks for `entities/` and `blocks/` under one root.

As a result Engram carries its own copies or stand-ins of the loader, expression evaluator, validation, layout reader, JSON Schemas and form field components, several already drifting from MetaForge.

## Decision

### 1. A light core
The core is `metaforge.metadata` (loader, validator), `metaforge.validation` (expressions, defaulting, validation services), `metaforge.layouts` and `metaforge.core`. Core dependencies are pyyaml and jsonschema only.

### 2. Server pieces behind an extra
The API, auth, persistence, migrations, MCP server, CLI server commands and fake data move behind `metaforge[server]`, imported lazily so `import metaforge.validation` never loads them.

### 3. Schemas ship as package data
The JSON Schemas are declared as setuptools package data.

### 4. A synchronous, database-free validation entry point
`validate_record(entity, record, operation, query=None)` applies defaults, auto fields and validation and returns the prepared record with its validation result. Validators that need data (uniqueness, exists) call the host's `query` callback, or are skipped with a warning when none is given. The async lifecycle stays for the server.

### 5. `referenced_fields(expression)`
Returns the field names an expression reads.

### 6. Explicit metadata directories
`MetadataLoader` accepts explicit entity and block directories, defaulting to today's layout.

### 7. Tagged releases
Releases are tagged; hosts pin a tag through a git URL with `#subdirectory=backend` until MetaForge is published.

## Alternatives Considered

- **Pin the package as it is.** Fastest start, but every host inherits the server stack and its pins (`bcrypt<4`, `fastmcp<3`), and the schemas are still missing from the wheel.
- **Vendor or git submodule.** No packaging work, but that is how Engram works today, with the drift it already shows.

## Consequences

### Positive
- A host gets typed rules, defaults and layouts without MetaForge's server stack.
- The core's public surface becomes explicit.
- The owns-the-app path in `app-separation.md` remains possible later, on top of the same core.

### Negative
- The core's public API must stay stable across tags.
- MetaForge's own tests and dev setup install `[server]`.

### Risks
- A lazy import missed in the CLI or API breaks `metaforge` commands without `[server]`; a test that imports the core with only core dependencies installed guards this.

## Related ADRs
- [ADR-0001](0001-validation-architecture.md) — Three-Layer Validation Architecture
- [ADR-0002](0002-expression-language-dsl.md) — Expression Language DSL
- [ADR-0003](0003-defaulting-lifecycle.md) — Entity Save Lifecycle with Defaulting
- [ADR-0014](0014-file-layout-metadata.md) — File-Layout Metadata
