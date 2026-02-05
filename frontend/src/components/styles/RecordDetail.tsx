/**
 * RecordDetail — presentation component for the "record/detail" style.
 *
 * Displays a single entity record's fields in a structured read-only
 * layout with optional sections. If no sections are configured, all
 * visible non-auto fields are shown in a single section.
 *
 * Does NOT own data fetching — receives data through props.
 */

import { useMemo } from 'react'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { PresentationProps } from '@/lib/viewTypes'
import type { FieldMetadata } from '@/lib/types'

export interface DetailSection {
  /** Section header label (omit for ungrouped) */
  label?: string
  /** Field names to display in this section */
  fields: string[]
  /** Number of columns (1 or 2, default 2) */
  columns?: 1 | 2
}

export interface DetailStyleConfig {
  /** Grouped field layout. If omitted, all visible fields are shown. */
  sections?: DetailSection[]
}

const AUTO_FIELD_NAMES = new Set([
  'id', 'tenantId', 'createdAt', 'updatedAt', 'createdBy', 'updatedBy',
])

function isAutoField(field: FieldMetadata): boolean {
  return field.primaryKey === true || AUTO_FIELD_NAMES.has(field.name)
}

export function RecordDetail({
  data,
  metadata,
  styleConfig,
  isLoading,
  error,
}: PresentationProps<DetailStyleConfig>) {
  const record = data?.data?.[0] ?? null

  // Build sections: either from config or auto-generate from metadata
  const sections: { label?: string; fieldsMeta: FieldMetadata[]; columns: number }[] = useMemo(() => {
    if (!metadata) return []

    if (styleConfig.sections && styleConfig.sections.length > 0) {
      return styleConfig.sections.map((section) => ({
        label: section.label,
        columns: section.columns ?? 2,
        fieldsMeta: section.fields
          .map((name) => metadata.fields.find((f) => f.name === name))
          .filter(Boolean) as FieldMetadata[],
      }))
    }

    // Auto-generate: all visible non-auto fields in one section
    const visibleFields = metadata.fields.filter((f) => !isAutoField(f))
    return [
      {
        label: undefined,
        columns: 2,
        fieldsMeta: visibleFields,
      },
    ]
  }, [metadata, styleConfig.sections])

  /** For relation fields, prefer the hydrated display value over the raw ID. */
  const fieldValue = (row: Record<string, unknown>, field: FieldMetadata) =>
    field.type === 'relation'
      ? (row[`${field.name}_display`] ?? row[field.name])
      : row[field.name]

  if (error) {
    return <div className="error">{error}</div>
  }

  if (!metadata) {
    return <div className="error">Entity not found</div>
  }

  if (isLoading) {
    return (
      <div className="record-detail">
        <div className="record-detail-loading">Loading...</div>
      </div>
    )
  }

  if (!record) {
    return (
      <div className="record-detail">
        <div className="record-detail-empty">Record not found</div>
      </div>
    )
  }

  return (
    <div className="record-detail">
      {sections.map((section, sectionIndex) => (
        <div key={sectionIndex} className="record-detail-section">
          {section.label && (
            <div className="record-detail-section-header">{section.label}</div>
          )}
          <div
            className="record-detail-fields"
            style={{ '--detail-columns': section.columns } as React.CSSProperties}
          >
            {section.fieldsMeta.map((field) => (
              <div key={field.name} className="record-detail-field">
                <span className="record-detail-label">{field.displayName}</span>
                <span className="record-detail-value">
                  <FieldRenderer
                    field={field}
                    context="display"
                    value={fieldValue(record, field)}
                  />
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
