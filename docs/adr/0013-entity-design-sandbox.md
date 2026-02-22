# ADR-0013: AI-Assisted Entity Design Sandbox

## Status
Proposed

## Context

Designing a new data entity today involves too many disconnected handoffs:

1. Brainstorm with an AI (or team) in a chat session
2. Transcribe decisions to documentation (Confluence, Notion, etc.)
3. An engineer reads the docs, interprets them, and writes schema migrations
4. Another engineer builds forms and grids
5. QA or the product owner can finally *see* the entity for the first time — days or weeks later

Each handoff is lossy. Intent erodes. By the time you can visualize the data model, you've already committed to it in code and migrations.

MetaForge's architecture enables collapsing these steps. Since YAML is the single source of truth and the framework generates database schema, API endpoints, and full UI from that YAML automatically, there is no technical reason a developer needs to be in the loop between "design conversation" and "working application." The only missing piece is a **sandbox layer** that lets a design exist in a live, interactive state before it is formally committed.

### The Target Workflow

```
AI chat → draft entity YAML generated incrementally
        → fake data seeded automatically
        → full CRUD UI visible in running app (marked DRAFT)
        → iterate: add fields, rename, adjust validations
        → promote: YAML moves to entities/, migration runs, entity goes live
          or dismiss: draft deleted, no trace left
```

The brainstorm conversation *is* the design session. Its artifact *is* the metadata. No intermediate documentation step is required — though a reference doc can be auto-generated from the YAML on promote for teams that want it.

### What Is Already in Place

- YAML metadata loader that reads `metadata/entities/*.yaml` at startup
- MCP server with 12 tools covering read, write, and config operations
- Migration tooling (`metaforge migrate generate` + `apply`) that produces Alembic scripts from metadata changes
- Navigation auto-generation: entities without a screen YAML get default screens automatically
- Seed script pattern and `faker` available for generating realistic records

The design sandbox builds on all of these rather than replacing them.

## Decision

### Draft Entity Storage

Draft entity YAML files live in `metadata/drafts/` alongside `metadata/entities/`. The metadata loader scans both directories and sets `is_draft: true` on entities loaded from `drafts/`.

Draft entities are fully functional within the sandbox: they get database tables, API endpoints, and auto-generated navigation screens. The UI marks them clearly (e.g., a DRAFT badge in the sidebar and on the list/detail views) so there is no confusion with production entities.

### Draft Data Isolation

Draft entity tables are created in a separate SQLite database (`draft.db` by default, configurable via `METAFORGE_DRAFT_DB`). This ensures:
- Draft data is trivially discardable (delete the file)
- Production queries are never contaminated by draft records
- The production DB schema is not polluted with draft tables

When using PostgreSQL in production, draft tables live in a `draft` schema within the same server, keeping them isolated but inspectable.

### MCP Tools for the Design Loop

Five new MCP tools drive the conversational design workflow:

| Tool | Description |
|------|-------------|
| `draft_entity(yaml)` | Write a draft entity YAML to `metadata/drafts/`, create its table in the draft DB, hot-reload metadata |
| `update_draft_entity(name, changes)` | Patch an existing draft (add/remove/rename fields, update validations); alter draft table to match |
| `generate_fake_data(entity, count, locale)` | Seed `count` realistic records into the draft entity using `faker`, respecting field types and picklist values |
| `promote_entity(name, generate_doc)` | Move YAML from `drafts/` to `entities/`, run `migrate generate` + `apply` against production DB, delete draft data. If `generate_doc=true`, emit a Markdown reference doc. |
| `dismiss_entity(name)` | Delete YAML from `drafts/`, drop draft table, discard all draft data |

### Fake Data Generation

`generate_fake_data` uses the entity's field definitions to produce realistic values:

| Field type | Generator |
|------------|-----------|
| `name` | `faker.name()` |
| `email` | `faker.email()` |
| `phone` | `faker.phone_number()` |
| `text`, `description` | `faker.sentence()` / `faker.paragraph()` |
| `url` | `faker.url()` |
| `currency`, `number`, `percent` | Random within a reasonable range |
| `date`, `datetime` | Random within the past 2 years |
| `picklist` | Random choice from declared options |
| `multi_picklist` | Random subset of declared options |
| `relation` | Random record ID from target entity (draft or production) |
| `checkbox` | `faker.boolean()` |
| `address` | `faker.address()` components |

### Promote Flow

On `promote_entity("Deal")`:

1. Copy `metadata/drafts/deal.yaml` → `metadata/entities/deal.yaml`
2. Run `metaforge migrate generate --message "add Deal entity"` → produces Alembic script
3. Run `metaforge migrate apply` → creates table in production DB
4. Delete `metadata/drafts/deal.yaml`
5. Drop draft table from draft DB
6. Hot-reload metadata: entity is now live, DRAFT badge disappears
7. Optionally write `docs/entities/deal.md` — a Markdown reference doc auto-generated from the YAML (fields, types, validations, relations, picklist values)

### Documentation Artifact

When requested at promote time, the framework generates a Markdown reference doc from the entity YAML. This replaces the Confluence page in the traditional workflow — it is accurate by definition (generated from the same source as the running application), versioned in git alongside the YAML, and always up to date.

```markdown
# Deal

A sales opportunity in the pipeline.

## Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | name | yes | |
| stage | picklist | yes | Options: Prospecting, Qualifying, Proposal, Closed Won, Closed Lost |
| amount | currency | no | |
| closeDate | date | no | |
| contactId | relation → Contact | no | |
| companyId | relation → Company | no | |

## Validations
- `closeDate` must be in the future when `stage` is Prospecting or Qualifying
```

### UI Treatment of Draft Entities

Draft entities appear in the navigation sidebar under a "Drafts" section (or with a DRAFT badge inline, depending on preference). List, detail, create, and edit views all work identically to production entities. A dismissible banner at the top of draft entity screens makes the draft status explicit and provides Promote and Dismiss actions.

## Consequences

**Easier:**
- Data model design becomes interactive and visual from the first iteration
- AI chat conversations produce working, explorable applications rather than documents
- Mistakes are cheap: dismiss and restart with no migration cleanup required
- Documentation is generated, not written — always accurate
- Solo developers and small teams can ship new entities in a single session
- The MCP server becomes a design-time tool, not just a runtime data tool

**Harder / Watch For:**
- Draft DB must stay in sync with the draft YAML; schema drift if `update_draft_entity` partially fails requires careful error handling and rollback
- Hot-reload of metadata (adding/removing entities mid-session) needs the API server to re-scan without restart — requires a metadata reload endpoint or file-watch mechanism
- Fake data for `relation` fields depends on target entities having records; may need to generate related entities' data first
- Promote is not currently reversible (the migration would need to be rolled back manually); this is acceptable for an explicit intentional action but should be documented clearly
- Draft entities with the same name as a production entity must be rejected at draft-time

## Related ADRs

- ADR-0007: Agent Skills Architecture — skills are the user-facing AI interaction layer; design sandbox tools are a new skill category
- ADR-0009: Entity Lifecycle Hooks — hooks on draft entities work the same as production; promote does not carry draft hooks forward (they are part of the YAML)
- ADR-0012: Persistence & Migrations — promote flow reuses migration tooling directly
