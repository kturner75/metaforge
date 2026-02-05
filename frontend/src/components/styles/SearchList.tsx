/**
 * SearchList — presentation component for the "query/search-list" style.
 *
 * Renders records as a compact vertical list with a built-in text search
 * input that filters rows client-side. Each row shows a primary field,
 * secondary fields joined by · separators, and an optional status badge.
 *
 * Does NOT own data fetching — receives data through props.
 */

import { useState, useMemo } from 'react'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { PresentationProps } from '@/lib/viewTypes'
import type { FieldMetadata } from '@/lib/types'

export interface SearchListStyleConfig {
  /** Field to use as the primary text for each row */
  titleField: string
  /** Field for the secondary line */
  subtitleField?: string
  /** Fields to search across (client-side text match). Defaults to title + subtitle. */
  searchFields?: string[]
  /** Additional fields shown inline on the subtitle line, joined by · */
  displayFields?: string[]
  /** Field to show as a status badge on the right side */
  statusField?: string
}

export function SearchList({
  data,
  metadata,
  styleConfig,
  dataConfig,
  isLoading,
  error,
  compact,
  onPageChange,
  onRowClick,
}: PresentationProps<SearchListStyleConfig>) {
  const [searchTerm, setSearchTerm] = useState('')

  // --- Resolve field metadata from styleConfig field names ---

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

  const displayFieldsMeta = useMemo((): FieldMetadata[] => {
    if (!metadata || !styleConfig.displayFields) return []
    return styleConfig.displayFields
      .map((name) => metadata.fields.find((f) => f.name === name))
      .filter(Boolean) as FieldMetadata[]
  }, [metadata, styleConfig.displayFields])

  const statusFieldMeta = useMemo(
    () =>
      styleConfig.statusField
        ? metadata?.fields.find((f) => f.name === styleConfig.statusField) ?? null
        : null,
    [metadata, styleConfig.statusField],
  )

  // --- Determine which fields to search ---

  const effectiveSearchFields = useMemo(() => {
    if (styleConfig.searchFields && styleConfig.searchFields.length > 0) {
      return styleConfig.searchFields
    }
    // Default: search across title and subtitle fields
    return [styleConfig.titleField, styleConfig.subtitleField].filter(Boolean) as string[]
  }, [styleConfig.searchFields, styleConfig.titleField, styleConfig.subtitleField])

  // --- Client-side filtering ---

  const filteredRows = useMemo(() => {
    const rows = data?.data ?? []
    if (!searchTerm.trim()) return rows

    const term = searchTerm.toLowerCase()
    return rows.filter((row) =>
      effectiveSearchFields.some((fieldName) => {
        // Prefer hydrated display value for relation fields
        const val = row[`${fieldName}_display`] ?? row[fieldName]
        if (val == null) return false
        return String(val).toLowerCase().includes(term)
      }),
    )
  }, [data?.data, searchTerm, effectiveSearchFields])

  // --- Helpers ---

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

  const pageSize = dataConfig.pageSize ?? 25
  const offset = data?.pagination?.offset ?? 0
  const total = data?.pagination?.total ?? 0
  const hasMore = data?.pagination?.hasMore ?? false

  const entityLabel = metadata.pluralName || metadata.entity

  return (
    <div className={`search-list-container${compact ? ' compact' : ''}`}>
      <div className="search-list-search">
        <input
          type="text"
          placeholder={`Search ${entityLabel.toLowerCase()}...`}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="search-list-input"
        />
      </div>

      <div className="search-list">
        {isLoading ? (
          <div className="search-list-loading">Loading...</div>
        ) : filteredRows.length === 0 ? (
          <div className="search-list-empty">
            {searchTerm ? 'No matching records' : 'No records found'}
          </div>
        ) : (
          filteredRows.map((row, index) => (
            <div
              key={(row[metadata.primaryKey] as string) ?? index}
              className={`search-list-item${onRowClick ? ' clickable' : ''}`}
              onClick={() => onRowClick?.(row)}
            >
              <div className="search-list-item-content">
                {titleFieldMeta && (
                  <div className="search-list-item-title">
                    <FieldRenderer
                      field={titleFieldMeta}
                      context="display"
                      value={fieldValue(row, titleFieldMeta)}
                    />
                  </div>
                )}

                {(subtitleFieldMeta || displayFieldsMeta.length > 0) && (
                  <div className="search-list-item-meta">
                    {subtitleFieldMeta && (
                      <span className="search-list-meta-item">
                        <FieldRenderer
                          field={subtitleFieldMeta}
                          context="display"
                          value={fieldValue(row, subtitleFieldMeta)}
                        />
                      </span>
                    )}
                    {displayFieldsMeta.map((field) => {
                      const val = fieldValue(row, field)
                      if (val == null || val === '') return null
                      return (
                        <span key={field.name} className="search-list-meta-item">
                          <FieldRenderer
                            field={field}
                            context="display"
                            value={val}
                          />
                        </span>
                      )
                    })}
                  </div>
                )}
              </div>

              {statusFieldMeta && row[statusFieldMeta.name] != null && (
                <div className="search-list-item-status">
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
              {searchTerm
                ? `${filteredRows.length} of ${total} shown`
                : `Showing ${offset + 1} - ${Math.min(offset + pageSize, total)} of ${total}`}
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
