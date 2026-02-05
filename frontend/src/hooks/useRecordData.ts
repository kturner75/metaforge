/**
 * useRecordData — shared data hook for the "record" pattern.
 *
 * Composes useEntityMetadata + useEntity to fetch a single record
 * and adapts the result into QueryResult shape for PresentationProps.
 */

import { useMemo } from 'react'
import { useEntityMetadata, useEntity } from './useApi'
import type { DataConfig } from '@/lib/viewTypes'
import type { QueryResult, EntityMetadata } from '@/lib/types'

interface UseRecordDataResult {
  data: QueryResult | undefined
  metadata: EntityMetadata | undefined
  isLoading: boolean
  error: string | null
}

export function useRecordData(dataConfig: DataConfig): UseRecordDataResult {
  const entityName = dataConfig.entityName ?? ''
  const recordId = dataConfig.recordId ?? undefined

  const { data: metadata, isLoading: metadataLoading } = useEntityMetadata(entityName)

  const {
    data: recordResult,
    isLoading: recordLoading,
    error: recordError,
  } = useEntity(entityName, recordId)

  // Adapt single record into QueryResult shape
  const adaptedData: QueryResult | undefined = useMemo(() => {
    if (!recordResult) return undefined
    const record = (recordResult as { data: Record<string, unknown> }).data
    return {
      data: [record],
      pagination: {
        total: 1,
        limit: null,
        offset: 0,
        hasMore: false,
      },
    }
  }, [recordResult])

  return {
    data: adaptedData,
    metadata,
    isLoading: metadataLoading || recordLoading,
    error: recordError ? (recordError as Error).message : null,
  }
}
