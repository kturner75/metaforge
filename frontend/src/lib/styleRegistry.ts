/**
 * Style registry — maps (dataPattern, style) pairs to presentation components.
 *
 * Mirrors the fieldRegistry pattern: module-level map with register/get functions.
 */

import type { DataPattern, StyleRegistration, PresentationProps } from './viewTypes'
import type { ComponentType } from 'react'

const registry = new Map<DataPattern, Map<string, StyleRegistration>>()

export function registerStyle<TStyleConfig = Record<string, unknown>>(
  registration: StyleRegistration<TStyleConfig>
): void {
  let patternMap = registry.get(registration.pattern)
  if (!patternMap) {
    patternMap = new Map()
    registry.set(registration.pattern, patternMap)
  }
  patternMap.set(registration.style, registration as StyleRegistration)
}

export function getStyle(
  pattern: DataPattern,
  style: string
): StyleRegistration | null {
  return registry.get(pattern)?.get(style) ?? null
}

export function getStyleOrFallback(
  pattern: DataPattern,
  style: string
): StyleRegistration {
  const exact = getStyle(pattern, style)
  if (exact) return exact

  // Fall back to first registered style for this pattern
  const patternMap = registry.get(pattern)
  if (patternMap && patternMap.size > 0) {
    return patternMap.values().next().value!
  }

  // Last resort: return a placeholder that renders nothing
  return {
    pattern,
    style,
    component: (() => null) as ComponentType<PresentationProps>,
    defaultStyleConfig: {},
    label: style,
  }
}

export function listStyles(pattern?: DataPattern): StyleRegistration[] {
  if (pattern) {
    const patternMap = registry.get(pattern)
    return patternMap ? Array.from(patternMap.values()) : []
  }

  const all: StyleRegistration[] = []
  for (const patternMap of registry.values()) {
    for (const reg of patternMap.values()) {
      all.push(reg)
    }
  }
  return all
}
