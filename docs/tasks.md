# Metaforge Tasks

Living task list for the metadata-driven framework. Add new items anywhere.

## Working Agreement
- Keep one feature "In Progress" at a time.
- Add new ideas to the Inbox, then triage into the right section.
- When a feature is done, move it to Completed and summarize key outcomes.

## Inbox (Triage Needed)

## Design Decisions (Captured)

### Entity Overview / Detail Page (Compose Pattern)
**Approach: Option A — extend existing styles, no purpose-built child components.**

Child/embedded views reuse existing styles (grid, card-list, kanban, kpi-card, bar-chart, etc.) with these cross-cutting additions to DataConfig/StyleConfig:

1. **`contextFilter`** in DataConfig — a filter field that binds to parent record ID at render time (e.g., `companyId` auto-filtered by parent)
2. **`compact` flag** in StyleConfig — rendering hint for denser display (fewer rows, smaller height, "View All" overflow). Driven by the slot, not the component.
3. **`actionMode`** in StyleConfig — how "New" works in embedded context: `modal` | `inline` | `navigate`

**Tab modes for entity overview screen:**
- `tabMode: full` — vertical tab bar, selected tab fills available space, child components render at full size (`compact: false`)
- `tabMode: inline` — horizontal tabs within a section (below record header), child components render compact (`compact: true`)

The tab mode is a property of the overview screen layout, not the child config. The same `company-contacts-grid` config works in either mode — the slot determines compact vs. full.

**Example detail page config:**
```yaml
pattern: compose
style: detailPage
data:
  entityName: Company
styleConfig:
  headerFields: [name, industry, website]
  tabMode: full       # full | inline
  tabs:
    - label: Contacts
      componentConfig: "yaml:company-contacts-grid"
    - label: Deals
      componentConfig: "yaml:company-deals-grid"
```

**Example child config (referenced by tab):**
```yaml
view:
  name: Company Contacts
  entityName: Contact
  pattern: query
  style: grid
  data:
    contextFilter:
      field: companyId
    pageSize: 5
  styleConfig:
    columns: [fullName, email, phone, status]
    showActions: true
    actionMode: modal
```

## Metadata Core (Source of Truth)
- [ ] Define metadata schema versioning strategy
- [x] Add JSON Schema validation for `metadata/` YAML files — 5 JSON Schemas (`_defs`, entity, block, view, screen) using Draft 2020-12 with cross-schema `$ref` via `referencing` registry; `metadata/validator.py` public API (`validate_yaml_file`, `validate_metadata_dir`) with PyYAML `on:` bool-key preprocessing; `metaforge metadata validate` CLI enhanced with `--strict` and `--path` flags; startup validation in `api/app.py` lifespan (warns but doesn't block); 35 tests in `test_metadata_validator.py`
- [ ] Add metadata migration mechanism (handle schema changes across versions)
- [ ] Build CLI scaffolding for new entities/fields (`metaforge new entity Foo`)

## Backend Entity Framework
- [x] Hook system (pre/post save, validation, transform callbacks) — ADR-0009 implemented: `HookRegistry`, `HookService`, `HookContext`/`HookResult` types, `@hook` decorator, metadata-declared hooks with `on:`/`when:` filtering, 4 hook points (beforeSave, afterSave, afterCommit, beforeDelete), transaction management (`create_no_commit`/`update_no_commit`/`delete_no_commit`/`commit`/`rollback`), wired into all CRUD endpoints
- [ ] Relationship handling enhancements (many-to-many via junction entities)

## Backend API Layer
- [ ] Bulk operations (create/update/delete)
- [ ] OpenAPI schema generation from metadata
- [x] Aggregate endpoint: `POST /api/aggregate/{entity}` with groupBy, measures (count/sum/avg/min/max), filter

## Frontend Entity Framework
- [x] Register remaining field types in field registry (date, datetime, currency, percent, number, checkbox, url, address, attachment, multi_picklist, description)
- [x] Wire server-side validation errors into form UI (backend returns 422, form needs to display)
- [x] Warning acknowledgment flow UI (backend token system works, frontend auto-acknowledges for now — needs dialog + user choice)
- [x] Client-side validation mirroring backend rules (beyond required check)
- [x] Relationship UI improvements: display value hydration in grids, searchable typeahead picker
- [ ] Localization hooks for labels/help text

## Shared Validation + Rules
- [ ] Sync backend <-> frontend validation rules (shared rule definitions)
- [ ] Shared error codes/messages mapping

## Persistence & Migrations
- [x] Set up Alembic for migration management — `cli/migrate_cmd.py` with `init`, `generate`, `apply`, `rollback`, `stamp`, `status` commands; programmatic Alembic runner in `migrations/runner.py`; no static `alembic.ini` required
- [x] Migration diff tool (metadata changes -> SQL migration) — snapshot-based diff engine in `migrations/diff.py` + `snapshot.py`; detects new/removed entities and fields, type changes, NOT NULL constraint changes; generates Alembic-compatible `.py` files; 71 tests covering all paths
- [x] PostgreSQL adapter — `PostgreSQLAdapter` using psycopg v3; `SequenceService` dialect param (`INSERT … ON CONFLICT DO UPDATE`); `SavedConfigStore` refactored to SQLAlchemy Core (dialect-neutral URL-based); wired in `create_adapter()`, `api/app.py`, `mcp/bootstrap.py`; 5 protocol conformance tests always run + 12 live CRUD tests skip without `DATABASE_URL=postgresql://…`
- [ ] SQLite dev / Postgres prod parity checks

## Auth & Permissions
- [ ] Role/permission model in metadata (declarative per-entity access)
- [ ] Row-level access policies
- [ ] Field-level access policies (hide/redact fields by role)
- [ ] Admin UI for managing roles and permissions

## UI Component Configuration (ADR-0008)

### Foundation
- [x] Implement `saved_configs` table (pattern, style, data_config, style_config columns) and CRUD API
- [x] Config resolution engine (user → role → tenant → global precedence)
- [x] Config YAML loader: load dev-authored view configs from `metadata/views/`
- [x] Shared data layer: Query pattern hook (filters, sort, pagination, caching)
- [x] Shared data layer: Aggregate pattern hook (groupBy, measures) — `useAggregateData` calls `POST /api/aggregate/{entity}`
- [x] Presentation style registry (register style name → component + styleConfig schema)
- [x] Style-swap logic: switch presentation keeping data config intact, infer default styleConfig
- [x] Config-driven rendering: `ConfiguredComponent` resolves config → style → data → render
- [x] End-to-end integration: Classic/Config-Driven toggle in ContactsApp

### Query Pattern Styles
- [x] Grid style: columns, sortable/filterable, selectable, inline edit — `QueryGrid` component
- [x] Card List style: title/subtitle/detail fields, CSS grid layout, status badge — `CardList` component
- [x] Search List style: filterable fields, search fields, display fields — `SearchList` component with client-side text search
- [x] Tree style: parentField, expand/collapse, detailFields, indentPx — `TreeView` component with client-side tree building, Expand All/Collapse All toolbar, compact mode
- [x] Kanban style: laneField, card layout (read-only; drag-to-update deferred) — `KanbanBoard` component groups by picklist lanes
- [x] Calendar style: dateField, titleField, month navigation, event display — `CalendarView` component with 7-column CSS grid, today highlighting, compact dot mode

### Aggregate Pattern Styles
- [x] Summary Grid style: grouped aggregates with totals row — `SummaryGrid` component with HTML table + totals row
- [x] Bar Chart style: dimension + measures, stacked/grouped, orientation — `BarChart` SVG component, vertical/horizontal
- [x] Pie Chart style: dimension + measure, labels, donut variant — `PieChart` SVG component with legend, donut mode
- [x] Time Series style: timeField, measureField, line/area chartType, dateTrunc bucketing — `TimeSeries` SVG component with gridlines, smart label stepping, backend strftime support
- [x] KPI Card style: single measure display — `KpiCard` component with formatted value, icon, label
- [x] Funnel style: stageField, measureField, stageOrder, conversion percentages — `Funnel` SVG component with centered bars, percentage of top stage, compact mode

### Record Pattern Styles
- [x] Form style: field ordering, sections, collapsible groups — `RecordForm` component with configurable sections, collapsible chevron, client+server validation
- [x] Detail style: read-only display with sections — `RecordDetail` component + `useRecordData` hook + record pattern in `ConfiguredComponent`

### Compose Pattern Styles
- [x] Detail Page style: record header + tabbed related components — `DetailPage` compose component with `ComposeProps`, `TabPanel` inner component, vertical/inline tab modes, `contextFilter` parent-to-child propagation
- [x] Dashboard style: CSS grid of panels, each a `ConfiguredComponent` — `Dashboard` compose component, replaces hardcoded `DashboardSection`, config-driven via YAML
- [x] Context propagation: `parentContext={{ recordId }}` flows to child `ConfiguredComponent`, injects `contextFilter` as `eq` condition on foreign-key field

### Cross-Cutting
- [x] DrillDown: context-passing from summary views to detail views — clicking bar/pie/funnel chart segments navigates to the entity list pre-filtered by that dimension; dismissible filter badge shown in list view; location state preserves clean URLs
- [ ] Structured config editor UI (view/edit saved configs without AI)

## Agent Skills (ADR-0007)
- [ ] Skill registry and definition schema
- [ ] Context assembler (gathers entity metadata, view context, permissions for skills)
- [ ] Output verifier (schema validation, expression parsing, field existence checks)
- [ ] Skill executor: route verified output to YAML (dev-time) or Layer 3 (runtime)
- [ ] LLM integration layer (thin adapter: context + intent → structured output)
- [ ] Core skills: `create-filter`, `configure-view`, `create-chart`, `configure-dashboard`, `switch-style`
- [ ] Core skills: `add-validation-rule`, `add-default`, `create-entity`, `add-field`
- [ ] Skill composability: plan decomposition and sequential execution
- [ ] Hybrid interaction UI: NL input → structured editor → verify → apply
- [ ] Config promotion: move Layer 3 configs to YAML (graduate to code)
- [ ] Scoping UX: personal / team / role / global with permission checks

## DX / Tooling
- [ ] CLI scaffolding for new entities/fields (`metaforge new entity Foo`)
- [ ] Metadata editor (basic UI for editing YAML)
- [ ] Dev server watch for metadata changes (auto-reload on YAML edit)
- [ ] Test fixtures generated from metadata

## Testing
- [ ] Frontend component tests for core field types
- [ ] E2E flows for CRUD on a sample entity

## Documentation
- [ ] "Getting Started" guide
- [ ] Metadata reference doc (field types, validation rules, defaults, blocks)
- [ ] Field type catalog with examples
- [ ] API usage examples

---

## Completed

### Metadata Core
- [x] YAML metadata loader with entity + block resolution — `metadata/loader.py` loads entities from `metadata/entities/`, expands reusable blocks from `metadata/blocks/`, validates abbreviation uniqueness
- [x] 5 entities defined: User, Tenant, TenantMembership, Contact, Company
- [x] 3 reusable blocks: AuditTrail, Address, ContactInfo
- [x] Rich field type system: id, text, name, description, email, phone, url, checkbox, picklist, multi_picklist, date, datetime, currency, percent, number, address, attachment, relation

### Backend Entity Framework
- [x] Entity registry loading from metadata — MetadataLoader parses YAML, creates EntityModel/FieldDefinition dataclasses
- [x] Field constraint system (required, unique, min/max, minLength/maxLength, pattern, format validation) — `validators/field_constraints.py`
- [x] Three-layer validation architecture (ADR-0001): field constraints, canned validators, expression validators, tenant-scoped DB validators
- [x] Canned validators: `unique`, `dateRange`, `conditionalRequired`, `fieldComparison`, `immutable`, `referenceExists`, `referenceActive`, `noActiveChildren`
- [x] Expression language DSL (ADR-0002): lexer, parser, evaluator with arithmetic/comparison/logical ops and built-in functions (`concat`, `now`, `exists`, `count`, `lookup`, etc.)
- [x] Validation pipeline with consistent error structure — `ValidationService` runs all layers in parallel, returns typed `ValidationResult` with errors/warnings
- [x] Defaulting lifecycle (ADR-0003): static defaults, computed defaults via expressions, auto-fields (createdAt/updatedAt/createdBy/updatedBy/tenantId), conditional defaults with `when:` expressions
- [x] Warning acknowledgment flow (ADR-0004): token-based, prevents submitting stale data
- [x] Message interpolation (ADR-0005): `{fieldName}`, `{fieldName:raw}`, `{fieldName:label}`, `{original.fieldName}` placeholders in error messages
- [x] Entity scoping: global vs tenant (ADR-0006)
- [x] Persistence mapping (metadata -> SQL schema) — `SQLiteAdapter.initialize_entity()` creates tables from metadata
- [x] CRUD service layer — full create/get/update/delete on SQLiteAdapter with sequence-based ID generation
- [x] Relation handling (one-to-many): display value hydration, onDelete (restrict/cascade/setNull)

### Backend API Layer
- [x] CRUD endpoints: `POST/GET/PUT/DELETE /api/entities/{entity}` with full lifecycle (defaults + validation + persistence)
- [x] Query endpoint: `POST /api/query/{entity}` with filter/sort/paginate
- [x] Metadata endpoints: `GET /api/metadata`, `GET /api/metadata/{entity}`
- [x] Validation error format: 422 with `{valid, errors[], warnings[]}` structure
- [x] Auth/permissions integration into entity access — middleware extracts JWT, `can_access_entity()` enforces role-based access per operation
- [x] Automatic tenant filtering on queries for tenant-scoped entities

### Frontend Entity Framework
- [x] Metadata loader + cache — `useEntityMetadata` hook with TanStack Query (staleTime: Infinity)
- [x] Field renderer system by type — `FieldRenderer` + `fieldRegistry` dispatches to type-specific components
- [x] 6 field components: Text, TextInput, TextArea, Select, Badge, RelationSelect
- [x] Form generation from metadata — `EntityForm` renders editable fields, handles required validation
- [x] Grid/table view from metadata — `EntityGrid` with sorting, pagination, clickable rows
- [x] CRUD hooks: `useCreateEntity`, `useUpdateEntity`, `useDeleteEntity`, `useEntity`, `useEntityQuery`
- [x] Auth hooks: `useAuth` (login/logout/token management), `useAuthMe` (current user info)
- [x] Login screen UI

### Persistence
- [x] SQLite adapter with full CRUD, query, filtering (eq/neq/gt/gte/lt/lte/in/notIn/contains/startsWith/isNull/isNotNull/between)
- [x] Sequence-based ID generation with tenant scoping — `SequenceService`
- [x] Relation hydration (batch lookup of display values for foreign keys)

### Auth & Permissions
- [x] JWT auth: access tokens (15min), refresh tokens (7d), password reset tokens
- [x] Password hashing with bcrypt
- [x] Auth endpoints: login, register, refresh, /me, change-password, reset-password (request + confirm)
- [x] Role hierarchy: readonly < user < manager < admin
- [x] Entity-level permission enforcement: read (all), create/update (user+), delete (manager+), global entity writes (admin)
- [x] Multi-tenant support: tenant membership model, tenant switching on refresh

### UI Component Configuration (ADR-0008 Foundation)
- [x] Backend `views` package: `types.py` (DataPattern, OwnerType, ConfigScope, ConfigSource enums + SavedConfig dataclass), `store.py` (SavedConfigStore with `_saved_configs` system table, CRUD, filtered list, precedence-based resolve, YAML upsert), `loader.py` (ViewConfigLoader reads `metadata/views/*.yaml` with `yaml:{stem}` ID convention), `endpoints.py` (REST API at `/api/views/` — list, get, create, update, delete, resolve; YAML configs are read-only)
- [x] Wired into app lifespan: SavedConfigStore + ViewConfigLoader initialized after DB connect, YAML configs seeded on startup, views router included
- [x] Sample YAML view config: `metadata/views/contact-grid.yaml` (Contact entity, query/grid, 5 columns, sort by fullName, pageSize 25)
- [x] Backend tests: 59 tests across 3 files — `test_saved_config_store.py` (30 tests: CRUD, filtering, precedence resolution, YAML upsert), `test_view_loader.py` (11 tests: YAML parsing, edge cases), `test_views_api.py` (18 tests: full API integration)
- [x] Frontend types + registry: `viewTypes.ts` (DataPattern, DataConfig, ConfigBase, PresentationProps, StyleRegistration), `styleRegistry.ts` (Map-based registry with register/get/fallback/list)
- [x] QueryGrid presentation component: `components/styles/QueryGrid.tsx` — table renderer driven by `PresentationProps<GridStyleConfig>`, supports styleConfig.columns for column order/visibility/pinning
- [x] Style registration: `components/styles/index.ts` registers `query/grid`, imported in `main.tsx` before App renders
- [x] Shared data hooks: `useQueryData` (composes useEntityMetadata + useEntityQuery with sort/pagination state), `useAggregateData` (stub)
- [x] Config API hooks: `useViewConfig.ts` — `useSavedConfig`, `useSavedConfigs`, `useResolvedConfig`, `useCreateConfig`, `useUpdateConfig`, `useDeleteConfig`
- [x] ConfiguredComponent: resolves style from registry, fetches data via pattern-appropriate hook, merges default + saved styleConfig, renders
- [x] Phase C integration: Classic/Config-Driven toggle in ContactsApp — both paths render same contact grid data, proving full stack end-to-end

### Testing
- [x] Backend unit tests: expressions (parser/evaluator), validators (all canned types), field constraints (required/format/bounds/pattern/picklist), defaulting service, message interpolation, sequences
- [x] Backend views tests: saved config store (30), view loader (11), views API integration (18) — 59 new tests, 315 total
- [x] API integration tests: CRUD lifecycle, validation errors, warning acknowledgment flow
- [x] Aggregate endpoint tests: 7 tests (count, groupBy, filter, 404, empty, invalid function, no measures) — 322 total

### Frontend Build
- [x] Clean TypeScript build: fixed unused imports (EntityForm, Text), type narrowing (RelationSelect), HeadersInit typing (api.ts)

### UI Component Configuration (ADR-0008 Phase D)
- [x] Backend aggregate endpoint: `POST /api/aggregate/{entity}` — `SQLiteAdapter.aggregate()` method with GROUP BY + count/sum/avg/min/max, field validation, filter reuse; endpoint in `app.py` with auth + tenant filtering
- [x] Frontend aggregate data hook: replaced `useAggregateData` stub with real implementation calling backend; added `useAggregateQuery` to `useApi.ts`; adapts `AggregateResult` into `QueryResult` shape for `PresentationProps` compatibility
- [x] CardList presentation component: `components/styles/CardList.tsx` — CSS grid of cards with configurable title/subtitle/detail fields, status badge via FieldRenderer, pagination footer; registered as `query/card-list`
- [x] KpiCard presentation component: `components/styles/KpiCard.tsx` — single aggregate value display with icon, label, number/percent/currency formatting; registered as `aggregate/kpi-card`
- [x] Style selector: dropdown in App.tsx to swap between Data Grid and Card List in config-driven mode; KPI summary section below main view
- [x] YAML view configs: `metadata/views/contact-cards.yaml` (card list), `metadata/views/contact-count.yaml` (KPI total contacts)

### Frontend Bug Fixes
- [x] Fixed `useCreateEntity` / `useUpdateEntity` not wrapping payload in `{data: ...}` — backend `CreateRequest`/`UpdateRequest` Pydantic models require `data` key
- [x] Fixed warning acknowledgment: mutations now auto-acknowledge backend 202 responses by resubmitting with the `acknowledgmentToken` — records are now persisted correctly

### Frontend Field Types
- [x] 10 new field components: Checkbox, NumberInput, CurrencyInput, DatePicker, DateTimePicker, DateDisplay, NumberDisplay, BooleanBadge, UrlLink, MultiPicklistBadges
- [x] 16 field types registered in frontend field registry (up from 8): uuid, string, name, text, description, email, phone, url, picklist, multi_picklist, relation, date, datetime, number, currency, percent, boolean, checkbox, address, attachment
- [x] 7 new backend field types added: description, url, multi_picklist, checkbox, percent, address, attachment (21 total)
- [x] FieldRenderer updated: `mode='multi'` for multi_picklist fields

### Server-Side Validation in Form UI
- [x] `ApiError` extended with structured `validation` property (errors[], warnings[] with field/message/code/severity)
- [x] `fetchJson` preserves 422 response body as `ValidationErrorBody` on `ApiError`
- [x] `EntityForm` accepts `serverErrors` prop, merges with client-side errors per field, shows general error banners for non-field errors
- [x] `App.tsx` catches mutation errors, extracts validation body, passes to form; clears on cancel/navigate

### Warning Acknowledgment Dialog (ADR-0004 Frontend)
- [x] Mutations return discriminated `SaveResult` type: `{ saved: true, data }` or `{ saved: false, pendingWarnings }` — no more auto-acknowledge
- [x] `PendingWarnings` type exported: `{ warnings, token, data }` for caller to inspect
- [x] `acknowledge()` function on create/update mutations: resubmits with token, invalidates caches
- [x] `WarningDialog` component: overlay modal showing warning list with field labels, "Go Back" and "Save Anyway" buttons, pending state
- [x] `App.tsx` wired: mutations check `SaveResult`, open dialog on warnings, handle acknowledge/dismiss, clear state on cancel/navigate
- [x] Error recovery: if token expires during acknowledgment, dialog closes and validation errors display on form

### Client-Side Validation
- [x] `EntityForm.validate()` now checks all field constraint rules from metadata: required, minLength, maxLength, min, max, pattern
- [x] Empty non-required fields skip length/range/pattern checks
- [x] Pattern validation wrapped in try/catch for safety against invalid regex in metadata
- [x] First failing rule per field shown (no error stacking on client side)

### Relationship UI Improvements
- [x] Grids show hydrated display values (`{field}_display`) instead of raw IDs — EntityGrid, QueryGrid, CardList all updated
- [x] `RelationSelect` rewritten as searchable typeahead: text input with filtered dropdown, keyboard navigation (arrow keys, enter, escape), outside-click close, clear button
- [x] Limit raised from 100 to 200 related records

### Aggregate Visualization Styles (ADR-0008 Phase E)
- [x] BarChart component: `components/styles/BarChart.tsx` — pure SVG bar chart with vertical/horizontal orientation, value labels, gridlines, configurable color and format; registered as `aggregate/bar-chart`
- [x] PieChart component: `components/styles/PieChart.tsx` — SVG pie/donut chart with arc slices, percentage labels, color legend; registered as `aggregate/pie-chart`
- [x] SummaryGrid component: `components/styles/SummaryGrid.tsx` — HTML table of grouped aggregate data with totals row, per-column formatting; registered as `aggregate/summary-grid`
- [x] YAML view configs: `contact-status-bar.yaml`, `contact-status-pie.yaml`, `contact-status-summary.yaml`
- [x] Aggregate style selector in config-driven mode

### Record Form Style (ADR-0008 Phase F)
- [x] RecordForm component: `components/styles/RecordForm.tsx` — config-driven editable form with sections, collapsible groups, client+server validation, create/edit mode via `dataConfig.recordId`; registered as `record/form`
- [x] PresentationProps extended with form callbacks: `onSubmit`, `onCancel`, `isSubmitting`, `serverErrors`
- [x] ConfiguredComponent passes form callbacks through to presentation components
- [x] YAML view config: `contact-form.yaml`

### React Router + Generic EntityCrudScreen
- [x] URL-based routing with react-router-dom: `/:slug` (list), `/:slug/new` (create), `/:slug/:id` (detail), `/:slug/:id/edit` (edit)
- [x] `EntityCrudScreen` — generic CRUD screen for any entity, detects mode from URL, delegates rendering to ConfiguredComponent
- [x] `useEntityCrud` hook — extracts CRUD mutations + warning acknowledgment state machine
- [x] `routeConfig.ts` — static entity route definitions (Contact + Company), adding new entity requires one-line entry
- [x] `AppLayout` shell with `Sidebar` (left nav with entity links) + header (user label, logout)
- [x] Classic/Config-Driven toggle removed — list always uses ConfiguredComponent
- [x] EntityForm replaced by ConfiguredComponent with record/form in all CRUD flows

### Compose Pattern (ADR-0008 Phase G)
- [x] `ComposeProps` interface and `composeComponent` field on `StyleRegistration` — compose-pattern components manage their own data, bypass `PresentationProps` render path
- [x] Compose branch in `ConfiguredComponent` — early return when `pattern === 'compose'`, delegates to `registration.composeComponent`
- [x] `DetailPage` compose component (`compose/detail-page`): record header with `FieldRenderer` + tabbed child views via `TabPanel` inner component; `tabMode: full` (vertical sidebar) or `inline` (horizontal tabs); children receive `parentContext={{ recordId }}` for automatic `contextFilter` injection
- [x] `EntityCrudScreen` prefers `compose/detail-page` config over `record/detail` for entity detail views; falls back when no compose config exists
- [x] YAML config: `company-detail-page.yaml` — Company header (name, industry, website, phone) + Contacts tab referencing `yaml:company-contacts-grid`
- [x] `Dashboard` compose component (`compose/dashboard`): CSS grid of panels with configurable columns, gap, colSpan/rowSpan; `DashboardPanelCard` inner component resolves child config and renders `ConfiguredComponent compact`
- [x] YAML config: `contacts-dashboard.yaml` — 4-panel dashboard (KPI, bar chart, pie chart, summary grid) replaces hardcoded `DashboardSection`
- [x] Migration: deleted `DashboardSection.tsx`, removed `dashboardConfigIds` from `routeConfig.ts` and `EntityRouteConfig` interface; dashboards now fully config-driven via `useResolvedConfig(entityName, 'dashboard')`

### Bug Fixes (Phase G)
- [x] Fixed "Rendered more hooks than during previous render" crash on Contact detail: `liveDataConfig` useMemo was after compose early return in `ConfiguredComponent`, causing hook count to change when config swapped from record→compose; moved above early return
- [x] Fixed slow Companies list page (5-6s load): `useResolvedConfig` retried 404s 3× with exponential backoff; added `retry` function to skip retries on 404 (`ApiError.status === 404`) and `enabled: !!entityName` guard
- [x] Default row-click navigation in `ConfiguredComponent`: embedded grids (tabs, dashboards) navigate to entity detail on click without explicit `onRowClick` wiring

### Documentation / ADRs
- [x] 8 ADRs accepted: validation architecture, expression DSL, defaulting lifecycle, warning acknowledgment, message interpolation, entity scoping, agent skills, UI component configuration
- [x] ADR index maintained in `docs/adr/README.md`

### Navigation & Screens (ADR-0011)
- [x] Navigation metadata: replace static `routeConfig.ts` + `Sidebar` with metadata-driven nav — `metadata/screens/*.yaml` loader, `GET /api/navigation` + `GET /api/screens/:slug`, sectioned sidebar with icons, permission-aware filtering, auto-generation for uncovered entities
- [x] Screen as a first-class concept: entity/dashboard/admin/custom screen types; `EntityCrudScreen` handles dashboard-type screens, screen-defined view config IDs
- [x] Breadcrumb component: context-aware navigation trail — `Breadcrumb.tsx` + `entityUtils.ts` helpers, wired into `EntityCrudScreen`
