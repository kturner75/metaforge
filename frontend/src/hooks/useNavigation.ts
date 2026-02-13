/**
 * Navigation and screen hooks — fetch navigation tree and screen definitions.
 */

import { useQuery } from '@tanstack/react-query'
import { fetchJson } from '@/lib/api'
import type { NavigationResponse, ScreenConfig } from '@/lib/screenTypes'

/**
 * Fetch the navigation tree for the current user (permission-filtered).
 * Cached for 5 minutes since navigation structure rarely changes.
 */
export function useNavigation() {
  return useQuery({
    queryKey: ['navigation'],
    queryFn: () => fetchJson<NavigationResponse>('/api/navigation'),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Fetch the full screen definition for a given slug.
 * Used by EntityCrudScreen to get view config references.
 */
export function useScreen(slug: string | undefined) {
  return useQuery({
    queryKey: ['screen', slug],
    queryFn: () => fetchJson<{ data: ScreenConfig }>(`/api/screens/${slug}`),
    enabled: !!slug,
    select: (res) => res.data,
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error) => {
      // Don't retry 404s — screen simply doesn't exist
      if (error && 'status' in error && (error as { status: number }).status === 404) return false
      return failureCount < 2
    },
  })
}
