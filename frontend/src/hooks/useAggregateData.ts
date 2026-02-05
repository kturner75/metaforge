/**
 * useAggregateData — shared data hook for the "aggregate" pattern.
 *
 * Calls the backend aggregate endpoint and adapts the result
 * into PresentationProps-compatible shape.
 */

import { useMemo } from 'react'
import { useEntityMetadata, useAggregateQuery } from './useApi'
import type { DataConfig } from '@/lib/viewTypes'
import type { QueryResult, EntityMetadata } from '@/lib/types'

interface UseAggregateDataResult {
  data: QueryResult | undefined
  metadata: EntityMetadata | undefined
  isLoading: boolean
  error: string | null
}

export function useAggregateData(dataConfig: DataConfig): UseAggregateDataResult {
  const entityName = dataConfig.entityName ?? ''

  const { data: metadata, isLoading: metadataLoading } = useEntityMetadata(entityName)

  const aggregateRequest = useMemo(
    () => ({
      groupBy: dataConfig.groupBy,
      measures: dataConfig.measures?.map((m) => ({
        field: m.field,
        aggregate: m.aggregate,
        label: m.label,
      })),
      filter: dataConfig.filter,
    }),
    [dataConfig.groupBy, dataConfig.measures, dataConfig.filter],
  )

  const {
    data: aggregateResult,
    isLoading: dataLoading,
    error: queryError,
  } = useAggregateQuery(entityName, aggregateRequest)

  // Adapt AggregateResult into QueryResult shape for PresentationProps
  const adaptedData: QueryResult | undefined = useMemo(() => {
    if (!aggregateResult) return undefined
    return {
      data: aggregateResult.data,
      pagination: {
        total: aggregateResult.total,
        limit: null,
        offset: 0,
        hasMore: false,
      },
    }
  }, [aggregateResult])

  return {
    data: adaptedData,
    metadata,
    isLoading: metadataLoading || dataLoading,
    error: queryError ? (queryError as Error).message : null,
  }
}
