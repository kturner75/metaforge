/**
 * ConfiguredComponent — renders a config-driven view.
 *
 * Given a ConfigBase, it:
 * 1. Resolves the style from the registry
 * 2. Fetches data using the appropriate hook (useQueryData, useAggregateData, useRecordData)
 * 3. Merges default + saved style config
 * 4. Renders the resolved presentation component
 */

import { useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getStyleOrFallback } from '@/lib/styleRegistry'
import { getRouteByEntity } from '@/lib/routeConfig'
import { useQueryData } from '@/hooks/useQueryData'
import { useAggregateData } from '@/hooks/useAggregateData'
import { useRecordData } from '@/hooks/useRecordData'
import type { ConfigBase, DataConfig } from '@/lib/viewTypes'
import type { FilterGroup } from '@/lib/types'
import type { ValidationErrorBody } from '@/lib/api'

interface ConfiguredComponentProps {
  config: ConfigBase
  /** Parent record context — supplies the value for contextFilter */
  parentContext?: { recordId: string }
  /** When true, tells the style component to render in compact/embedded mode */
  compact?: boolean
  onRowClick?: (row: Record<string, unknown>) => void
  onSubmit?: (data: Record<string, unknown>) => void
  onCancel?: () => void
  isSubmitting?: boolean
  serverErrors?: ValidationErrorBody | null
}

export function ConfiguredComponent({ config, parentContext, compact, onRowClick: onRowClickProp, onSubmit, onCancel, isSubmitting, serverErrors }: ConfiguredComponentProps) {
  const navigate = useNavigate()

  // Default row click: navigate to the entity detail page when no explicit handler is provided.
  // This makes embedded grids (tabs, dashboards) clickable without each parent wiring onRowClick.
  const entityName = config.entityName ?? config.dataConfig?.entityName
  const defaultRowClick = useCallback(
    (row: Record<string, unknown>) => {
      if (!entityName) return
      const route = getRouteByEntity(entityName)
      if (route && row.id) navigate(`/${route.slug}/${row.id}`)
    },
    [entityName, navigate]
  )
  const onRowClick = onRowClickProp ?? (config.pattern === 'query' ? defaultRowClick : undefined)

  // Drilldown handler for aggregate components: navigate to the entity list filtered by the clicked dimension.
  const onDrilldown = useCallback(
    (field: string, value: unknown) => {
      if (!entityName) return
      const route = getRouteByEntity(entityName)
      if (!route) return
      const drilldownFilter = { operator: 'and' as const, conditions: [{ field, operator: 'eq' as const, value }] }
      navigate(`/${route.slug}`, { state: { drilldownFilter } })
    },
    [entityName, navigate]
  )
  const registration = useMemo(
    () => getStyleOrFallback(config.pattern, config.style),
    [config.pattern, config.style]
  )

  const mergedStyleConfig = useMemo(
    () => ({ ...registration.defaultStyleConfig, ...config.styleConfig }),
    [registration.defaultStyleConfig, config.styleConfig]
  )

  const dataConfig: DataConfig = useMemo(() => {
    const base: DataConfig = {
      entityName: config.entityName ?? undefined,
      ...config.dataConfig,
    }

    // Merge contextFilter: when a parent context is provided and the config declares
    // a contextFilter field, inject an eq condition into the filter.
    if (base.contextFilter && parentContext) {
      const contextCondition = {
        field: base.contextFilter.field,
        operator: 'eq',
        value: parentContext.recordId,
      }
      const existingFilter = base.filter
      const merged: FilterGroup = existingFilter
        ? { operator: 'and', conditions: [...existingFilter.conditions, contextCondition] }
        : { operator: 'and', conditions: [contextCondition] }
      base.filter = merged
    }

    return base
  }, [config.entityName, config.dataConfig, parentContext])

  // All hooks are called unconditionally (React hook rules).
  // Inactive ones get a config that produces minimal work.
  const isCompose = config.pattern === 'compose'
  const isQuery = config.pattern === 'query'
  const isAggregate = config.pattern === 'aggregate'
  const isRecord = config.pattern === 'record'
  const queryData = useQueryData(isQuery ? dataConfig : { entityName: '' })
  const aggregateData = useAggregateData(isAggregate ? dataConfig : { entityName: '' })
  const recordData = useRecordData(isRecord ? dataConfig : { entityName: '' })

  // Need the dataConfig with live sort state for the presentation component.
  // Must be called unconditionally (React hook rules) — before the compose early return.
  const liveDataConfig: DataConfig = useMemo(
    () =>
      isQuery
        ? { ...dataConfig, sort: queryData.sort }
        : dataConfig,
    [isQuery, dataConfig, queryData.sort]
  )

  // Compose pattern: delegate to the compose-specific component which manages
  // its own data fetching and renders child ConfiguredComponent instances.
  if (isCompose && registration.composeComponent) {
    const ComposeComponent = registration.composeComponent
    return (
      <ComposeComponent
        config={config}
        styleConfig={mergedStyleConfig}
        compact={compact}
      />
    )
  }

  const active = isQuery ? queryData : isRecord ? recordData : aggregateData

  const { data, metadata, isLoading, error } = active

  // For query pattern, wire sort/pagination callbacks
  const handleSort = isQuery ? queryData.setSort : undefined
  const handlePageChange = isQuery ? queryData.setOffset : undefined

  if (!metadata && !isLoading) {
    return <div className="error">Entity metadata not available</div>
  }

  const Component = registration.component

  return (
    <Component
      data={data ?? { data: [], pagination: { total: 0, limit: null, offset: 0, hasMore: false } }}
      metadata={metadata!}
      styleConfig={mergedStyleConfig}
      dataConfig={liveDataConfig}
      isLoading={isLoading}
      error={error}
      compact={compact}
      onSort={handleSort}
      onPageChange={handlePageChange}
      onRowClick={onRowClick}
      onDrilldown={isAggregate ? onDrilldown : undefined}
      onSubmit={onSubmit}
      onCancel={onCancel}
      isSubmitting={isSubmitting}
      serverErrors={serverErrors}
    />
  )
}
