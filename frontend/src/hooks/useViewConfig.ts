/**
 * Config API hooks — fetch, create, update, delete saved view configs.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchJson } from '@/lib/api'
import type { ConfigBase } from '@/lib/viewTypes'

const API = '/api/views'

interface ConfigListResponse {
  data: ConfigBase[]
}

interface ConfigSingleResponse {
  data: ConfigBase
}

// --- Query hooks ---

export function useSavedConfig(configId: string | undefined) {
  return useQuery({
    queryKey: ['viewConfig', configId],
    queryFn: () => fetchJson<ConfigSingleResponse>(`${API}/configs/${configId}`),
    enabled: !!configId,
    select: (res) => res.data,
  })
}

export function useSavedConfigs(params?: {
  entityName?: string
  pattern?: string
  style?: string
}) {
  const searchParams = new URLSearchParams()
  if (params?.entityName) searchParams.set('entity_name', params.entityName)
  if (params?.pattern) searchParams.set('pattern', params.pattern)
  if (params?.style) searchParams.set('style', params.style)
  const qs = searchParams.toString()

  return useQuery({
    queryKey: ['viewConfigs', params],
    queryFn: () => fetchJson<ConfigListResponse>(`${API}/configs${qs ? `?${qs}` : ''}`),
    select: (res) => res.data,
  })
}

export function useResolvedConfig(entityName: string, style: string) {
  return useQuery({
    queryKey: ['viewConfig', 'resolve', entityName, style],
    queryFn: () =>
      fetchJson<ConfigSingleResponse>(
        `${API}/resolve?entity_name=${encodeURIComponent(entityName)}&style=${encodeURIComponent(style)}`
      ),
    select: (res) => res.data,
  })
}

// --- Mutation hooks ---

export function useCreateConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: {
      name: string
      description?: string
      entity_name?: string
      pattern: string
      style: string
      scope?: string
      data_config: Record<string, unknown>
      style_config: Record<string, unknown>
    }) =>
      fetchJson<ConfigSingleResponse>(`${API}/configs`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['viewConfigs'] })
      queryClient.invalidateQueries({ queryKey: ['viewConfig', 'resolve'] })
    },
  })
}

export function useUpdateConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string
      name?: string
      description?: string
      data_config?: Record<string, unknown>
      style_config?: Record<string, unknown>
      scope?: string
    }) =>
      fetchJson<ConfigSingleResponse>(`${API}/configs/${id}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['viewConfig', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['viewConfigs'] })
      queryClient.invalidateQueries({ queryKey: ['viewConfig', 'resolve'] })
    },
  })
}

export function useDeleteConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ success: boolean }>(`${API}/configs/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['viewConfigs'] })
      queryClient.invalidateQueries({ queryKey: ['viewConfig'] })
    },
  })
}
