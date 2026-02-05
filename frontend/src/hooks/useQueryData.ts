/**
 * useQueryData — shared data hook for "query" pattern components.
 *
 * Composes useEntityMetadata + useEntityQuery to provide a single
 * interface that presentation components consume through ConfiguredComponent.
 */

import { useState, useMemo } from 'react'
import { useEntityMetadata, useEntityQuery } from './useApi'
import type { DataConfig } from '@/lib/viewTypes'
import type { SortField, QueryResult, EntityMetadata } from '@/lib/types'

interface UseQueryDataResult {
  data: QueryResult | undefined
  metadata: EntityMetadata | undefined
  isLoading: boolean
  error: string | null
  sort: SortField[]
  setSort: (sort: SortField[]) => void
  offset: number
  setOffset: (offset: number) => void
}

export function useQueryData(dataConfig: DataConfig): UseQueryDataResult {
  const entityName = dataConfig.entityName ?? ''

  const [sortOverride, setSortOverride] = useState<SortField[] | null>(null)
  const [offset, setOffset] = useState(0)

  const sort = sortOverride ?? dataConfig.sort ?? []
  const pageSize = dataConfig.pageSize ?? 25

  const { data: metadata, isLoading: metadataLoading } = useEntityMetadata(entityName)

  const queryRequest = useMemo(
    () => ({
      fields: dataConfig.fields,
      filter: dataConfig.filter,
      sort,
      limit: pageSize,
      offset,
    }),
    [dataConfig.fields, dataConfig.filter, sort, pageSize, offset]
  )

  const {
    data: queryResult,
    isLoading: dataLoading,
    error: queryError,
  } = useEntityQuery(entityName, queryRequest)

  return {
    data: queryResult,
    metadata,
    isLoading: metadataLoading || dataLoading,
    error: queryError ? (queryError as Error).message : null,
    sort,
    setSort: (next: SortField[]) => {
      setSortOverride(next)
      setOffset(0) // Reset pagination on sort change
    },
    offset,
    setOffset,
  }
}
