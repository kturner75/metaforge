/**
 * ConfiguredComponent — renders a config-driven view.
 *
 * Given a ConfigBase, it:
 * 1. Resolves the style from the registry
 * 2. Fetches data using the appropriate hook (useQueryData, useAggregateData, useRecordData)
 * 3. Merges default + saved style config
 * 4. Renders the resolved presentation component
 */

import { useMemo } from 'react'
import { getStyleOrFallback } from '@/lib/styleRegistry'
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

export function ConfiguredComponent({ config, parentContext, compact, onRowClick, onSubmit, onCancel, isSubmitting, serverErrors }: ConfiguredComponentProps) {
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
  const isQuery = config.pattern === 'query'
  const isAggregate = config.pattern === 'aggregate'
  const isRecord = config.pattern === 'record'
  const queryData = useQueryData(isQuery ? dataConfig : { entityName: '' })
  const aggregateData = useAggregateData(isAggregate ? dataConfig : { entityName: '' })
  const recordData = useRecordData(isRecord ? dataConfig : { entityName: '' })

  const active = isQuery ? queryData : isRecord ? recordData : aggregateData

  const { data, metadata, isLoading, error } = active

  // For query pattern, wire sort/pagination callbacks
  const handleSort = isQuery ? queryData.setSort : undefined
  const handlePageChange = isQuery ? queryData.setOffset : undefined

  // Need the dataConfig with live sort state for the presentation component
  const liveDataConfig: DataConfig = useMemo(
    () =>
      isQuery
        ? { ...dataConfig, sort: queryData.sort }
        : dataConfig,
    [isQuery, dataConfig, queryData.sort]
  )

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
      onSubmit={onSubmit}
      onCancel={onCancel}
      isSubmitting={isSubmitting}
      serverErrors={serverErrors}
    />
  )
}
