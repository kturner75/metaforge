/**
 * EntityGrid - renders a data grid for an entity using metadata.
 */

import { useState, useMemo } from 'react'
import { useEntityMetadata, useEntityQuery } from '@/hooks/useApi'
import { FieldRenderer } from './FieldRenderer'
import type { FilterGroup, SortField } from '@/lib/types'

interface EntityGridProps {
  entity: string
  fields?: string[]
  defaultFilter?: FilterGroup
  defaultSort?: SortField[]
  onRowClick?: (row: Record<string, unknown>) => void
}

export function EntityGrid({
  entity,
  fields: fieldOverride,
  defaultFilter,
  defaultSort,
  onRowClick,
}: EntityGridProps) {
  const { data: metadata, isLoading: metadataLoading } = useEntityMetadata(entity)

  const [sort, setSort] = useState<SortField[]>(defaultSort ?? [])
  const [pagination, setPagination] = useState({ limit: 25, offset: 0 })

  const { data: queryResult, isLoading: dataLoading } = useEntityQuery(entity, {
    fields: fieldOverride,
    filter: defaultFilter,
    sort,
    ...pagination,
  })

  // Determine visible fields (exclude primary key by default)
  const visibleFields = useMemo(() => {
    if (!metadata) return []

    const fields = fieldOverride
      ? metadata.fields.filter((f) => fieldOverride.includes(f.name))
      : metadata.fields

    return fields.filter((f) => !f.primaryKey)
  }, [metadata, fieldOverride])

  const handleSort = (fieldName: string) => {
    setSort((current) => {
      const existing = current.find((s) => s.field === fieldName)
      if (!existing) {
        return [{ field: fieldName, direction: 'asc' }]
      }
      if (existing.direction === 'asc') {
        return [{ field: fieldName, direction: 'desc' }]
      }
      return []
    })
  }

  const getSortIndicator = (fieldName: string) => {
    const s = sort.find((s) => s.field === fieldName)
    if (!s) return ''
    return s.direction === 'asc' ? ' ↑' : ' ↓'
  }

  if (metadataLoading) {
    return <div className="loading">Loading metadata...</div>
  }

  if (!metadata) {
    return <div className="error">Entity not found</div>
  }

  return (
    <div className="entity-grid">
      <table>
        <thead>
          <tr>
            {visibleFields.map((field) => (
              <th
                key={field.name}
                onClick={() => handleSort(field.name)}
                className="sortable"
                style={{ textAlign: field.ui.grid.alignment as 'left' | 'right' | undefined }}
              >
                {field.displayName}
                {getSortIndicator(field.name)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dataLoading ? (
            <tr>
              <td colSpan={visibleFields.length} className="loading">
                Loading...
              </td>
            </tr>
          ) : queryResult?.data.length === 0 ? (
            <tr>
              <td colSpan={visibleFields.length} className="empty">
                No records found
              </td>
            </tr>
          ) : (
            queryResult?.data.map((row, index) => (
              <tr
                key={(row[metadata.primaryKey] as string) ?? index}
                onClick={() => onRowClick?.(row)}
                className={onRowClick ? 'clickable' : undefined}
              >
                {visibleFields.map((field) => {
                  // For relation fields, prefer the hydrated display value
                  const value = field.type === 'relation'
                    ? (row[`${field.name}_display`] ?? row[field.name])
                    : row[field.name]

                  return (
                    <td
                      key={field.name}
                      style={{ textAlign: field.ui.grid.alignment as 'left' | 'right' | undefined }}
                    >
                      <FieldRenderer
                        field={field}
                        context="grid"
                        value={value}
                      />
                    </td>
                  )
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>

      {queryResult && (
        <div className="pagination">
          <span>
            Showing {pagination.offset + 1} - {Math.min(pagination.offset + pagination.limit, queryResult.pagination.total)} of {queryResult.pagination.total}
          </span>
          <div className="pagination-buttons">
            <button
              disabled={pagination.offset === 0}
              onClick={() => setPagination((p) => ({ ...p, offset: Math.max(0, p.offset - p.limit) }))}
            >
              Previous
            </button>
            <button
              disabled={!queryResult.pagination.hasMore}
              onClick={() => setPagination((p) => ({ ...p, offset: p.offset + p.limit }))}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
