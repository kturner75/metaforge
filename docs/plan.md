# Plan: Aggregate Visualization Styles (Bar Chart, Pie Chart, Summary Grid)

## Goal
Add three new aggregate-pattern presentation styles — **Bar Chart**, **Pie Chart**, and **Summary Grid** — following the same zero-dependency, CSS-only approach used by every existing style in MetaForge.

## Approach: SVG Charts, No External Library
The project currently has zero charting dependencies. Rather than pulling in a heavy library (Recharts ~170 kB, Chart.js ~200 kB), we'll render **inline SVG** directly in React components. This keeps the bundle lean, matches the existing pattern of self-contained presentation components, and gives full control over styling via CSS custom properties.

- Bar Chart → `<svg>` with `<rect>` bars + axis labels
- Pie Chart → `<svg>` with `<path>` slices computed from arc math (`Math.sin`/`Math.cos`)
- Summary Grid → HTML `<table>` (no SVG needed)

Each component follows the identical contract: `PresentationProps<TStyleConfig>`, registered in the style registry as `aggregate/bar-chart`, `aggregate/pie-chart`, and `aggregate/summary-grid`.

## Deliverables

### 1. BarChart component (`components/styles/BarChart.tsx`)
**StyleConfig:**
```ts
interface BarChartStyleConfig {
  dimensionField: string      // groupBy field for x-axis labels
  measureField: string        // measure result column for bar height
  orientation?: 'vertical' | 'horizontal'  // default: vertical
  showValues?: boolean        // label bars with values (default: true)
  barColor?: string           // CSS color (default: var(--brand))
  format?: 'number' | 'percent' | 'currency'
}
```
**Rendering:** Pure SVG. Computes bar widths from container, scales heights to max value. Axis labels from `dimensionField` values. Responsive via `viewBox`.

### 2. PieChart component (`components/styles/PieChart.tsx`)
**StyleConfig:**
```ts
interface PieChartStyleConfig {
  dimensionField: string      // groupBy field for slice labels
  measureField: string        // measure result column for slice size
  donut?: boolean             // hollow center (default: false)
  showLegend?: boolean        // legend alongside chart (default: true)
  showPercent?: boolean       // % labels on slices (default: true)
  colors?: string[]           // custom palette (has sensible defaults)
  format?: 'number' | 'percent' | 'currency'
}
```
**Rendering:** SVG circle with `<path>` arcs. Legend as an HTML list next to the SVG. Donut variant uses a smaller inner radius.

### 3. SummaryGrid component (`components/styles/SummaryGrid.tsx`)
**StyleConfig:**
```ts
interface SummaryGridStyleConfig {
  dimensionFields?: string[]  // columns to show from groupBy (all if omitted)
  measureFields?: string[]    // which measure columns to display (all if omitted)
  showTotals?: boolean        // totals row at bottom (default: true)
  format?: Record<string, 'number' | 'percent' | 'currency'>  // per-column format
}
```
**Rendering:** HTML `<table>` with grouped rows + a totals row computed client-side from the aggregate data.

### 4. Style registration (`components/styles/index.ts`)
Register all three as:
- `{ pattern: 'aggregate', style: 'bar-chart', label: 'Bar Chart' }`
- `{ pattern: 'aggregate', style: 'pie-chart', label: 'Pie Chart' }`
- `{ pattern: 'aggregate', style: 'summary-grid', label: 'Summary Grid' }`

### 5. YAML view configs (`metadata/views/`)
- `contact-status-bar.yaml` — Bar chart of contacts grouped by `status`, measure `count(*)`. Demonstrates the bar chart with real data.
- `contact-status-pie.yaml` — Same data as pie chart.
- `contact-status-summary.yaml` — Summary grid of contacts by status with count.

### 6. CSS (`App.css`)
Add styles for `.bar-chart-*`, `.pie-chart-*`, and `.summary-grid-*` classes, following the naming pattern of existing `.kpi-card-*`, `.kanban-*`, etc.

### 7. App.tsx integration
Add an **Aggregate Styles** section below the existing KPI card in config-driven mode:
- A style selector scoped to aggregate pattern
- Renders the selected aggregate chart via `ConfiguredComponent`

This mirrors how the query-pattern style selector already works but for aggregate views.

## File Changes Summary

| File | Action |
|------|--------|
| `frontend/src/components/styles/BarChart.tsx` | **Create** |
| `frontend/src/components/styles/PieChart.tsx` | **Create** |
| `frontend/src/components/styles/SummaryGrid.tsx` | **Create** |
| `frontend/src/components/styles/index.ts` | **Edit** — add 3 registrations |
| `frontend/src/App.css` | **Edit** — add chart CSS |
| `frontend/src/App.tsx` | **Edit** — aggregate style selector + section |
| `metadata/views/contact-status-bar.yaml` | **Create** |
| `metadata/views/contact-status-pie.yaml` | **Create** |
| `metadata/views/contact-status-summary.yaml` | **Create** |

## What This Does NOT Change
- No backend changes needed (aggregate endpoint already supports groupBy + measures)
- No new npm dependencies
- No changes to `viewTypes.ts`, `styleRegistry.ts`, `useAggregateData.ts`, or `ConfiguredComponent.tsx` — all existing infrastructure works as-is
- No changes to existing styles or components

## Build / Test
- `npm run build` must pass (TypeScript clean)
- Manual verification: config-driven mode shows aggregate style selector with Bar Chart, Pie Chart, Summary Grid alongside existing KPI Card
