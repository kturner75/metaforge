/**
 * TimeSeries — presentation component for the "aggregate/time-series" style.
 *
 * Renders time-bucketed aggregate data as an SVG line or area chart.
 * Requires the backend dateTrunc feature to produce meaningful time buckets
 * (e.g., groupBy createdAt with dateTrunc: { createdAt: 'month' }).
 *
 * Does NOT own data fetching — receives data through props.
 */

import type { PresentationProps } from '@/lib/viewTypes'

export interface TimeSeriesStyleConfig {
  /** groupBy field containing time bucket labels (x-axis) */
  timeField: string
  /** Measure result column for y-axis values */
  measureField: string
  /** Chart rendering mode (default: 'line') */
  chartType?: 'line' | 'area'
  /** Show dots at each data point (default: true) */
  showPoints?: boolean
  /** Show horizontal gridlines (default: true) */
  showGrid?: boolean
}

const CHART_WIDTH = 500
const CHART_HEIGHT = 300
const PADDING = { top: 20, right: 20, bottom: 60, left: 60 }

function formatValue(raw: unknown): string {
  if (raw === null || raw === undefined) return '\u2014'
  const num = typeof raw === 'number' ? raw : Number(raw)
  if (isNaN(num)) return String(raw)
  return num.toLocaleString()
}

function truncateLabel(label: string, maxLen: number = 10): string {
  return label.length > maxLen ? label.slice(0, maxLen - 1) + '\u2026' : label
}

export function TimeSeries({
  data,
  styleConfig,
  isLoading,
  error,
}: PresentationProps<TimeSeriesStyleConfig>) {
  if (isLoading) {
    return <div className="time-series-container time-series-loading">Loading...</div>
  }

  if (error) {
    return <div className="time-series-container time-series-error">{error}</div>
  }

  const rows = data?.data ?? []
  if (rows.length === 0) {
    return <div className="time-series-container time-series-empty">No data</div>
  }

  const { timeField, measureField, chartType = 'line', showPoints = true, showGrid = true } = styleConfig

  // Sort by time label ascending for chronological order
  const sortedRows = [...rows].sort((a, b) => {
    const aKey = String(a[timeField] ?? '')
    const bKey = String(b[timeField] ?? '')
    return aKey.localeCompare(bKey)
  })

  const values = sortedRows.map((row) => {
    const raw = row[measureField]
    return typeof raw === 'number' ? raw : Number(raw) || 0
  })
  const labels = sortedRows.map((row) => String(row[timeField] ?? ''))
  const maxVal = Math.max(...values, 1)

  const plotW = CHART_WIDTH - PADDING.left - PADDING.right
  const plotH = CHART_HEIGHT - PADDING.top - PADDING.bottom

  // Compute data point positions
  const points = sortedRows.map((_, i) => {
    const x =
      sortedRows.length === 1
        ? PADDING.left + plotW / 2
        : PADDING.left + (i / (sortedRows.length - 1)) * plotW
    const y = PADDING.top + plotH - (values[i] / maxVal) * plotH
    return { x, y }
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

  const areaPath =
    linePath +
    ` L ${points[points.length - 1].x} ${PADDING.top + plotH}` +
    ` L ${points[0].x} ${PADDING.top + plotH} Z`

  // Decide how many x-axis labels to show (avoid overlap)
  const maxLabels = Math.floor(plotW / 50)
  const labelStep = labels.length <= maxLabels ? 1 : Math.ceil(labels.length / maxLabels)

  return (
    <div className="time-series-container">
      <svg
        className="time-series-svg"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Y-axis */}
        <line
          x1={PADDING.left}
          y1={PADDING.top}
          x2={PADDING.left}
          y2={PADDING.top + plotH}
          className="time-series-axis"
        />
        {/* X-axis */}
        <line
          x1={PADDING.left}
          y1={PADDING.top + plotH}
          x2={PADDING.left + plotW}
          y2={PADDING.top + plotH}
          className="time-series-axis"
        />

        {/* Y-axis ticks and gridlines */}
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
          const y = PADDING.top + plotH * (1 - frac)
          const tickVal = Math.round(maxVal * frac)
          return (
            <g key={frac}>
              <line
                x1={PADDING.left - 4}
                y1={y}
                x2={PADDING.left}
                y2={y}
                className="time-series-axis"
              />
              <text
                x={PADDING.left - 8}
                y={y + 4}
                textAnchor="end"
                className="time-series-tick-label"
              >
                {formatValue(tickVal)}
              </text>
              {showGrid && frac > 0 && (
                <line
                  x1={PADDING.left + 1}
                  y1={y}
                  x2={PADDING.left + plotW}
                  y2={y}
                  className="time-series-gridline"
                />
              )}
            </g>
          )
        })}

        {/* Area fill (behind line) */}
        {chartType === 'area' && (
          <path d={areaPath} className="time-series-area" />
        )}

        {/* Line */}
        <path d={linePath} className="time-series-line" fill="none" />

        {/* Data points */}
        {showPoints &&
          points.map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={3.5}
              className="time-series-point"
            />
          ))}

        {/* X-axis labels */}
        {labels.map((label, i) => {
          if (i % labelStep !== 0 && i !== labels.length - 1) return null
          return (
            <text
              key={i}
              x={points[i].x}
              y={PADDING.top + plotH + 20}
              textAnchor="middle"
              className="time-series-tick-label"
              transform={`rotate(-30, ${points[i].x}, ${PADDING.top + plotH + 20})`}
            >
              {truncateLabel(label)}
            </text>
          )
        })}
      </svg>
    </div>
  )
}
