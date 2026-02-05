/**
 * SummaryGrid — presentation component for the "aggregate/summary-grid" style.
 *
 * Renders grouped aggregate data as an HTML table with an optional totals row.
 * Does NOT own data fetching — receives data through props.
 */

import type { PresentationProps } from '@/lib/viewTypes'

export interface SummaryGridStyleConfig {
  /** Which groupBy columns to show (all if omitted) */
  dimensionFields?: string[]
  /** Which measure columns to show (all if omitted) */
  measureFields?: string[]
  /** Show a totals row at the bottom (default: true) */
  showTotals?: boolean
  /** Per-column format overrides: { columnName: 'number' | 'percent' | 'currency' } */
  format?: Record<string, string>
}

function formatCell(raw: unknown, fmt?: string): string {
  if (raw === null || raw === undefined) return '\u2014'
  const num = typeof raw === 'number' ? raw : Number(raw)
  if (isNaN(num)) return String(raw)

  switch (fmt) {
    case 'number':
      return num.toLocaleString()
    case 'percent':
      return `${num.toLocaleString()}%`
    case 'currency':
      return num.toLocaleString(undefined, { style: 'currency', currency: 'USD' })
    default:
      return String(raw)
  }
}

function titleCase(s: string): string {
  return s
    .replace(/([A-Z])/g, ' $1')
    .replace(/_/g, ' ')
    .replace(/^\w/, (c) => c.toUpperCase())
    .trim()
}

export function SummaryGrid({
  data,
  dataConfig,
  styleConfig,
  isLoading,
  error,
}: PresentationProps<SummaryGridStyleConfig>) {
  if (isLoading) {
    return <div className="summary-grid-container summary-grid-loading">Loading...</div>
  }

  if (error) {
    return <div className="summary-grid-container summary-grid-error">{error}</div>
  }

  const rows = data?.data ?? []
  if (rows.length === 0) {
    return <div className="summary-grid-container summary-grid-empty">No data</div>
  }

  const { showTotals = true, format = {} } = styleConfig

  // Determine dimension and measure columns from config or data
  const groupByFields = styleConfig.dimensionFields
    ?? dataConfig.groupBy
    ?? []

  const allKeys = rows.length > 0 ? Object.keys(rows[0]) : []
  const groupBySet = new Set(groupByFields)
  const inferredMeasureFields = allKeys.filter((k) => !groupBySet.has(k))

  const measureFields = styleConfig.measureFields ?? inferredMeasureFields

  // Compute totals
  const totals: Record<string, number> = {}
  if (showTotals) {
    for (const mf of measureFields) {
      let sum = 0
      for (const row of rows) {
        const v = row[mf]
        const n = typeof v === 'number' ? v : Number(v)
        if (!isNaN(n)) sum += n
      }
      totals[mf] = sum
    }
  }

  return (
    <div className="summary-grid-container">
      <table className="summary-grid-table">
        <thead>
          <tr>
            {groupByFields.map((col) => (
              <th key={col} className="summary-grid-th summary-grid-dim-th">
                {titleCase(col)}
              </th>
            ))}
            {measureFields.map((col) => (
              <th key={col} className="summary-grid-th summary-grid-measure-th">
                {titleCase(col)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="summary-grid-row">
              {groupByFields.map((col) => (
                <td key={col} className="summary-grid-td summary-grid-dim-td">
                  {String(row[col] ?? '\u2014')}
                </td>
              ))}
              {measureFields.map((col) => (
                <td key={col} className="summary-grid-td summary-grid-measure-td">
                  {formatCell(row[col], format[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {showTotals && (
          <tfoot>
            <tr className="summary-grid-totals-row">
              {groupByFields.map((col, i) => (
                <td key={col} className="summary-grid-td summary-grid-totals-td">
                  {i === 0 ? 'Total' : ''}
                </td>
              ))}
              {measureFields.map((col) => (
                <td key={col} className="summary-grid-td summary-grid-totals-td summary-grid-measure-td">
                  {formatCell(totals[col], format[col])}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}
