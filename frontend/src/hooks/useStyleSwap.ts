/**
 * useStyleSwap — switch presentation styles while preserving data config.
 *
 * Computes a transient ConfigBase by keeping the current config's dataConfig
 * and inferring a new styleConfig for the target style from entity metadata
 * and any saved config.
 */

import { useMemo } from 'react'
import { useEntityMetadata } from './useApi'
import { useSavedConfigs } from './useViewConfig'
import { getStyle, getStyleOrFallback, listStyles } from '@/lib/styleRegistry'
import { inferStyleConfig } from '@/lib/styleInference'
import type { ConfigBase } from '@/lib/viewTypes'

interface UseStyleSwapOptions {
  /** The current active config (base config). Undefined while loading. */
  currentConfig: ConfigBase | undefined
  /** The target style name to swap to */
  targetStyle: string
}

interface UseStyleSwapResult {
  /** The computed config for the target style (null while loading) */
  config: ConfigBase | null
  /** Whether metadata or saved config is still loading */
  isLoading: boolean
  /** Available styles for the current config's pattern */
  availableStyles: { style: string; label: string }[]
}

export function useStyleSwap({
  currentConfig,
  targetStyle,
}: UseStyleSwapOptions): UseStyleSwapResult {
  const entityName = currentConfig?.entityName ?? ''
  const pattern = currentConfig?.pattern ?? 'query'

  const { data: metadata, isLoading: metadataLoading } = useEntityMetadata(entityName)

  // Fetch saved configs for the target style (returns [] if none exist — no 404)
  const { data: savedTargetConfigs, isLoading: savedLoading } = useSavedConfigs({
    entityName: entityName || undefined,
    pattern,
    style: targetStyle,
  })
  const savedTargetConfig = savedTargetConfigs?.[0] ?? null

  const sourceRegistration = currentConfig
    ? getStyle(pattern, currentConfig.style)
    : null
  const targetRegistration = getStyleOrFallback(pattern, targetStyle)

  const availableStyles = useMemo(
    () => listStyles(pattern).map((s) => ({ style: s.style, label: s.label })),
    [pattern],
  )

  const config: ConfigBase | null = useMemo(() => {
    if (!currentConfig) return null

    // Same style — return current config unchanged
    if (targetStyle === currentConfig.style) return currentConfig

    if (!metadata) return null

    // Adapt pageSize: swap to target's suggested size only if current
    // matches the source style's suggested size (i.e. user didn't customize it)
    let newPageSize = currentConfig.dataConfig.pageSize
    const sourcePageSize = sourceRegistration?.suggestedPageSize
    const targetPageSize = targetRegistration.suggestedPageSize
    if (sourcePageSize && targetPageSize && newPageSize === sourcePageSize) {
      newPageSize = targetPageSize
    }

    const newDataConfig = {
      ...currentConfig.dataConfig,
      pageSize: newPageSize,
    }

    const newStyleConfig = inferStyleConfig({
      registration: targetRegistration,
      metadata,
      currentDataConfig: newDataConfig,
      savedStyleConfig: savedTargetConfig?.styleConfig as Record<string, unknown> | undefined,
    })

    return {
      ...currentConfig,
      id: `transient:${currentConfig.id}:${targetStyle}`,
      name: `${currentConfig.name} (${targetRegistration.label})`,
      style: targetStyle,
      source: 'transient',
      dataConfig: newDataConfig,
      styleConfig: newStyleConfig,
    }
  }, [
    targetStyle,
    currentConfig,
    metadata,
    savedTargetConfig,
    sourceRegistration,
    targetRegistration,
  ])

  return {
    config,
    isLoading: !currentConfig || metadataLoading || (savedLoading && targetStyle !== currentConfig.style),
    availableStyles,
  }
}
