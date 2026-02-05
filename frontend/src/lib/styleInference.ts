/**
 * Style-config inference — produces a reasonable styleConfig for a target
 * style by combining the style's defaults, metadata-aware heuristics,
 * and any existing saved config.
 */

import type { EntityMetadata, FieldMetadata } from './types'
import type { StyleRegistration, DataConfig } from './viewTypes'

export interface InferStyleConfigOptions {
  /** Target style registration from the registry */
  registration: StyleRegistration
  /** Entity metadata for field-aware inference */
  metadata: EntityMetadata
  /** The current config's dataConfig (for context) */
  currentDataConfig?: DataConfig
  /** A saved styleConfig for this style, if one exists */
  savedStyleConfig?: Record<string, unknown>
}

const AUTO_FIELD_NAMES = new Set([
  'id', 'tenantId', 'createdAt', 'updatedAt', 'createdBy', 'updatedBy',
])

const LONG_TEXT_TYPES = new Set(['text', 'description', 'address'])

const SEARCHABLE_TYPES = new Set(['name', 'text', 'email', 'phone', 'description'])

function isAutoField(field: FieldMetadata): boolean {
  return field.primaryKey === true || AUTO_FIELD_NAMES.has(field.name)
}

function findFirstByType(
  fields: FieldMetadata[],
  types: string[],
): FieldMetadata | undefined {
  return fields.find((f) => types.includes(f.type))
}

/**
 * Built-in heuristic: inspects which keys exist in defaultStyleConfig
 * and fills them from entity metadata.
 */
function builtinInfer(
  defaultConfig: Record<string, unknown>,
  metadata: EntityMetadata,
): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  const visibleFields = metadata.fields.filter((f) => !isAutoField(f))

  if ('titleField' in defaultConfig) {
    result.titleField =
      findFirstByType(visibleFields, ['name'])?.name ?? visibleFields[0]?.name
  }

  if ('subtitleField' in defaultConfig) {
    const titleName = result.titleField as string | undefined
    const candidates = visibleFields.filter((f) => f.name !== titleName)
    result.subtitleField =
      findFirstByType(candidates, ['email'])?.name ??
      findFirstByType(candidates, ['phone'])?.name
  }

  if ('detailFields' in defaultConfig) {
    const used = new Set(
      [result.titleField, result.subtitleField].filter(Boolean) as string[],
    )
    result.detailFields = visibleFields
      .filter((f) => !used.has(f.name))
      .slice(0, 4)
      .map((f) => f.name)
  }

  if ('statusField' in defaultConfig) {
    result.statusField = findFirstByType(visibleFields, ['picklist'])?.name
  }

  if ('laneField' in defaultConfig) {
    result.laneField = findFirstByType(visibleFields, ['picklist'])?.name
  }

  if ('displayFields' in defaultConfig) {
    const used = new Set(
      [result.titleField, result.subtitleField].filter(Boolean) as string[],
    )
    result.displayFields = visibleFields
      .filter((f) => !used.has(f.name))
      .slice(0, 3)
      .map((f) => f.name)
  }

  if ('searchFields' in defaultConfig) {
    result.searchFields = visibleFields
      .filter((f) => SEARCHABLE_TYPES.has(f.type))
      .map((f) => f.name)
  }

  if ('columns' in defaultConfig && Array.isArray(defaultConfig.columns)) {
    result.columns = visibleFields
      .filter((f) => !LONG_TEXT_TYPES.has(f.type))
      .map((f) => ({ field: f.name }))
  }

  return result
}

/**
 * Produce a merged styleConfig for the target style.
 *
 * Merge order (least → most authoritative):
 * 1. registration.defaultStyleConfig
 * 2. Inferred values (per-style inferConfig or built-in heuristic)
 * 3. savedStyleConfig (intentional human/AI-authored config)
 */
export function inferStyleConfig(options: InferStyleConfigOptions): Record<string, unknown> {
  const { registration, metadata, savedStyleConfig } = options

  const inferred = registration.inferConfig
    ? registration.inferConfig(metadata)
    : builtinInfer(registration.defaultStyleConfig as Record<string, unknown>, metadata)

  return {
    ...(registration.defaultStyleConfig as Record<string, unknown>),
    ...inferred,
    ...(savedStyleConfig ?? {}),
  }
}
