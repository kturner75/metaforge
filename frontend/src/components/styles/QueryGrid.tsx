/**
 * QueryGrid — presentation component for the "query/grid" style.
 *
 * Renders a table with sortable headers, field-type-aware cells via FieldRenderer,
 * and pagination controls. Does NOT own data fetching — receives data through props.
 *
 * When styleConfig.columns is provided, uses that for column order/visibility/pinning.
 * Otherwise falls back to metadata fields (excluding primaryKey).
 */

import { useMemo } from 'react'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { PresentationProps } from '@/lib/viewTypes'
import type { FieldMetadata, SortField } from '@/lib/types'

export interface GridColumn {
  field: string
  width?: string | number
  visible?: boolean
  sortable?: boolean
  filterable?: boolean
  pinned?: 'left' | 'right' | null
}

export interface GridStyleConfig {
  columns?: GridColumn[]
  selectable?: boolean
  inlineEdit?: boolean
}

export function QueryGrid({
  data,
  metadata,
  styleConfig,
  dataConfig,
  isLoading,
  error,
  compact,
  onSort,
  onPageChange,
  onRowClick,
}: PresentationProps<GridStyleConfig>) {
  // Resolve visible fields from styleConfig.columns or metadata
  const visibleFields = useMemo(() => {
    if (!metadata) return []

    if (styleConfig.columns?.length) {
      return styleConfig.columns
        .filter((col) => col.visible !== false)
        .map((col) => {
          const fieldMeta = metadata.fields.find((f) => f.name === col.field)
          return fieldMeta ? { field: fieldMeta, column: col } : null
        })
        .filter(Boolean) as { field: FieldMetadata; column: GridColumn }[]
    }

    // Fallback: all fields except primary key
    return metadata.fields
      .filter((f) => !f.primaryKey)
      .map((f) => ({ field: f, column: { field: f.name } as GridColumn }))
  }, [metadata, styleConfig.columns])

  // Current sort state derived from dataConfig
  const currentSort: SortField[] = dataConfig.sort ?? []

  const handleSort = (fieldName: string) => {
    if (!onSort) return
    const existing = currentSort.find((s) => s.field === fieldName)
    if (!existing) {
      onSort([{ field: fieldName, direction: 'asc' }])
    } else if (existing.direction === 'asc') {
      onSort([{ field: fieldName, direction: 'desc' }])
    } else {
      onSort([])
    }
  }

  const getSortIndicator = (fieldName: string) => {
    const s = currentSort.find((s) => s.field === fieldName)
    if (!s) return ''
    return s.direction === 'asc' ? ' ↑' : ' ↓'
  }

  if (error) {
    return <div className="error">{error}</div>
  }

  if (!metadata) {
    return <div className="error">Entity not found</div>
  }

  const pageSize = dataConfig.pageSize ?? 25
  const offset = data?.pagination?.offset ?? 0
  const total = data?.pagination?.total ?? 0
  const hasMore = data?.pagination?.hasMore ?? false

  return (
    <div className={`entity-grid${compact ? ' compact' : ''}`}>
      <table>
        <thead>
          <tr>
            {visibleFields.map(({ field, column }) => (
              <th
                key={field.name}
                onClick={() => handleSort(field.name)}
                className="sortable"
                style={{
                  textAlign: field.ui.grid.alignment as 'left' | 'right' | undefined,
                  ...(column.width ? { width: column.width } : {}),
                }}
              >
                {field.displayName}
                {getSortIndicator(field.name)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr>
              <td colSpan={visibleFields.length} className="loading">
                Loading...
              </td>
            </tr>
          ) : data?.data.length === 0 ? (
            <tr>
              <td colSpan={visibleFields.length} className="empty">
                No records found
              </td>
            </tr>
          ) : (
            data?.data.map((row, index) => (
              <tr
                key={(row[metadata.primaryKey] as string) ?? index}
                onClick={() => onRowClick?.(row)}
                className={onRowClick ? 'clickable' : undefined}
              >
                {visibleFields.map(({ field }) => {
                  // For relation fields, prefer the hydrated display value
                  const value = field.type === 'relation'
                    ? (row[`${field.name}_display`] ?? row[field.name])
                    : row[field.name]

                  return (
                    <td
                      key={field.name}
                      style={{ textAlign: field.ui.grid.alignment as 'left' | 'right' | undefined }}
                    >
                      <FieldRenderer field={field} context="grid" value={value} />
                    </td>
                  )
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>

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
