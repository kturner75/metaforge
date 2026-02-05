/**
 * KpiCard — presentation component for the "aggregate/kpi-card" style.
 *
 * Displays a single aggregate measure as a large-format KPI card.
 * Does NOT own data fetching — receives data through props.
 */

import type { PresentationProps } from '@/lib/viewTypes'

export interface KpiCardStyleConfig {
  /** Label displayed above the value */
  label: string
  /** Which measure result field to display as the primary value */
  valueField: string
  /** Optional format: "number", "percent", "currency" */
  format?: string
  /** Optional icon or emoji displayed alongside the label */
  icon?: string
  /** Optional CSS color for a left-border accent */
  accentColor?: string
}

function formatValue(raw: unknown, format?: string): string {
  if (raw === null || raw === undefined) return '\u2014'
  const num = typeof raw === 'number' ? raw : Number(raw)
  if (isNaN(num)) return String(raw)

  switch (format) {
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

export function KpiCard({
  data,
  styleConfig,
  isLoading,
  error,
}: PresentationProps<KpiCardStyleConfig>) {
  if (isLoading) {
    return <div className="kpi-card kpi-card-loading">Loading...</div>
  }

  if (error) {
    return <div className="kpi-card kpi-card-error">{error}</div>
  }

  const row = data?.data?.[0]
  const rawValue = row ? row[styleConfig.valueField] : undefined
  const displayValue = formatValue(rawValue, styleConfig.format)

  const accentStyle = styleConfig.accentColor
    ? { borderLeftColor: styleConfig.accentColor }
    : undefined

  return (
    <div className="kpi-card" style={accentStyle}>
      <div className="kpi-card-header">
        {styleConfig.icon && (
          <span className="kpi-card-icon">{styleConfig.icon}</span>
        )}
        <span className="kpi-card-label">{styleConfig.label}</span>
      </div>
      <div className="kpi-card-value">{displayValue}</div>
    </div>
  )
}
