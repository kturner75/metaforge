# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MetaForge is a metadata-driven full-stack framework for data-centric web applications (CRMs, admin panels, dashboards). Metadata in YAML is the single source of truth for entities, fields, validations, and UI behavior. See [docs/VISION.md](docs/VISION.md) for the full vision, architecture, and AI roadmap.

## Development Commands

### Backend (from `/backend`)
```bash
pip install -e ".[dev]"      # Install with dev dependencies
uvicorn metaforge.api:app --reload  # Run dev server on :8000
pytest                       # Run tests
pytest tests/test_foo.py -k test_name  # Run single test
ruff check src               # Lint
ruff format src              # Format
```

### Frontend (from `/frontend`)
```bash
npm install                  # Install dependencies
npm run dev                  # Run dev server on :5173
npm run build                # Production build
npm test                     # Run tests
npm run lint                 # Lint
```

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (SQLite for dev, PostgreSQL for prod)
- **Frontend**: React 18, TanStack Query, Vite, TypeScript
- **Metadata**: YAML files in `/metadata/` directory

## Architecture

### Metadata-Driven Design
- Entities defined in `/metadata/entities/*.yaml`
- Reusable blocks in `/metadata/blocks/*.yaml` (AuditTrail, AddressBlock, ContactInfo)
- Runtime user-saved views stored in database

### Rich Field Types
`text`, `name`, `description`, `email`, `phone`, `url`, `checkbox`, `picklist`, `multi_picklist`, `date`, `datetime`, `currency`, `percent`, `number`, `address`, `attachment`, `relation`

### API Pattern
- Generic query: `POST /query/{entity}` with fields, filter, sort, groupBy, aggregate
- Standard REST CRUD: `POST/GET/PUT/DELETE /entities/{entity}`

### Key React Components
- `<EntityGrid>` - Auto-generates columns/formatters/filters from metadata
- `<EntityForm>` - Create/edit with validation from metadata
- `<EntityDetail>` - Display entity details

## Design Goals
- Monolith-first for simplicity
- Framework handles 80-90% of CRUD/UI boilerplate
- End-users customize filters/views/dashboards without dev intervention
- AI-assisted entity/screen generation at dev-time

## Style Implementation Status

Each style belongs to a data pattern and is registered in `frontend/src/components/styles/index.ts`.
Cross-cutting features (contextFilter, compact mode) work across all implemented styles.

### Completed
| Pattern | Style | Component | YAML example |
|-----------|---------------|---------------|-------------------------------|
| query | grid | QueryGrid | contact-grid.yaml |
| query | card-list | CardList | contact-cards.yaml |
| query | search-list | SearchList | contact-search-list.yaml |
| query | kanban | KanbanBoard | contact-kanban.yaml |
| record | detail | RecordDetail | contact-detail.yaml |
| record | form | RecordForm | contact-form.yaml |
| aggregate | kpi-card | KpiCard | contact-count.yaml |
| aggregate | bar-chart | BarChart | contact-status-bar.yaml |
| aggregate | pie-chart | PieChart | contact-status-pie.yaml |
| aggregate | summary-grid | SummaryGrid | contact-status-summary.yaml |
| compose | detail-page | DetailPage | company-detail-page.yaml |
| compose | dashboard | Dashboard | contacts-dashboard.yaml |
| query | tree | TreeView | category-tree.yaml |
| query | calendar | CalendarView | contact-calendar.yaml |
| aggregate | time-series | TimeSeries | contact-created-timeseries.yaml |
| aggregate | funnel | Funnel | contact-status-funnel.yaml |

All 16 styles are implemented. The backend aggregate endpoint supports `dateTrunc` for time bucketing.
A Category entity with self-referential `parentId` was added for tree-view demonstration.

## Entity Lifecycle Hooks (ADR-0009)

Hooks provide extension points in the entity save/delete lifecycle for logic beyond defaults and validation.

### Hook Points
- **`beforeSave`**: After validation, before persist. Can modify record or abort.
- **`afterSave`**: After persist, same transaction. Can update related records or abort (rolls back).
- **`afterCommit`**: After commit, fire-and-forget. For notifications, external syncs.
- **`beforeDelete`**: Before delete. Can abort.

### Key Files
- `backend/src/metaforge/hooks/types.py` — `HookContext`, `HookResult`, `HookDefinition`
- `backend/src/metaforge/hooks/registry.py` — `HookRegistry` + `@hook` decorator
- `backend/src/metaforge/hooks/service.py` — `HookService` orchestration
- `backend/src/metaforge/hooks/__init__.py` — Public API, `register_builtin_hooks()`

### Declaring Hooks in Entity YAML
```yaml
hooks:
  beforeSave:
    - name: computeContractValue
      on: [create, update]
      when: 'amount > 0'
      description: "Recalculate total value"
```

### Registering Hook Implementations
```python
from metaforge.hooks import hook, HookContext, HookResult

@hook("computeContractValue")
async def compute_contract_value(ctx: HookContext) -> HookResult:
    return HookResult(update={"totalValue": computed_total})
```

## Navigation & Screens (ADR-0011)

Screens are defined in `metadata/screens/*.yaml` and are the routable entry points for the application.
Each screen has a `type` (entity, dashboard, admin, custom), navigation placement (`nav.section`, `nav.order`, `nav.icon`),
and optional view config references (`views.list`, `views.detail`, etc.).

- **Backend**: `ScreenConfigLoader` loads YAML, `GET /api/navigation` returns permission-filtered nav tree, `GET /api/screens/:slug` returns screen definition
- **Frontend**: `useNavigation()` hook drives the `Sidebar` (sections with icons), `useScreen()` provides screen config to `EntityCrudScreen`
- **Auto-generation**: Entities without screen YAML get default screens in an "Entities" section
- **Backward compatibility**: `routeConfig.ts` serves as final fallback for entity name resolution

## MCP Server

The MCP (Model Context Protocol) server exposes MetaForge's APIs to AI agents (Claude Desktop, etc.).
It calls the same services as the FastAPI app directly — no HTTP layer.

### Running
```bash
python -m metaforge.mcp                  # stdio transport (Claude Desktop)
python -m metaforge.mcp --transport sse  # SSE transport (web clients)
metaforge mcp                            # CLI entry point
```

### Claude Desktop Config
```json
{
  "mcpServers": {
    "metaforge": {
      "command": "python",
      "args": ["-m", "metaforge.mcp"],
      "cwd": "/path/to/metaforge/backend"
    }
  }
}
```

### Tools (12 total)
- **Discovery**: `list_entities`, `get_entity_metadata`
- **Read**: `query_records`, `get_record`, `aggregate_records`, `list_view_configs`, `get_view_config`
- **Write**: `create_record`, `update_record`, `delete_record`, `create_view_config`, `update_view_config`

### Key Files
- `backend/src/metaforge/mcp/bootstrap.py` — Service initialization
- `backend/src/metaforge/mcp/server.py` — FastMCP tool definitions
- `backend/src/metaforge/mcp/__main__.py` — Entry point
