# Separating an app from the MetaForge framework

**Status: Proposal.** Design note, not an accepted ADR. A separate app repository owns its metadata, database, and hooks, and depends on MetaForge as a library. The first consumer is a benefit-plan onboarding app, the POC for Engram, whose entities will be configured partly from uploaded documents. Companion proposal: [`docs/design/cursor-plugin.md`](cursor-plugin.md), a Cursor plugin (`.cursor-plugin/plugin.json`) bundling the existing MCP server, skills `author-entity`, `design-sandbox`, and `add-view-or-screen`, and `rules/entity-yaml.mdc`. This note is the app-root half of that proposal's "not an app dependency yet" prerequisite. Verified against `main` at `0c16367`.

## Where the coupling is

The backend is already a setuptools package (`backend/pyproject.toml` exposes the `metaforge` script), and the database URL is already configurable. Metadata, hooks, drafts, and migrations still assume this repository is the app.

Project root comes from the working directory: if `cwd.name == "backend"`, the parent is the root; otherwise cwd is. That rule is copied in `backend/src/metaforge/api/app.py` (lifespan), `backend/src/metaforge/mcp/bootstrap.py` (`initialize_services`), `backend/src/metaforge/cli/new_cmd.py`, and `backend/src/metaforge/cli/migrate_cmd.py`. Metadata is then `{root}/metadata`. `MetadataLoader` takes a path (`metadata/loader.py`); only the callers decide it. There is no metadata-path env var. The same root feeds:

- SQLite default `{root}/data/metaforge.db`, after `DATABASE_URL` and `METAFORGE_DB_PATH` (`persistence/config.py`).
- Draft SQLite `{root}/data/draft.db` (`persistence/draft.py`). ADR-0013 documents `METAFORGE_DRAFT_DB`; the code never reads it.
- Migrations in `{root}/migrations` (`cli/migrate_cmd.py`). `migrations/versions/0002_add_hq_state_to_company.py` is sample-app schema.
- Sandbox writes under `{root}/metadata/drafts` and `entities/`, plus optional docs in `{root}/docs/entities` (`sandbox/service.py`).

Hooks are names in entity YAML (`loader.py` `_resolve_hooks`) looked up in a process-global `HookRegistry`. `register_builtin_hooks()` is a no-op (`hooks/__init__.py`). The API calls it; MCP bootstrap does not. A missing implementation is logged and skipped (`hooks/service.py`). Coded validators match that shape: `ValidatorRegistry.register` is the app's job (`validation/registry.py`), and nothing imports an app module at startup.

The frontend never reads the metadata directory. `frontend/src/lib/api.ts` calls relative `/api/...`; Vite proxies that to port 8000 (`frontend/vite.config.ts`). `App.tsx` sends every slug through `EntityCrudScreen`. Sample-app leaks remain: `lib/routeConfig.ts` and the sidebar fallback hardcode Contact, Company, and Category, and `App.tsx` defaults the slug to `contacts`. `frontend/package.json` is `"private": true`. CORS allows only `http://localhost:5173` (`api/app.py`).

JSON Schemas sit next to the loader (`backend/src/metaforge/metadata/schemas/`). `pyproject.toml` has no package-data entry, so a wheel would drop the `.json` files until that is set. Auth entities are a separate gap: `auth/endpoints.py` loads `User` from the configured metadata directory, and screen auto-generation skips `User`, `Tenant`, and `TenantMembership` (`screens/endpoints.py`).

Layer 2 view and screen YAML loads from `{metadata}/views` and `{metadata}/screens` and is upserted into `_saved_configs` (`api/app.py` lifespan, `views/loader.py`). Layer 3 is rows in that table, resolved user → role → tenant → global (`views/store.py` `resolve`). ADR-0001 uses "layer 2/3" for validators; here it means ADR-0008 (YAML views vs saved configs). `METAFORGE_MCP_USER_ID`, `METAFORGE_MCP_TENANT_ID`, and `METAFORGE_MCP_ROLE` set who the agent is. They do not select the app.

## How an app points MetaForge at itself

One resolver, shared by the API lifespan, `initialize_services`, and the CLI:

1. `--project` on the CLI
2. `METAFORGE_HOME` (the app root)
3. `metaforge.yaml`, walking upward from cwd
4. Today's cwd heuristic, so this repo and its tests keep working until the sample moves

Env vars override single fields, so tests can keep setting `METAFORGE_DB_PATH` with no yaml file.

```yaml
# metaforge.yaml — app root
metadata: ./metadata        # entities, blocks, views, screens, drafts
database: sqlite:///./data/metaforge.db   # DATABASE_URL still wins
draftDatabase: sqlite:///./data/draft.db  # METAFORGE_DRAFT_DB
migrations: ./migrations
hooks: benefit_plans.hooks  # imported at startup; modules call @hook
validators: benefit_plans.validators
```

`METAFORGE_METADATA_DIR` overrides `metadata`. `METAFORGE_SECRET_KEY`, `METAFORGE_DISABLE_AUTH`, `METAFORGE_PORT`, and `METAFORGE_MCP_*` stay as they are. One process binds one app. Tools take no app id; a second app is a second process with a different `METAFORGE_HOME`.

## Packaging

| Approach | App repo contains | Upgrade |
|---|---|---|
| pip package + `metaforge new app` | `metaforge.yaml`, `metadata/`, a small hooks package, migrations, gitignored `data/` | Bump the dependency (git URL until PyPI) |
| Template repo | A copied starter, including glue | Merge from upstream; glue drifts |
| Git submodule | Framework source and app metadata | Submodule pointer; both trees sit in the agent workspace |

**Recommendation: pip package plus scaffold.** Agents configuring entities from uploaded documents should see the app repo, with framework behavior behind the installed package and the MCP tools. The first app depends on `metaforge @ git+https://github.com/kturner75/metaforge@<ref>` and does not wait on PyPI. `metaforge new app` writes the yaml, empty metadata directories, a hooks module, and a short README — the concrete form of the "Building an App with MetaForge" guide still open in `docs/tasks.md`. Write that guide against the scaffold, after it exists. A template repo can later be a clone of what the scaffold emits. A submodule puts framework source back in the agent workspace, which is the layout this proposal is leaving.

## Hooks, custom code, and Layer 2/3

App Python lives in the modules named by `hooks` and `validators`. API startup and MCP startup both import them, so `@hook(...)` and `ValidatorRegistry.register` run in both processes. Framework hooks stay in `register_builtin_hooks()`. Missing hook names keep warn-and-skip until an app turns on strict mode.

Layer 2 stays files in the app (`metadata/views`, `metadata/screens`). Layer 3 stays rows in the app database. A future "promote saved config to YAML" writes into that metadata directory, which the sandbox already does for entities.

[`docs/design/cursor-plugin.md`](cursor-plugin.md) ships `author-entity`, `design-sandbox`, and `add-view-or-screen`, plus `rules/entity-yaml.mdc` (`globs: metadata/**/*.yaml`). They call the sandbox and write YAML into the workspace `metadata/` tree, which under this proposal is the app's. `add-view-or-screen` writes the screen file `promote_entity` does not. The glob matches an app workspace as written; after the examples move it matches this repo only when the workspace is `examples/crm`, or the glob is widened. A benefit-plan skill that turns an uploaded document into entity YAML stays in the app (`.cursor/skills`) and calls the same sandbox tools. Marketplace plugins have to be open source, so that private schema stays out of the plugin whichever home the plugin note's open question picks (this repo, its own public repo, or a team marketplace).

System metadata ships in the wheel and merges underneath the app directory: `User`, `Tenant`, `TenantMembership`, and the blocks `AuditTrail`, `AddressBlock`, and `ContactInfo` (`metadata/blocks/`). Auth and `includes: [{block: AuditTrail}]` then work without copied files. An app file with the same name replaces the packaged one.

## Frontend

**The framework serves the shell.** Navigation comes from `GET /api/navigation`, and every route renders `EntityCrudScreen`. The benefit-plan admin UI can be that shell.

`metaforge serve` runs the API and, once `frontend/dist` is packaged, serves it on the same origin. Dev stays two processes: `npm run dev` from a framework checkout, `METAFORGE_HOME` pointed at the app, Vite proxy unchanged. The app repo has no `frontend/` copy. Publishing `@metaforge/ui` waits until a screen cannot be a registered style — the likely case is an Engram respondent interview, not the admin UI. Before then, `routeConfig.ts` and the `contacts` fallback should give way to navigation metadata so an app with no Contact entity still boots.

## How MCP, the sandbox, and the plugin find the app

They call the same resolver. The Cursor workspace is the app repo, so the upward walk finds that repo's `metaforge.yaml`. `initialize_services` already passes `base_path` into `SandboxService`, so drafts and promotes land in the app tree.

The plugin's `mcp.json` sketch launches `${workspaceFolder}/.venv/bin/python -m metaforge.mcp` and passes only `METAFORGE_MCP_USER_ID`, `METAFORGE_MCP_TENANT_ID`, and `METAFORGE_MCP_ROLE`. Those identity variables stay as sketched. The sketch assumes `metadata/` is at the workspace root, or the process starts in `backend/`, because the plugin reference does not document a stdio `cwd` and it is still open whether `${workspaceFolder}` expands inside a plugin `mcp.json`. Once the resolver exists, that same `env` block should set `METAFORGE_HOME` to `${workspaceFolder}` so the app root does not depend on an undocumented cwd. Until that lands, the plugin note's prerequisite stands. Running this framework checkout means `METAFORGE_HOME=examples/crm` (or a cwd inside that example). The walk does not search downward into `examples/`.

## What stays here

- The Python package (API, auth, validation, persistence, hook machinery, MCP, CLI, sandbox, schemas) and the React shell.
- Packaged system entities and the three shared blocks (`AuditTrail`, `AddressBlock`, `ContactInfo`).
- `examples/crm`: Contact, Company, Category, their views and screens, the root `migrations/` history, and the contact/category seed scripts. `scripts/seed_auth.py` becomes `metaforge seed-admin` against the system entities, because every app needs a login.
- `examples/pmads`: the nine unpromoted drafts in `metadata/drafts/` (Allotment, Mission, Organization, Program, ProgramAccountingLine, Project, Task, TaskAllotment, TreasuryAccount).

After that move the framework root has no `metadata/` and no app database. `docs/development.md` runs the CRM example through `METAFORGE_HOME`.

## Implementation plan

Each step is its own PR. This repo's layout keeps working through step 3.

1. **Shared resolver.** `metaforge.yaml` plus `METAFORGE_HOME`, `METAFORGE_METADATA_DIR`, and `METAFORGE_DRAFT_DB`. Point the API, MCP bootstrap, `new`, `migrate`, and `metadata validate` at it. No file means today's cwd heuristic.
2. **App import.** API and MCP import `hooks` and `validators` from the project file. MCP also calls `register_builtin_hooks()`.
3. **System overlay.** Ship User, Tenant, TenantMembership, and the three blocks (`AuditTrail`, `AddressBlock`, `ContactInfo`) in the wheel; merge them under the app directory.
4. **Examples.** Move the CRM sample and the PMADS drafts; point dev docs at `examples/crm`; route unknown slugs from navigation metadata alone.
5. **Scaffold and serve.** `metaforge new app` and `metaforge serve` (API and built shell, one origin). Declare the JSON Schemas as package data so a wheel still validates metadata.
6. **Guide and plugin env.** Write the Building an App guide against the scaffold (the plugin note's open prerequisite). Add `METAFORGE_HOME=${workspaceFolder}` to the plugin `mcp.json` sketch.

## Open questions

- May an app replace `User`, or only add fields through a documented extension? Auth endpoints assume today's shape.
- ADR-0013 also describes a Postgres `draft` schema. The code always uses a SQLite file. Keep SQLite drafts until a second database is actually required?
- Git-URL dependency until a second consumer, or publish to PyPI in the same step as `new app`?
- Strict missing-hook behavior as a project-file flag, defaulting to warn?
- The plugin's discovery question still gates step 6. If `${workspaceFolder}` does not expand in a plugin `mcp.json`, and stdio has no `cwd`, `METAFORGE_HOME` has to be set another way (a dashboard variable, or a `metaforge.yaml` the process cwd already walks up to).
