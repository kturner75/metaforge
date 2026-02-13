/**
 * API hooks for metadata and entity operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { EntityMetadata, FilterGroup, QueryRequest, QueryResult } from '@/lib/types'
import { fetchJson, type ValidationErrorItem } from '@/lib/api'

const API_BASE = '/api'

// --- Metadata ---

export function useEntityMetadata(entity: string) {
  return useQuery({
    queryKey: ['metadata', entity],
    queryFn: () => fetchJson<EntityMetadata>(`${API_BASE}/metadata/${entity}`),
    staleTime: Infinity,
  })
}

export function useEntitiesList() {
  return useQuery({
    queryKey: ['metadata'],
    queryFn: () =>
      fetchJson<{ entities: { name: string; displayName: string; pluralName: string }[] }>(
        `${API_BASE}/metadata`
      ),
    staleTime: Infinity,
  })
}

// --- Query ---

export function useEntityQuery<T = Record<string, unknown>>(
  entity: string,
  query: QueryRequest
) {
  return useQuery({
    queryKey: ['query', entity, query],
    queryFn: () =>
      fetchJson<QueryResult<T>>(`${API_BASE}/query/${entity}`, {
        method: 'POST',
        body: JSON.stringify(query),
      }),
  })
}

// --- Aggregate ---

export interface AggregateRequest {
  groupBy?: string[]
  measures?: { field: string; aggregate: string; label?: string }[]
  filter?: FilterGroup
  dateTrunc?: Record<string, string>
}

export interface AggregateResult {
  data: Record<string, unknown>[]
  total: number
}

export function useAggregateQuery(entity: string, request: AggregateRequest) {
  return useQuery({
    queryKey: ['aggregate', entity, request],
    queryFn: () =>
      fetchJson<AggregateResult>(`${API_BASE}/aggregate/${entity}`, {
        method: 'POST',
        body: JSON.stringify(request),
      }),
    enabled: !!entity,
  })
}

// --- CRUD ---

/** Shape returned by the backend when warnings require acknowledgment (HTTP 202). */
interface AcknowledgmentResponse {
  valid?: boolean
  requiresAcknowledgment?: boolean
  acknowledgmentToken?: string
  warnings?: ValidationErrorItem[]
  data?: Record<string, unknown>
}

/** Pending warning state surfaced to the caller for user confirmation. */
export interface PendingWarnings {
  warnings: ValidationErrorItem[]
  token: string
  data: Record<string, unknown>
}

/** Mutation result: either the saved record or pending warnings needing user acknowledgment. */
export type SaveResult = {
  saved: true
  data: Record<string, unknown>
} | {
  saved: false
  pendingWarnings: PendingWarnings
}

export function useEntity<T = Record<string, unknown>>(entity: string, id: string | undefined) {
  return useQuery({
    queryKey: ['entity', entity, id],
    queryFn: () => fetchJson<{ data: T }>(`${API_BASE}/entities/${entity}/${id}`),
    enabled: !!id,
  })
}

export function useCreateEntity(entity: string) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async (data: Record<string, unknown>): Promise<SaveResult> => {
      const result = await fetchJson<AcknowledgmentResponse & { data: Record<string, unknown> }>(
        `${API_BASE}/entities/${entity}`,
        { method: 'POST', body: JSON.stringify({ data }) },
      )

      // Surface warnings to the caller instead of auto-acknowledging
      if (result.requiresAcknowledgment && result.acknowledgmentToken && result.warnings) {
        return {
          saved: false,
          pendingWarnings: {
            warnings: result.warnings,
            token: result.acknowledgmentToken,
            data: result.data ?? data,
          },
        }
      }

      return { saved: true, data: result.data ?? result as unknown as Record<string, unknown> }
    },
    onSuccess: (result) => {
      if (result.saved) {
        queryClient.invalidateQueries({ queryKey: ['query', entity] })
        queryClient.invalidateQueries({ queryKey: ['aggregate', entity] })
      }
    },
  })

  /** Acknowledge warnings and complete the save. */
  const acknowledge = async (pending: PendingWarnings) => {
    const result = await fetchJson<{ data: Record<string, unknown> }>(
      `${API_BASE}/entities/${entity}`,
      {
        method: 'POST',
        body: JSON.stringify({
          data: pending.data,
          acknowledgeWarnings: pending.token,
        }),
      },
    )
    queryClient.invalidateQueries({ queryKey: ['query', entity] })
    queryClient.invalidateQueries({ queryKey: ['aggregate', entity] })
    return result
  }

  return { ...mutation, acknowledge }
}

export function useUpdateEntity(entity: string) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Record<string, unknown> }): Promise<SaveResult> => {
      const result = await fetchJson<AcknowledgmentResponse & { data: Record<string, unknown> }>(
        `${API_BASE}/entities/${entity}/${id}`,
        { method: 'PUT', body: JSON.stringify({ data }) },
      )

      // Surface warnings to the caller instead of auto-acknowledging
      if (result.requiresAcknowledgment && result.acknowledgmentToken && result.warnings) {
        return {
          saved: false,
          pendingWarnings: {
            warnings: result.warnings,
            token: result.acknowledgmentToken,
            data: result.data ?? data,
          },
        }
      }

      return { saved: true, data: result.data ?? result as unknown as Record<string, unknown> }
    },
    onSuccess: (result, { id }) => {
      if (result.saved) {
        queryClient.invalidateQueries({ queryKey: ['query', entity] })
        queryClient.invalidateQueries({ queryKey: ['entity', entity, id] })
        queryClient.invalidateQueries({ queryKey: ['aggregate', entity] })
      }
    },
  })

  /** Acknowledge warnings and complete the update. */
  const acknowledge = async (id: string, pending: PendingWarnings) => {
    const result = await fetchJson<{ data: Record<string, unknown> }>(
      `${API_BASE}/entities/${entity}/${id}`,
      {
        method: 'PUT',
        body: JSON.stringify({
          data: pending.data,
          acknowledgeWarnings: pending.token,
        }),
      },
    )
    queryClient.invalidateQueries({ queryKey: ['query', entity] })
    queryClient.invalidateQueries({ queryKey: ['entity', entity, id] })
    queryClient.invalidateQueries({ queryKey: ['aggregate', entity] })
    return result
  }

  return { ...mutation, acknowledge }
}

export function useDeleteEntity(entity: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ success: boolean }>(`${API_BASE}/entities/${entity}/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['query', entity] })
    },
  })
}

export function useAuthMe(enabled: boolean) {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () =>
      fetchJson<{
        user_id: string
        email: string
        name: string
        active_tenant_id: string | null
        active_role: string | null
        tenants: { id: string; name: string; slug: string; role: string }[]
      }>(`${API_BASE}/auth/me`),
    enabled,
    retry: false,
  })
}
