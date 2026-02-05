/**
 * KanbanBoard — presentation component for the "query/kanban" style.
 *
 * Groups records into vertical lanes by a picklist field value.
 * Each card shows title, subtitle, and optional detail fields.
 * Read-only for now — drag-to-update will be added in a future iteration.
 *
 * Does NOT own data fetching — receives data through props.
 */

import { useMemo } from 'react'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { PresentationProps } from '@/lib/viewTypes'
import type { FieldMetadata } from '@/lib/types'

export interface KanbanStyleConfig {
  /** Picklist field whose values become lane columns */
  laneField: string
  /** Field to use as the card title */
  titleField: string
  /** Field for the secondary line on each card */
  subtitleField?: string
  /** Fields to show as key-value pairs in the card body */
  detailFields?: string[]
}

interface Lane {
  value: string
  label: string
  rows: Record<string, unknown>[]
}

export function KanbanBoard({
  data,
  metadata,
  styleConfig,
  dataConfig,
  isLoading,
  error,
  compact,
  onPageChange,
  onRowClick,
}: PresentationProps<KanbanStyleConfig>) {
  // --- Resolve field metadata ---

  const laneFieldMeta = useMemo(
    () => metadata?.fields.find((f) => f.name === styleConfig.laneField) ?? null,
    [metadata, styleConfig.laneField],
  )

  const titleFieldMeta = useMemo(
    () => metadata?.fields.find((f) => f.name === styleConfig.titleField) ?? null,
    [metadata, styleConfig.titleField],
  )

  const subtitleFieldMeta = useMemo(
    () =>
      styleConfig.subtitleField
        ? metadata?.fields.find((f) => f.name === styleConfig.subtitleField) ?? null
        : null,
    [metadata, styleConfig.subtitleField],
  )

  const detailFieldsMeta = useMemo((): FieldMetadata[] => {
    if (!metadata || !styleConfig.detailFields) return []
    return styleConfig.detailFields
      .map((name) => metadata.fields.find((f) => f.name === name))
      .filter(Boolean) as FieldMetadata[]
  }, [metadata, styleConfig.detailFields])

  // --- Group rows into lanes ---

  const lanes: Lane[] = useMemo(() => {
    const rows = data?.data ?? []
    if (!laneFieldMeta) return []

    // Picklist options define lane order and labels
    const options = laneFieldMeta.options ?? []
    const optionValues = new Set(options.map((o) => o.value))

    // Build a map: option value → rows
    const grouped = new Map<string, Record<string, unknown>[]>()
    for (const opt of options) {
      grouped.set(opt.value, [])
    }

    const unset: Record<string, unknown>[] = []
    const other: Record<string, unknown>[] = []

    for (const row of rows) {
      const val = row[styleConfig.laneField]
      if (val == null || val === '') {
        unset.push(row)
      } else {
        const strVal = String(val)
        if (optionValues.has(strVal)) {
          grouped.get(strVal)!.push(row)
        } else {
          other.push(row)
        }
      }
    }

    // Build ordered lane array from picklist options
    const result: Lane[] = options.map((opt) => ({
      value: opt.value,
      label: opt.label,
      rows: grouped.get(opt.value) ?? [],
    }))

    // Append catch-all lanes only if non-empty
    if (unset.length > 0) {
      result.push({ value: '__unset__', label: 'Unset', rows: unset })
    }
    if (other.length > 0) {
      result.push({ value: '__other__', label: 'Other', rows: other })
    }

    return result
  }, [data?.data, laneFieldMeta, styleConfig.laneField])

  // --- Helpers ---

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

  if (!laneFieldMeta) {
    return <div className="error">Lane field &quot;{styleConfig.laneField}&quot; not found</div>
  }

  const pageSize = dataConfig.pageSize ?? 100
  const offset = data?.pagination?.offset ?? 0
  const total = data?.pagination?.total ?? 0
  const hasMore = data?.pagination?.hasMore ?? false

  return (
    <div className={`kanban-container${compact ? ' compact' : ''}`}>
      {isLoading ? (
        <div className="kanban-loading">Loading...</div>
      ) : lanes.every((l) => l.rows.length === 0) ? (
        <div className="kanban-empty">No records found</div>
      ) : (
        <div className="kanban-board">
          {lanes.map((lane) => (
            <div key={lane.value} className="kanban-lane">
              <div className="kanban-lane-header">
                <span className="kanban-lane-label">{lane.label}</span>
                <span className="kanban-lane-count">{lane.rows.length}</span>
              </div>
              <div className="kanban-lane-body">
                {lane.rows.map((row, index) => (
                  <div
                    key={(row[metadata.primaryKey] as string) ?? index}
                    className={`kanban-card${onRowClick ? ' clickable' : ''}`}
                    onClick={() => onRowClick?.(row)}
                  >
                    {titleFieldMeta && (
                      <div className="kanban-card-title">
                        <FieldRenderer
                          field={titleFieldMeta}
                          context="display"
                          value={fieldValue(row, titleFieldMeta)}
                        />
                      </div>
                    )}

                    {subtitleFieldMeta && (
                      <div className="kanban-card-subtitle">
                        <FieldRenderer
                          field={subtitleFieldMeta}
                          context="display"
                          value={fieldValue(row, subtitleFieldMeta)}
                        />
                      </div>
                    )}

                    {detailFieldsMeta.length > 0 && (
                      <div className="kanban-card-details">
                        {detailFieldsMeta.map((field) => (
                          <div key={field.name} className="kanban-card-detail-row">
                            <span className="kanban-card-detail-label">
                              {field.displayName}
                            </span>
                            <span className="kanban-card-detail-value">
                              <FieldRenderer
                                field={field}
                                context="display"
                                value={fieldValue(row, field)}
                              />
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {data && total > 0 && (
        compact ? (
          <div className="compact-footer">
            <span>{Math.min(data.data.length, pageSize)} of {total}</span>
            {hasMore && <span className="compact-footer-more">View All</span>}
          </div>
        ) : (
          <div className="pagination">
            <span>
              Showing {offset + 1} - {Math.min(offset + pageSize, total)} of {total}
            </span>
            <div className="pagination-buttons">
              <button
                disabled={offset === 0}
                onClick={() => onPageChange?.(Math.max(0, offset - pageSize))}
              >
                Previous
              </button>
              <button
                disabled={!hasMore}
                onClick={() => onPageChange?.(offset + pageSize)}
              >
                Next
              </button>
            </div>
          </div>
        )
      )}
    </div>
  )
}
