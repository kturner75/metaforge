/**
 * Utilities for working with entity metadata and records.
 */

import type { EntityMetadata } from './types'

/**
 * Return the field name to use as a record's human-readable label
 * (e.g. for breadcrumbs, titles, relation display).
 *
 * Priority:
 * 1. Explicit `labelField` from entity metadata (set in YAML)
 * 2. First field with type 'name' found in the field list
 * 3. Falls back to 'id'
 */
export function getLabelField(metadata: EntityMetadata | undefined): string {
  if (metadata?.labelField) return metadata.labelField
  const nameField = metadata?.fields.find(f => f.type === 'name')
  return nameField?.name ?? 'id'
}

/**
 * Extract the human-readable label for a record using the entity's label field.
 * Returns undefined if the record or its label value is not available yet.
 */
export function getRecordLabel(
  record: Record<string, unknown> | undefined,
  metadata: EntityMetadata | undefined
): string | undefined {
  if (!record) return undefined
  const fieldName = getLabelField(metadata)
  const val = record[fieldName]
  return val != null ? String(val) : undefined
}
