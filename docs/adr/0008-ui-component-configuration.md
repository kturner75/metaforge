# ADR-0008: UI Component Configuration Model

## Status
Accepted

## Context
MetaForge renders UI components from metadata. Currently, entity metadata defines fields, types, and validation — but there is no configuration model for **how data is presented and interacted with** at the view level.

To support:
- Developer-authored views (YAML, Layer 2)
- User-configured views (Layer 3, runtime)
- AI-generated views (agent skills, ADR-0007)

...we need a unified configuration vocabulary for UI components. Every configurable component must have a schema that is:
- Expressive enough to describe real-world views
- Structured enough for AI to generate reliably
- Identical whether authored in YAML or stored in the database

### Key Insight: Data Patterns vs Presentation Styles

Most UI components fall into a small number of **data interaction patterns** that share backend behavior. The difference between a data grid, tree list, and kanban board is *presentation* — they all query the same entity with filters, sort, and pagination. Defining separate schemas per visual component creates unnecessary duplication and makes extensibility harder.

Instead, we separate **what data to fetch** (shared) from **how to render it** (pluggable).

## Decision

### Data Interaction Patterns

Every component implements one of four data patterns:

| Pattern | Backend Interaction | Examples |
|---------|-------------------|----------|
| **Query** | `POST /query/{entity}` with filters/sort/pagination | Data Grid, Search List, Tree List, Kanban, Calendar |
| **Aggregate** | `POST /query/{entity}` with groupBy + aggregate functions | Summary Grid, Bar Chart, Pie Chart, Time Series, KPI Card, Funnel |
| **Record** | `GET/PUT /entities/{entity}/{id}` | Entity Form, Detail View, Activity Timeline |
| **Compose** | No direct backend call — arranges other components | Dashboard, Detail Page |

Components within a pattern group share identical data fetching, filtering, pagination, and caching logic. Presentation styles are purely visual — swapping from grid to kanban changes the renderer, not the query.

### Configuration Structure

Every component config has two parts: a shared **data config** (determined by pattern) and a pluggable **presentation config** (determined by style).

```yaml
ComponentConfig:
  extends: ConfigBase

  # Shared data configuration (same across all styles in a pattern)
  data:
    entityName: string
    filters: FilterConfig | null
    sort: SortField[]
    pageSize: number              # for Query pattern
    drillDown: DrillDownConfig | null

    # Aggregate pattern adds:
    groupBy: string[]             # fields to group by
    measures: Measure[]           # aggregate calculations

  # Pluggable presentation configuration
  presentation:
    style: string                 # registered style name
    styleConfig: object           # style-specific settings (schema per style)
```

### Base Configuration

All component configs extend a common base for scoping, ownership, and metadata:

```yaml
ConfigBase:
  id: string                    # unique identifier
  name: string                  # user-visible name
  description: string | null
  entityName: string            # null for Compose pattern (dashboards)
  owner:
    type: user | role | global
    id: string                  # userId, roleId, or null for global
  scope: personal | team | role | global
  tenantId: string | null       # null for global/dev-time configs
  source: yaml | database       # Layer 2 vs Layer 3 origin
  createdAt: datetime
  updatedAt: datetime
```

### Shared Data Primitives

#### FilterConfig

```yaml
FilterConfig:
  conditions: FilterCondition[]
  operator: and | or            # default: and

FilterCondition:
  field: string
  operator: eq | neq | gt | gte | lt | lte | in | notIn | contains |
            startsWith | isNull | isNotNull | between
  value: any                    # type depends on field + operator
```

This matches the existing backend query filter structure (`SQLiteAdapter.query`), ensuring filters are directly executable without translation.

#### SortField

```yaml
SortField:
  field: string
  direction: asc | desc
```

#### Measure

```yaml
Measure:
  field: string                 # field to aggregate (or "*" for count)
  aggregate: count | sum | avg | min | max | countDistinct
  label: string | null          # display name (auto-generated if null)
  format: number | currency | percent | null
```

#### DrillDownConfig

Drill-down links a summary or grouped view to a detail view, passing filter context:

```yaml
DrillDownConfig:
  targetStyle: string | null    # presentation style to open (null = default grid)
  targetConfig: string | null   # specific saved config ID, or null for ad-hoc
  filterMapping: DrillDownFilter[]

DrillDownFilter:
  sourceField: string           # field from the clicked context
  targetField: string           # field to filter by in the target view
```

### Presentation Style Registry

Presentation styles are registered with the framework. Each style declares:
- Which data pattern it supports
- Its `styleConfig` schema
- The React component that renders it

Adding a new visualization is purely a frontend concern — register a style, provide a component, define the styleConfig shape.

#### Query Pattern Styles

**grid** — Tabular data with sortable, filterable columns.

```yaml
styleConfig:
  columns: GridColumn[]
  selectable: boolean           # checkbox selection column
  inlineEdit: boolean           # allow inline cell editing

GridColumn:
  field: string
  width: number | null          # pixels, null = auto
  visible: boolean              # default true
  sortable: boolean             # default true
  filterable: boolean           # default true
  pinned: left | right | null
```

**searchList** — Filterable list with prominent search and filter controls.

```yaml
styleConfig:
  filterableFields: string[]    # fields exposed as filter inputs
  searchFields: string[]        # fields searched by free-text input
  displayFields: string[]       # fields shown in each result row
```

**tree** — Hierarchical display via self-referencing parentId.

```yaml
styleConfig:
  parentField: string           # e.g., "parentId" — self-relation field
  labelField: string            # field displayed as the node label
  expandDepth: number           # levels expanded by default (default 1)
  showCounts: boolean           # show child count badges
```

**kanban** — Cards grouped into swimlanes by a picklist field.

```yaml
styleConfig:
  laneField: string             # picklist field defining columns/lanes
  cardFields: string[]          # fields displayed on each card
  cardTitleField: string        # primary display field on cards
  allowDrag: boolean            # drag between lanes triggers field update
  showCounts: boolean           # show count per lane
```

**calendar** — Records positioned on a date/time axis.

```yaml
styleConfig:
  dateField: string             # field for event placement
  endDateField: string | null   # for date ranges (null = single-day events)
  labelField: string            # what to display on the calendar entry
  defaultView: month | week | day
```

#### Aggregate Pattern Styles

**summaryGrid** — Tabular display of grouped aggregates.

```yaml
styleConfig:
  showTotals: boolean           # show total row
```

**barChart** — Categorical dimension with one or more measures.

```yaml
styleConfig:
  orientation: horizontal | vertical
  stacked: boolean
  showLabels: boolean
  showLegend: boolean
  colorScheme: string | null    # named palette
```

**pieChart** — Proportional breakdown of a single measure by dimension.

```yaml
styleConfig:
  showLabels: boolean
  showLegend: boolean
  innerRadius: number | null    # > 0 for donut variant
  colorScheme: string | null
```

**timeSeries** — Measures plotted over a date dimension.

```yaml
styleConfig:
  dateField: string             # field for x-axis
  granularity: day | week | month | quarter | year
  comparePrevious: boolean      # overlay previous period
  showArea: boolean             # filled area under line
  colorScheme: string | null
```

**kpiCard** — Single aggregate value with label and optional trend.

```yaml
styleConfig:
  label: string                 # display title
  format: number | currency | percent
  trend:                        # optional comparison
    compareTo: previousPeriod | target
    targetValue: number | null  # for target comparison
```

**funnel** — Sequential stage counts (e.g., sales pipeline).

```yaml
styleConfig:
  stageField: string            # picklist field defining stages
  stageOrder: string[]          # explicit ordering of stages
  showConversion: boolean       # show conversion % between stages
```

#### Record Pattern Styles

**form** — Editable field layout.

```yaml
styleConfig:
  fieldOrder: string[] | null   # explicit field ordering (null = metadata order)
  sections: FormSection[] | null  # group fields into collapsible sections

FormSection:
  label: string
  fields: string[]
  collapsible: boolean
  defaultExpanded: boolean
```

**detail** — Read-only record display.

```yaml
styleConfig:
  fieldOrder: string[] | null
  sections: FormSection[] | null
  showRelatedLists: boolean     # show related entity lists below
```

#### Compose Pattern

**dashboard** — Grid layout of component panels.

```yaml
# Dashboard data config is minimal (no entity):
data:
  entityName: null

styleConfig:
  columns: number               # grid columns (default 12)
  panels: DashboardPanel[]

DashboardPanel:
  id: string
  title: string
  position:
    x: number                   # column start (0-based)
    y: number                   # row start
    width: number               # column span
    height: number              # row span
  componentConfig: string       # ID reference to a saved ComponentConfig
  refreshInterval: number | null  # auto-refresh seconds
```

**detailPage** — Record header with tabbed related components.

```yaml
data:
  entityName: string
  # record ID comes from route context

styleConfig:
  headerFields: string[]        # fields shown in the page header
  tabs: DetailTab[]

DetailTab:
  label: string
  componentConfig: string       # ID of a saved ComponentConfig (usually a grid filtered to this record)
```

### Swapping Presentation

Because data config and presentation config are independent, users can switch styles without reconfiguring data:

```
"Show this as a kanban instead"
  → Keep data config (same entity, filters, sort)
  → Replace presentation: { style: "grid", ... } with { style: "kanban", laneField: "status", ... }
  → No new query, no AI needed for the data side
```

The framework infers reasonable `styleConfig` defaults when switching — e.g., switching to kanban auto-selects the first picklist field as `laneField`. The AI or structured editor can refine from there.

### Layer 3 Storage

All configurations are stored in a single polymorphic table:

```sql
saved_configs
  id              TEXT PRIMARY KEY
  name            TEXT NOT NULL
  entity_name     TEXT             -- nullable for dashboards
  pattern         TEXT NOT NULL    -- "query", "aggregate", "record", "compose"
  style           TEXT NOT NULL    -- "grid", "tree", "barChart", etc.
  owner_type      TEXT NOT NULL    -- "user", "role", "global"
  owner_id        TEXT             -- user or role ID
  tenant_id       TEXT             -- null for global
  scope           TEXT NOT NULL    -- "personal", "team", "role", "global"
  data_config     TEXT NOT NULL    -- JSON: shared data configuration
  style_config    TEXT NOT NULL    -- JSON: presentation-specific configuration
  source          TEXT NOT NULL    -- "yaml" or "database"
  version         INTEGER          -- optimistic locking / history
  created_at      TEXT
  updated_at      TEXT
  created_by      TEXT
  updated_by      TEXT
```

Separating `data_config` and `style_config` into two JSON columns reinforces the split and makes it straightforward to swap styles without touching data config.

### Config Resolution Order

When a component renders, configs resolve with precedence:

1. **Explicit config ID** — component told to use a specific config
2. **User personal config** — user's saved config for this entity + style
3. **Role default** — config scoped to user's role
4. **Tenant default** — tenant-wide default
5. **Global/YAML default** — developer-authored baseline

### Dev-Time YAML (Layer 2)

Developers define baseline views in `metadata/views/`:

```yaml
# metadata/views/contact-grid.yaml
view:
  name: Contact Grid
  entityName: contact
  pattern: query
  style: grid
  data:
    filters: null
    sort:
      - field: fullName
        direction: asc
    pageSize: 25
  styleConfig:
    columns:
      - field: fullName
        pinned: left
      - field: email
      - field: companyId
      - field: status
      - field: healthStatus
    selectable: true
    inlineEdit: false
```

```yaml
# metadata/views/deal-pipeline.yaml
view:
  name: Deal Pipeline
  entityName: deal
  pattern: query
  style: kanban
  data:
    filters: null
    sort:
      - field: updatedAt
        direction: desc
    pageSize: 100
  styleConfig:
    laneField: stage
    cardTitleField: name
    cardFields: [amount, company, closeDate]
    allowDrag: true
    showCounts: true
```

```yaml
# metadata/views/sales-dashboard.yaml
view:
  name: Sales Dashboard
  pattern: compose
  style: dashboard
  data:
    entityName: null
  styleConfig:
    columns: 12
    panels:
      - id: pipeline-by-stage
        title: Pipeline by Stage
        position: { x: 0, y: 0, width: 6, height: 4 }
        componentConfig: deal-stage-bar  # references another saved config
      - id: revenue-trend
        title: Monthly Revenue
        position: { x: 6, y: 0, width: 6, height: 4 }
        componentConfig: deal-revenue-timeseries
```

These serve as baselines. Users and AI skills create Layer 3 overrides and additions.

## Consequences

### Positive
- **Extensibility**: new presentation styles are purely frontend additions — register a style, provide a component, define a styleConfig shape. No backend changes, no new API endpoints.
- **Simplicity**: the backend only understands data patterns (query, aggregate, record). Presentation is a frontend concern.
- **Style swapping**: users can switch between grid/tree/kanban/calendar without reconfiguring filters, sort, or entity selection.
- **AI targeting**: skills produce a data config + style suggestion. The constrained `styleConfig` schemas are small and reliable for LLM generation.
- **Shared infrastructure**: all Query-pattern components share the same data fetching, caching, pagination, and filter logic. Building a new style is just building a renderer.

### Negative
- The `styleConfig` is an untyped `object` at the storage layer — runtime schema validation is needed per style.
- Some styles blur pattern boundaries (e.g., a kanban drag-to-update is both Query and Record). The component handles this internally.
- Reasonable defaults when switching styles require style-aware inference logic.

### Risks
- **Style proliferation**: too many styles with thin differences. Mitigation: only add styles that represent genuinely different interaction models, not cosmetic variants.
- **Config migration**: if a styleConfig schema changes, existing saved configs need migration. Mitigation: version field + backward-compatible additions.
- **Complex dashboards**: deeply nested compose patterns (dashboard of dashboards). Mitigation: limit nesting to one level initially.

### Dependencies
- ADR-0007 (Agent Skills): skills target these configuration schemas as output
- ADR-0006 (Entity Scoping): tenant scoping applies to saved configs
- Backend query endpoint already supports the filter/sort/paginate structure used by DataConfig
