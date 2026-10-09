# Proposal: a Cursor plugin for MetaForge apps

**Status: proposal.** This note describes a plugin we have not built. It is not an ADR. No plugin manifest, skill, or rule is added with this file.

MetaForge already lets agents call the framework through an MCP server, and ADR-0007 already says agent output should be metadata. What is missing for authoring in Cursor is one installable package: that server, a few skills that know the design loop, and rules that keep entity YAML inside what the loader actually reads. Checked against Cursor's docs on 2026-10-09.

## What Cursor will load

Cursor has two plugin formats ([Plugins](https://cursor.com/docs/plugins), [plugins reference](https://cursor.com/docs/plugins/building)):

| Format | Manifest | Bundles |
| --- | --- | --- |
| Agent Plugins (open standard) | `plugin.json` at the plugin root | Skills and MCP servers |
| Cursor Plugins | `.cursor-plugin/plugin.json` | Those, plus rules, agents, commands, hooks, and variables |

This plugin needs rules, so it is a Cursor Plugin. `name` is the only required field (lowercase kebab-case). Discovery is conventional unless the manifest overrides it: `skills/<name>/SKILL.md`, `rules/*.mdc`, and a root `mcp.json`.

A skill is `skills/<name>/SKILL.md` with required frontmatter `name` (must match the folder) and `description` ([Agent Skills](https://cursor.com/docs/skills)). The agent applies it from the description, or the user invokes `/skill-name`. Plugin rules are `.mdc` files with `description`, `alwaysApply`, and `globs`; `alwaysApply: false` plus `globs` attaches the rule when a matching file is in context ([plugins reference](https://cursor.com/docs/plugins/building), [Rules](https://cursor.com/docs/rules)). Marketplace plugins come from a public Git repo and are reviewed manually. A local copy lives at `~/.cursor/plugins/local/<plugin>` and loads after a window reload.

## What it would bundle

### The existing MCP server

The server is FastMCP and calls the same services as the API, in-process. Launch it with `python -m metaforge.mcp` (stdio, the default), `python -m metaforge.mcp --transport sse`, or `metaforge mcp` (stdio or SSE only; `backend/src/metaforge/cli/mcp_cmd.py`). Cursor also documents streamable HTTP ([MCP](https://cursor.com/docs/mcp)); a local plugin should use stdio.

Seventeen tools are registered: `list_entities`, `get_entity_metadata`, `query_records`, `get_record`, `aggregate_records`, `list_view_configs`, `get_view_config`, `create_record`, `update_record`, `delete_record`, `create_view_config`, `update_view_config`, plus sandbox tools `draft_entity`, `update_draft_entity`, `generate_fake_data`, `promote_entity`, and `dismiss_entity`.

`initialize_services` (`backend/src/metaforge/mcp/bootstrap.py`) takes the process cwd as the project root, or the parent when cwd is named `backend`, and loads `{root}/metadata`. Optional identity env vars are `METAFORGE_MCP_USER_ID`, `METAFORGE_MCP_TENANT_ID`, and `METAFORGE_MCP_ROLE`. The database is `DATABASE_URL`, else `METAFORGE_DB_PATH`, else SQLite.

Cursor stdio config is `command`, `args`, and `env`, with `${workspaceFolder}` and `${env:NAME}` ([MCP](https://cursor.com/docs/mcp)). A plugin can also declare dashboard variables as `${VAR}`. Cursor does not expand the agent-plugins `${PLUGIN_ROOT}` variable; use `${CURSOR_PLUGIN_ROOT}` ([Plugins](https://cursor.com/docs/plugins)). Sketch only:

```json
{
  "mcpServers": {
    "metaforge": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "metaforge.mcp"],
      "env": {
        "METAFORGE_MCP_USER_ID": "${METAFORGE_MCP_USER_ID}",
        "METAFORGE_MCP_TENANT_ID": "${METAFORGE_MCP_TENANT_ID}",
        "METAFORGE_MCP_ROLE": "${METAFORGE_MCP_ROLE}"
      }
    }
  }
}
```

### Skills to write first

ADR-0007's executor is unbuilt (`docs/tasks.md`). A Cursor skill is instructions plus the tools above, which is the dev-time slice of that catalog. Three skills, in order:

1. **`author-entity`** — entity YAML the loader and the JSON Schema both accept (`abbreviation`, `id` primary key, `includes`, `relation` fields, `{value, label}` options, `defaults` expressions, `hooks`). This is ADR-0007's `create-entity`, `add-field`, and `add-relation` as one skill. The loader ignores a field `calculated` key and an entity `lifecycle` block; the skill's job is to stop emitting them.
2. **`design-sandbox`** — the ADR-0013 loop: `draft_entity`, `generate_fake_data`, `update_draft_entity`, then `promote_entity` or `dismiss_entity`. Seed relation targets first.
3. **`add-view-or-screen`** — view YAML (`pattern`, `style`, `data`) and a screen YAML. Promote does not write a screen. This is ADR-0007's `configure-view` plus ADR-0011, which that catalog does not name.

Hold the rest of the ADR-0007 catalog (`create-filter`, `create-chart`, `configure-dashboard`, `switch-style`, `add-validation-rule`, `add-default`). Validation and defaults come next: the expression DSL is easy to get wrong, and `metaforge metadata validate` is already the check.

### One YAML rule

`rules/entity-yaml.mdc` with `alwaysApply: false` and `globs: metadata/**/*.yaml`. State the loader contract (types from `core/types.py`, relations as fields, defaults as expressions, hook points `beforeSave`, `afterSave`, `afterCommit`, `beforeDelete`). Call out keys the field schema allows (`additionalProperties: true`) that `_resolve_field` drops: `calculated` (still on `latLong` in `metadata/blocks/address.yaml`), per-field `ui` (`FieldDefinition.ui` stays the default; YAML never fills it), and `description` (also on the entity schema, and absent from `EntityModel` and `FieldDefinition`). An entity `lifecycle` block fails the entity schema (`additionalProperties: false`) and the loader ignores it too. Point at `metadata/entities/contact.yaml` instead of pasting a second schema.

## ADR-0007, and whether a new ADR is warranted

ADR-0007's skill takes natural language plus metadata context and returns verified configuration, as YAML or a Layer 3 row. Its registry, context assembler, verifier, and LLM adapter are unbuilt. This plugin uses the Cursor agent as the model, the skill file as the procedure, and MCP as the read/write path. `draft_entity` and `metaforge metadata validate` are the checks. That is the dev-time half only. Runtime filters, Layer 3 promotion, and the structured editor stay accepted and unimplemented, so ADR-0007 remains the runtime decision.

A new ADR is warranted once this proposal is accepted, and not before. It would record that dev-time skills ship as a Cursor plugin rather than the framework-owned executor ADR-0007 assumed. Number it ADR-0014, status Proposed, only after the questions below are settled. Writing it now would freeze packaging choices that are still open.

## Prerequisite fixes

- **fastmcp.** `pyproject.toml` pins `fastmcp>=2.0.0,<3.0.0` (commit `1acd555`) because `tests/test_mcp_server.py` and `tests/test_mcp_sandbox.py` use `.fn` on the 2.x `FunctionTool`. 3.x removed `.fn`. `uv.lock` (from `0ecd2c4`) still locks 3.2.0 at `>=2.0.0` with no upper bound, so `pip install` and `uv sync` disagree. PyPI's current release on 2026-10-09 is 4.1.0. Port the tests and regenerate the lock before raising the pin (`docs/tasks.md`).
- **Not an app dependency yet.** The "Building an App with MetaForge" guide is still open. A plugin in another repo works when `metaforge` imports from the `mcp.json` interpreter and `metadata/` is at the workspace root, or the process starts in `backend/`.
- **Rules must follow the loader.** `description` and per-field `ui` validate, then disappear at load time.

## Open questions

- Does `${workspaceFolder}` resolve inside a plugin `mcp.json`? The plugin reference shows `${VAR}` and `${CURSOR_PLUGIN_ROOT}`, and it does not document a stdio `cwd`. Metadata root is the process cwd.
- Where does the plugin live: its own repo with `.cursor-plugin/marketplace.json`, a directory in this repo, or a team marketplace only? Marketplace plugins are reviewed and must be open source ([Plugins](https://cursor.com/docs/plugins)).
- Ship the YAML rule only inside the plugin, or also as `.cursor/rules` in this repo for people working on the framework?
- Is v1 local stdio only? SSE exists; streamable HTTP is what Cursor documents for remote servers, and a cloud agent cannot use a stdio process on a laptop.
- After the first three skills, do validation and defaults stay Cursor skills, or wait for ADR-0007's verifier?

## Sources

- [Plugins](https://cursor.com/docs/plugins), [plugins reference](https://cursor.com/docs/plugins/building), [Agent Skills](https://cursor.com/docs/skills), [Rules](https://cursor.com/docs/rules), [MCP](https://cursor.com/docs/mcp)
- ADR-0007, ADR-0011, and ADR-0013 in `docs/adr/`
