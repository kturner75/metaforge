/**
 * TreeView — presentation component for the "query/tree" style.
 *
 * Renders a hierarchical tree of records using a self-referential
 * parent field (e.g., parentId → same entity). Records are fetched
 * via the query pattern with a high page size, then assembled into
 * a tree structure client-side.
 *
 * Does NOT own data fetching — receives data through props.
 */

import { useState, useMemo } from 'react'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { PresentationProps } from '@/lib/viewTypes'
import type { FieldMetadata } from '@/lib/types'

export interface TreeStyleConfig {
  /** Field name shown as the node label */
  titleField: string
  /** Self-referential FK field that points to the parent record */
  parentField: string
  /** Additional field names shown inline on each node */
  detailFields?: string[]
  /** Indent pixels per tree level (default: 24) */
  indentPx?: number
}

interface TreeNode {
  row: Record<string, unknown>
  children: TreeNode[]
}

export function TreeView({
  data,
  metadata,
  styleConfig,
  isLoading,
  error,
  compact,
  onRowClick,
}: PresentationProps<TreeStyleConfig>) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())

  const { titleField, parentField, detailFields, indentPx = 24 } = styleConfig
  const effectiveIndent = compact ? Math.min(indentPx, 16) : indentPx

  // Resolve field metadata
  const titleMeta = useMemo(
    () => metadata?.fields.find((f) => f.name === titleField),
    [metadata, titleField],
  )
  const detailMetas: FieldMetadata[] = useMemo(() => {
    if (!metadata || !detailFields) return []
    if (compact) return [] // hide details in compact mode
    return detailFields
      .map((name) => metadata.fields.find((f) => f.name === name))
      .filter(Boolean) as FieldMetadata[]
  }, [metadata, detailFields, compact])

  // Build tree from flat rows
  const roots = useMemo(() => {
    const rows = data?.data ?? []
    if (rows.length === 0) return []

    // Index rows by id
    const byId = new Map<string, TreeNode>()
    for (const row of rows) {
      byId.set(String(row.id), { row, children: [] })
    }

    const rootNodes: TreeNode[] = []
    for (const row of rows) {
      const parentId = row[parentField]
      const node = byId.get(String(row.id))!
      if (parentId && byId.has(String(parentId))) {
        byId.get(String(parentId))!.children.push(node)
      } else {
        rootNodes.push(node)
      }
    }

    return rootNodes
  }, [data, parentField])

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const expandAll = () => {
    const allIds = (data?.data ?? []).map((row) => String(row.id))
    setExpanded(new Set(allIds))
  }

  const collapseAll = () => {
    setExpanded(new Set())
  }

  /** For relation fields, prefer the hydrated display value over the raw ID. */
  const fieldValue = (row: Record<string, unknown>, field: FieldMetadata) =>
    field.type === 'relation'
      ? (row[`${field.name}_display`] ?? row[field.name])
      : row[field.name]

  if (isLoading) {
    return <div className="tree-container tree-loading">Loading...</div>
  }

  if (error) {
    return <div className="tree-container tree-error">{error}</div>
  }

  if (roots.length === 0) {
    return <div className="tree-container tree-empty">No data</div>
  }

  function renderNode(node: TreeNode, depth: number): React.ReactNode {
    const id = String(node.row.id)
    const hasChildren = node.children.length > 0
    const isExpanded = expanded.has(id)

    return (
      <div key={id} className="tree-node">
        <div
          className={`tree-node-row${onRowClick ? ' clickable' : ''}`}
          style={{ paddingLeft: `${depth * effectiveIndent}px` }}
        >
          <button
            className={`tree-toggle${isExpanded ? ' expanded' : ''}${hasChildren ? '' : ' invisible'}`}
            onClick={(e) => {
              e.stopPropagation()
              toggle(id)
            }}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            &#9654;
          </button>
          <span
            className="tree-node-title"
            onClick={() => onRowClick?.(node.row)}
          >
            {titleMeta ? (
              <FieldRenderer field={titleMeta} context="display" value={fieldValue(node.row, titleMeta)} />
            ) : (
              String(node.row[titleField] ?? '')
            )}
          </span>
          {detailMetas.length > 0 && (
            <span className="tree-node-details">
              {detailMetas.map((field) => (
                <span key={field.name} className="tree-node-detail">
                  <span className="tree-node-detail-label">{field.displayName}:</span>{' '}
                  <FieldRenderer field={field} context="display" value={fieldValue(node.row, field)} />
                </span>
              ))}
            </span>
          )}
        </div>
        {hasChildren && isExpanded && (
          <div className="tree-children">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={`tree-container${compact ? ' compact' : ''}`}>
      <div className="tree-toolbar">
        <button className="tree-toolbar-btn" onClick={expandAll}>
          Expand All
        </button>
        <button className="tree-toolbar-btn" onClick={collapseAll}>
          Collapse All
        </button>
      </div>
      <div className="tree-body">
        {roots.map((node) => renderNode(node, 0))}
      </div>
    </div>
  )
}
