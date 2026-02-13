/**
 * Style registration entry point.
 *
 * Import this module before rendering to ensure all built-in
 * presentation styles are registered in the style registry.
 */

import { registerStyle } from '@/lib/styleRegistry'
import { QueryGrid } from './QueryGrid'
import type { GridStyleConfig } from './QueryGrid'
import { CardList } from './CardList'
import type { CardListStyleConfig } from './CardList'
import { SearchList } from './SearchList'
import type { SearchListStyleConfig } from './SearchList'
import { KanbanBoard } from './KanbanBoard'
import type { KanbanStyleConfig } from './KanbanBoard'
import { RecordDetail } from './RecordDetail'
import type { DetailStyleConfig } from './RecordDetail'
import { RecordForm } from './RecordForm'
import type { FormStyleConfig } from './RecordForm'
import { KpiCard } from './KpiCard'
import type { KpiCardStyleConfig } from './KpiCard'
import { BarChart } from './BarChart'
import type { BarChartStyleConfig } from './BarChart'
import { PieChart } from './PieChart'
import type { PieChartStyleConfig } from './PieChart'
import { SummaryGrid } from './SummaryGrid'
import type { SummaryGridStyleConfig } from './SummaryGrid'
import { TreeView } from './TreeView'
import type { TreeStyleConfig } from './TreeView'
import { CalendarView } from './CalendarView'
import type { CalendarStyleConfig } from './CalendarView'
import { TimeSeries } from './TimeSeries'
import type { TimeSeriesStyleConfig } from './TimeSeries'
import { Funnel } from './Funnel'
import type { FunnelStyleConfig } from './Funnel'
import { DetailPage } from './DetailPage'
import { Dashboard } from './Dashboard'
import type { DetailPageStyleConfig, DashboardStyleConfig } from '@/lib/viewTypes'
import type { PresentationProps } from '@/lib/viewTypes'
import type { ComponentType } from 'react'

registerStyle<GridStyleConfig>({
  pattern: 'query',
  style: 'grid',
  component: QueryGrid,
  defaultStyleConfig: {
    selectable: false,
    inlineEdit: false,
  },
  label: 'Data Grid',
  suggestedPageSize: 25,
})

registerStyle<CardListStyleConfig>({
  pattern: 'query',
  style: 'card-list',
  component: CardList,
  defaultStyleConfig: {
    titleField: 'fullName',
    subtitleField: undefined,
    detailFields: undefined,
    statusField: undefined,
    columns: 3,
  },
  label: 'Card List',
  suggestedPageSize: 12,
})

registerStyle<SearchListStyleConfig>({
  pattern: 'query',
  style: 'search-list',
  component: SearchList,
  defaultStyleConfig: {
    titleField: '',
    subtitleField: undefined,
    searchFields: undefined,
    displayFields: undefined,
    statusField: undefined,
  },
  label: 'Search List',
  suggestedPageSize: 25,
})

registerStyle<KanbanStyleConfig>({
  pattern: 'query',
  style: 'kanban',
  component: KanbanBoard,
  defaultStyleConfig: {
    laneField: '',
    titleField: '',
    subtitleField: undefined,
    detailFields: undefined,
  },
  label: 'Kanban Board',
  suggestedPageSize: 100,
})

registerStyle<DetailStyleConfig>({
  pattern: 'record',
  style: 'detail',
  component: RecordDetail,
  defaultStyleConfig: {
    sections: undefined,
  },
  label: 'Record Detail',
})

registerStyle<FormStyleConfig>({
  pattern: 'record',
  style: 'form',
  component: RecordForm,
  defaultStyleConfig: {
    sections: undefined,
  },
  label: 'Record Form',
})

registerStyle<KpiCardStyleConfig>({
  pattern: 'aggregate',
  style: 'kpi-card',
  component: KpiCard,
  defaultStyleConfig: {
    label: 'Metric',
    valueField: 'value',
  },
  label: 'KPI Card',
})

registerStyle<BarChartStyleConfig>({
  pattern: 'aggregate',
  style: 'bar-chart',
  component: BarChart,
  defaultStyleConfig: {
    dimensionField: '',
    measureField: '',
    orientation: 'vertical',
    showValues: true,
  },
  label: 'Bar Chart',
})

registerStyle<PieChartStyleConfig>({
  pattern: 'aggregate',
  style: 'pie-chart',
  component: PieChart,
  defaultStyleConfig: {
    dimensionField: '',
    measureField: '',
    donut: false,
    showLegend: true,
    showPercent: true,
  },
  label: 'Pie Chart',
})

registerStyle<SummaryGridStyleConfig>({
  pattern: 'aggregate',
  style: 'summary-grid',
  component: SummaryGrid,
  defaultStyleConfig: {
    showTotals: true,
  },
  label: 'Summary Grid',
})

registerStyle<TreeStyleConfig>({
  pattern: 'query',
  style: 'tree',
  component: TreeView,
  defaultStyleConfig: {
    titleField: '',
    parentField: '',
    detailFields: undefined,
    indentPx: 24,
  },
  label: 'Tree View',
  suggestedPageSize: 500,
})

registerStyle<CalendarStyleConfig>({
  pattern: 'query',
  style: 'calendar',
  component: CalendarView,
  defaultStyleConfig: {
    dateField: '',
    titleField: '',
    eventColor: undefined,
  },
  label: 'Calendar',
  suggestedPageSize: 500,
})

registerStyle<TimeSeriesStyleConfig>({
  pattern: 'aggregate',
  style: 'time-series',
  component: TimeSeries,
  defaultStyleConfig: {
    timeField: '',
    measureField: '',
    chartType: 'line',
    showPoints: true,
    showGrid: true,
  },
  label: 'Time Series',
})

registerStyle<FunnelStyleConfig>({
  pattern: 'aggregate',
  style: 'funnel',
  component: Funnel,
  defaultStyleConfig: {
    stageField: '',
    measureField: '',
    stageOrder: undefined,
    showPercent: true,
    showValues: true,
  },
  label: 'Funnel',
})

registerStyle<DetailPageStyleConfig>({
  pattern: 'compose',
  style: 'detail-page',
  component: (() => null) as unknown as ComponentType<PresentationProps<DetailPageStyleConfig>>,
  composeComponent: DetailPage,
  defaultStyleConfig: {
    headerFields: [],
    tabMode: 'full',
    tabs: [],
  },
  label: 'Detail Page',
})

registerStyle<DashboardStyleConfig>({
  pattern: 'compose',
  style: 'dashboard',
  component: (() => null) as unknown as ComponentType<PresentationProps<DashboardStyleConfig>>,
  composeComponent: Dashboard,
  defaultStyleConfig: {
    columns: 3,
    gap: 16,
    panels: [],
  },
  label: 'Dashboard',
})
