# MetaForge Vision

## What MetaForge Is

MetaForge is a metadata-driven application framework for building data-centric web applications — CRMs, admin panels, financial systems, operational dashboards. It targets the 80-90% of enterprise software that is fundamentally about defining data structures, enforcing business rules, and presenting information in useful ways.

The core idea: **metadata is the single source of truth.** Entity definitions, field types, validation rules, default behaviors, UI presentation, and business logic are all expressed as structured metadata. The framework's backend and frontend components interpret this metadata at runtime, so adding a new entity or changing a business rule doesn't require writing new endpoints, new components, or new deployment pipelines.

## Why This Matters

Most enterprise application development follows the same pattern: define a data model, write CRUD endpoints, build forms and grids, add validation, wire up permissions, repeat for every entity. Frameworks reduce the boilerplate but don't eliminate the fundamental duplication — the same field definitions appear in the database schema, the API validation, the form layout, and the grid columns.

MetaForge eliminates this duplication. A field defined once in metadata is automatically understood by the database layer (schema, constraints), the API layer (validation, defaults, serialization), and the UI layer (form inputs, grid columns, display formatters, chart dimensions). Change the metadata, and every layer adapts.

But reducing boilerplate is just the foundation. The real payoff is what a metadata-driven architecture enables for AI.

## The AI-Native Advantage

Traditional AI-assisted development generates static code — a component, an endpoint, a migration script. The output requires human review, a build step, and a deploy cycle before users see the result. The AI is a developer tool.

MetaForge's architecture enables something fundamentally different: **AI configures live, interactive views by writing metadata — not code.** Because every UI component already knows how to render any valid metadata configuration, an AI can produce a fully functional dashboard, a filtered grid with drill-down, or a complex chart — complete with sorting, pagination, context filtering, and navigation — by writing a JSON object to an API endpoint. No build. No deploy. Instant.

This works because of three properties of the architecture:

1. **Components are metadata interpreters.** A `ConfiguredComponent` given a valid `ConfigBase` will resolve the right data pattern, fetch data, and render the appropriate presentation style. The AI doesn't need to know React — it needs to know the metadata schema.

2. **Metadata is just data.** View configurations are stored in the database alongside user data, scoped to users, roles, or tenants, and resolved via a precedence engine. An AI-authored configuration is a first-class citizen alongside developer-authored YAML and user-saved views.

3. **The metadata layer is a rich, constrained API surface.** Entity metadata provides field names, types, picklist values, relations, and validation rules. An AI with access to this context can construct valid queries and view configurations without hallucinating field names or invalid filter operators. The metadata acts as both documentation and guardrails.

The result: AI in MetaForge is not a code generation tool. It's an **application participant** that can understand the data model, reason about business rules, and create or modify live application behavior at runtime.

## Architecture

### The Layer Model

MetaForge organizes configuration into layers, each with a different authoring context and lifecycle:

**Layer 1 — Entity Metadata** (developer-authored, version-controlled)
- Entity definitions, field types, validation rules, defaults, relations
- Lives in `metadata/entities/*.yaml` and `metadata/blocks/*.yaml`
- Defines what data exists and how it behaves
- Changes require code review and deployment

**Layer 2 — View Configuration** (developer-authored, version-controlled)
- Pre-built views, dashboards, detail pages, navigation screens
- Lives in `metadata/views/*.yaml` (and future `metadata/screens/*.yaml`)
- Defines how data is presented and navigated
- Loaded at startup, seeded into the database as read-only configs

**Layer 3 — Runtime Configuration** (user/AI-authored, database-stored)
- Personalized views, saved filters, custom dashboards
- Stored in `_saved_configs` table with owner, scope, and tenant scoping
- Created via API at runtime — no deploy required
- Resolved via precedence: user > role > tenant > global (Layer 2)

**Layer 4 — AI-Driven Configuration** (planned)
- Agent skills that generate Layer 3 configs from natural language
- Business rule-aware data analysis and recommendations
- Composable agent workflows for multi-step processes
- Exposed via MCP (Model Context Protocol) for external agent access

Each layer builds on the one below. Layer 2 references Layer 1 schemas. Layer 3 overrides Layer 2 defaults. Layer 4 produces Layer 3 configs using Layer 1 context.

### Backend Architecture

The backend is a monolith-first Python/FastAPI application where metadata drives behavior:

- **Generic entity endpoints**: `POST/GET/PUT/DELETE /entities/{entity}` — no per-entity endpoint code
- **Flexible query endpoint**: `POST /query/{entity}` — dynamic filtering (12 operators), sorting, pagination, field selection
- **Aggregate endpoint**: `POST /aggregate/{entity}` — GROUP BY with count/sum/avg/min/max, date bucketing via `dateTrunc`
- **Validation pipeline**: Field constraints, canned validators, expression validators — all defined in metadata, executed automatically on create/update
- **Defaulting lifecycle**: Static defaults, computed defaults via expression DSL, auto-fields (timestamps, tenant ID) — metadata-driven, no custom code
- **Relation handling**: Display value hydration, referential integrity (restrict/cascade/setNull) — derived from metadata relation definitions
- **Row-level tenant isolation**: Automatic tenant filtering injected into every query for tenant-scoped entities
- **Views API**: Full CRUD on saved configs, precedence-based resolution, YAML config seeding

### Frontend Architecture

The frontend is a React/TypeScript application built around a single rendering primitive:

- **`ConfiguredComponent`**: Given a `ConfigBase`, resolves the style from the registry, fetches data via the appropriate hook (query/aggregate/record), merges style configuration, and renders. This single component can render any of the 16 implemented presentation styles.
- **Style registry**: Maps `(pattern, style)` pairs to presentation components. Adding a new visualization style requires one component file and one registration call — no framework changes.
- **Data hooks**: `useQueryData`, `useAggregateData`, `useRecordData` — shared data-fetching logic per data pattern, with sort/pagination state management and caching.
- **Style inference**: When creating or switching views, metadata-aware heuristics auto-populate style configuration (e.g., first `name` field becomes `titleField`, first `picklist` becomes `laneField`).
- **Context propagation**: Parent views pass `parentContext` to children, which automatically inject `contextFilter` conditions — enabling drill-down from dashboards to detail views without explicit wiring.

### Data Patterns and Presentation Styles

The framework separates **what data to fetch** (data pattern) from **how to render it** (presentation style). This means the same data configuration can be rendered as a grid, a kanban board, or a chart — and the same chart component can render any entity's aggregate data.

| Pattern | Backend | Presentation Styles |
|---------|---------|-------------------|
| **Query** | `POST /query/{entity}` | Grid, Card List, Search List, Kanban, Tree, Calendar |
| **Aggregate** | `POST /aggregate/{entity}` | KPI Card, Bar Chart, Pie Chart, Summary Grid, Time Series, Funnel |
| **Record** | `GET/PUT /entities/{entity}/{id}` | Detail View, Form |
| **Compose** | Orchestrates child components | Dashboard, Detail Page |

All 16 styles support the cross-cutting features that make embedded views powerful: `contextFilter` for parent-child data binding, `compact` mode for dense embedded rendering, and default row-click navigation for drill-down.

### Rich Field Type System

The field type system ensures that every layer of the application — persistence, validation, API serialization, form inputs, display formatters, grid columns — understands each field type natively:

`text`, `name`, `description`, `email`, `phone`, `url`, `checkbox`, `picklist`, `multi_picklist`, `date`, `datetime`, `currency`, `percent`, `number`, `address`, `attachment`, `relation`

Each type carries semantic meaning beyond its storage format. An `email` field gets format validation, a mailto: link in display mode, and an appropriate input in edit mode — all from the type declaration alone, with no per-field configuration.

### Authentication and Multi-Tenancy

- JWT-based authentication with access/refresh token lifecycle
- Role hierarchy: `readonly < user < manager < admin` with automatic permission inheritance
- Entity-level access control: read (all roles), create/update (user+), delete (manager+), global entity writes (admin only)
- Automatic tenant isolation: queries for tenant-scoped entities are transparently filtered by the authenticated user's active tenant
- View config scoping: saved configurations respect user/role/tenant/global precedence

## AI Capabilities Roadmap

### MCP Server — MetaForge as an AI-Accessible Platform

The first AI milestone: expose MetaForge's existing APIs as an MCP (Model Context Protocol) server, making the application's data and configuration accessible to any MCP-compatible AI agent.

**Tools an MCP server would expose:**
- `get_entity_metadata(entity)` — field names, types, picklist values, relations, validation rules
- `list_entities()` — all available entities and their descriptions
- `query_entity(entity, filter, sort, fields, limit)` — read data with full filter/sort support
- `aggregate_entity(entity, groupBy, measures, dateTrunc)` — summarize data
- `create_view_config(entity, pattern, style, dataConfig, styleConfig)` — create a live view
- `list_view_configs(entity)` — discover existing views
- `get_view_config(id)` — read a specific view's configuration

The metadata endpoint is the key enabler. When an agent calls `get_entity_metadata`, it receives the full schema — field names, types, valid picklist values, relation targets. This context lets the agent construct valid queries and configurations without hallucinating, because the metadata acts as both documentation and constraint.

**Two consumption modes:**
1. **External agents** (Claude Desktop, custom agent applications) connect to MetaForge's MCP server to query data and create views from outside the app
2. **Embedded agent** (in-app natural language interface) uses the same MCP tools internally, giving users a conversational interface within MetaForge itself

### AI-Driven Configuration — Agent Skills

Building on the MCP foundation, agent skills enable natural language interaction with MetaForge's configuration system:

- **"Show me contacts by status as a pie chart"** — the agent reads Contact metadata, constructs an aggregate config with `groupBy: [status]` and `style: pie-chart`, writes it to the views API, and the user sees an interactive chart instantly
- **"Add a column for email to this grid"** — the agent reads the current grid config, adds the column to `styleConfig.columns`, updates via the API
- **"Filter this to show only active contacts at Acme Corp"** — the agent constructs a filter condition using the correct field names and valid picklist values from metadata

These aren't generated code artifacts. They're runtime configurations that produce interactive views with full drill-down, sorting, pagination, and context filtering — because the framework's components already know how to render any valid configuration.

**Key properties of the skill system:**
- **Context-aware**: Skills receive entity metadata, current view state, and user permissions automatically
- **Schema-validated**: All AI output is validated against the configuration schemas before being applied
- **Scoped**: AI-created configurations can be personal, role-scoped, or promoted to team/global visibility
- **Reversible**: Configurations are versioned and can be rolled back or deleted
- **Promotable**: Proven Layer 3 configs can be graduated to Layer 2 YAML and checked into version control

### AI-Assisted Data Analysis — Rule-Aware Reasoning

Beyond configuring views, MetaForge's metadata layer enables AI agents to reason about data in the context of business rules.

**Example: Funding recommendations in a financial application.**

A user asks: *"Give me funding options for this task."* The agent:

1. Reads the entity metadata to understand the funding model (allotment types, fiscal year fields, expiration dates)
2. Reads business rules from metadata (which allotment types are eligible, FY constraints, expiration preferences)
3. Queries available allotments using the generic query endpoint with appropriate filters
4. Applies the prioritization rules (prefer expiring funds, match FY requirements)
5. Presents ranked recommendations with explanations

This is possible because MetaForge's metadata doesn't just describe data structures — it describes business semantics. Field types, validation rules, picklist values, and relation definitions give an AI agent enough context to reason about domain-specific questions, not just query data.

**Analysis capabilities, from near-term to ambitious:**
- **Data exploration**: "What's the distribution of contacts by status and company?" — aggregate query, materialized as a chart
- **Anomaly detection**: "Are there any contacts without companies?" — metadata-aware rule checking
- **Rule-based recommendations**: "What's the best funding source for this task?" — reasoning over domain rules against live data
- **Cross-entity analysis**: "Show me companies with more than 10 active contacts" — join-aware queries guided by relation metadata
- **External data integration**: Composing MetaForge's MCP tools with external data source MCP servers for cross-system analysis

### Composable Agent Workflows

The most ambitious AI capability: metadata-driven workflow orchestration that composes skills and agents into multi-step business processes.

**Mental model — three levels of composition:**

**Skills** (atomic operations): query data, create a view, evaluate rules, send a notification, update a record.

**Agents** (skill + reasoning bundles): A "Funding Agent" combines query + rule evaluation + recommendation. A "Dashboard Builder" combines metadata inspection + view creation. An "Approval Agent" checks conditions and routes decisions.

**Workflows** (agent orchestration): A "Fund a Task" workflow chains Funding Agent (recommend) → User (select) → Approval Agent (route) → System (apply). Each step is an agent invocation with defined inputs, outputs, and transition conditions.

**The metadata-driven pattern applies here too.** Just as entity definitions are metadata and view configurations are metadata, workflow definitions could be metadata:

```yaml
workflow:
  name: Fund Task
  trigger: manual
  steps:
    - agent: funding-recommender
      input: { taskId: "{{trigger.taskId}}" }
      output: recommendations
    - type: user-decision
      prompt: "Select a funding source"
      options: "{{steps.0.recommendations}}"
      output: selectedFunding
    - agent: approval-router
      input: { funding: "{{steps.1.selectedFunding}}" }
      output: approval
    - type: conditional
      condition: "{{steps.2.approval.approved}}"
      onTrue: apply-funding
      onFalse: notify-rejection
```

**Implementation approach:** Start concrete, generalize later. Build 2-3 real workflows as agent loops using existing tools (Claude Agent SDK + MetaForge MCP). Let the patterns for data flow, human-in-the-loop, and error handling emerge from real use cases. Then extract those patterns into a metadata-driven workflow definition schema.

This area is evolving rapidly in the broader AI ecosystem. MetaForge's advantage is that its metadata layer provides the structured context that makes agent workflows reliable rather than brittle — agents know what entities exist, what fields are valid, what rules apply, and what actions are possible.

## Design Principles

These principles guide architectural decisions across the framework:

1. **Metadata is the source of truth.** If something can be expressed as metadata rather than code, it should be. This maximizes what AI can configure and what users can customize without developer intervention.

2. **Components interpret, they don't hard-code.** UI components and backend handlers are generic interpreters of metadata. Adding a new entity should never require a new component or endpoint.

3. **AI configures, it doesn't generate.** The framework's value proposition for AI is live runtime configuration, not static code generation. AI output is data (metadata/config), not artifacts (source files).

4. **Sensible defaults, minimal configuration.** Style inference, auto-generated field renderers, and convention-over-configuration mean that a valid view can be created with just an entity name and a style — everything else has a reasonable default.

5. **Layers with clear precedence.** Developer YAML, tenant defaults, role preferences, and user personalizations coexist through a well-defined precedence model. Each layer can override the one below without modifying it.

6. **Monolith-first, interfaces for later.** Start simple (SQLite, single process, static routes) with clean interface boundaries (adapter protocols, style registry, config store) that enable decomposition when scale demands it.

7. **Open to the AI ecosystem.** MCP-first design means MetaForge is accessible to any AI agent, not locked to a specific LLM provider or agent framework. The same tools work for embedded and external agents.

## Current State and Roadmap

### Built and Working
- Entity metadata system (5 entities, 3 reusable blocks, 18 field types)
- Generic CRUD + query + aggregate API endpoints
- Expression DSL for validation rules and computed defaults
- 16 presentation styles across 4 data patterns
- Layer 2 (YAML) + Layer 3 (database) config pipeline with precedence resolution
- JWT auth, role hierarchy, multi-tenant isolation
- Config-driven rendering with style inference and context propagation
- Metadata-driven navigation — screens, sections, permission-aware sidebar
- MCP server — 12 tools exposing metadata, query, CRUD, and config APIs to external agents (FastMCP, stdio/SSE transports)

### Designed, Not Yet Built
- Agent skills framework (ADR-0007) — skill registry, context assembler, output verifier
- Structured config editor UI — view/edit saved configs without AI
- Drill-down context passing from summary views to detail views

### Planned
- Embedded AI agent for in-app natural language interaction
- AI-assisted data analysis with rule-aware reasoning
- Composable agent workflow definitions
- Config promotion (Layer 3 → Layer 2)
- PostgreSQL adapter for production deployments
