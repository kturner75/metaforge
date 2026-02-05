/**
 * CardList — presentation component for the "query/card-list" style.
 *
 * Renders records as a grid of cards instead of table rows.
 * Does NOT own data fetching — receives data through props.
 */

import { useMemo } from 'react'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { PresentationProps } from '@/lib/viewTypes'
import type { FieldMetadata } from '@/lib/types'

export interface CardListStyleConfig {
  /** Field to use as the card title */
  titleField: string
  /** Field to use as subtitle/secondary line */
  subtitleField?: string
  /** Fields to show in the card body as key-value pairs */
  detailFields?: string[]
  /** Number of columns in the card grid (default 3) */
  columns?: number
  /** Field to show as a status badge on each card */
  statusField?: string
}

export function CardList({
  data,
  metadata,
  styleConfig,
  dataConfig,
  isLoading,
  error,
  compact,
  onPageChange,
  onRowClick,
}: PresentationProps<CardListStyleConfig>) {
  const columns = styleConfig.columns ?? 3

  // Resolve field metadata for configured fields
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

  const statusFieldMeta = useMemo(
    () =>
      styleConfig.statusField
        ? metadata?.fields.find((f) => f.name === styleConfig.statusField) ?? null
        : null,
    [metadata, styleConfig.statusField],
  )

  if (error) {
    return <div className="error">{error}</div>
  }

  if (!metadata) {
    return <div className="error">Entity not found</div>
  }

  /** For relation fields, prefer the hydrated display value over the raw ID. */
  const fieldValue = (row: Record<string, unknown>, field: FieldMetadata) =>
    field.type === 'relation'
      ? (row[`${field.name}_display`] ?? row[field.name])
      : row[field.name]

  const pageSize = dataConfig.pageSize ?? 25
  const offset = data?.pagination?.offset ?? 0
  const total = data?.pagination?.total ?? 0
  const hasMore = data?.pagination?.hasMore ?? false

  return (
    <div className={`card-list-container${compact ? ' compact' : ''}`}>
      <div
        className="card-list"
        style={{ '--card-columns': columns } as React.CSSProperties}
      >
        {isLoading ? (
          <div className="card-list-loading">Loading...</div>
        ) : data?.data.length === 0 ? (
          <div className="card-list-empty">No records found</div>
        ) : (
          data?.data.map((row, index) => (
            <div
              key={(row[metadata.primaryKey] as string) ?? index}
              className={`card-list-item${onRowClick ? ' clickable' : ''}`}
              onClick={() => onRowClick?.(row)}
            >
              {titleFieldMeta && (
                <div className="card-list-item-title">
                  <FieldRenderer
                    field={titleFieldMeta}
                    context="display"
                    value={fieldValue(row, titleFieldMeta)}
                  />
                </div>
              )}

              {subtitleFieldMeta && (
                <div className="card-list-item-subtitle">
                  <FieldRenderer
                    field={subtitleFieldMeta}
                    context="display"
                    value={fieldValue(row, subtitleFieldMeta)}
                  />
                </div>
              )}

              {detailFieldsMeta.length > 0 && (
                <div className="card-list-item-details">
                  {detailFieldsMeta.map((field) => (
                    <div key={field.name} className="card-list-detail-row">
                      <span className="card-list-detail-label">
                        {field.displayName}
                      </span>
                      <span className="card-list-detail-value">
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

              {statusFieldMeta && row[statusFieldMeta.name] != null && (
                <div className="card-list-item-status">
                  <FieldRenderer
                    field={statusFieldMeta}
                    context="grid"
                    value={fieldValue(row, statusFieldMeta)}
                  />
                </div>
              )}
            </div>
          ))
        )}
      </div>

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
