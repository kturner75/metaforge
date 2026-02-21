/**
 * BarChart — presentation component for the "aggregate/bar-chart" style.
 *
 * Renders grouped aggregate data as an SVG bar chart.
 * Does NOT own data fetching — receives data through props.
 */

import type { PresentationProps } from '@/lib/viewTypes'

export interface BarChartStyleConfig {
  /** groupBy field used for bar labels (x-axis) */
  dimensionField: string
  /** Measure result column used for bar height */
  measureField: string
  /** Bar orientation (default: vertical) */
  orientation?: 'vertical' | 'horizontal'
  /** Show value labels on bars (default: true) */
  showValues?: boolean
  /** CSS color for bars (default: var(--brand)) */
  barColor?: string
  /** Number format: number, percent, currency */
  format?: string
}

const CHART_WIDTH = 500
const CHART_HEIGHT = 300
const PADDING = { top: 20, right: 20, bottom: 60, left: 60 }

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
      return num.toLocaleString()
  }
}

function truncateLabel(label: string, maxLen: number = 12): string {
  return label.length > maxLen ? label.slice(0, maxLen - 1) + '\u2026' : label
}

export function BarChart({
  data,
  styleConfig,
  isLoading,
  error,
  onDrilldown,
}: PresentationProps<BarChartStyleConfig>) {
  if (isLoading) {
    return <div className="bar-chart-container bar-chart-loading">Loading...</div>
  }

  if (error) {
    return <div className="bar-chart-container bar-chart-error">{error}</div>
  }

  const rows = data?.data ?? []
  if (rows.length === 0) {
    return <div className="bar-chart-container bar-chart-empty">No data</div>
  }

  const { dimensionField, measureField, orientation = 'vertical', showValues = true, barColor, format } = styleConfig
  const color = barColor || 'var(--brand)'

  const values = rows.map((row) => {
    const raw = row[measureField]
    return typeof raw === 'number' ? raw : Number(raw) || 0
  })
  const labels = rows.map((row) => String(row[dimensionField] ?? ''))
  const maxVal = Math.max(...values, 1)

  const isVertical = orientation === 'vertical'

  const plotW = CHART_WIDTH - PADDING.left - PADDING.right
  const plotH = CHART_HEIGHT - PADDING.top - PADDING.bottom

  if (isVertical) {
    const barCount = values.length
    const gap = Math.max(4, plotW * 0.1 / barCount)
    const barW = Math.max(8, (plotW - gap * (barCount + 1)) / barCount)

    return (
      <div className="bar-chart-container">
        <svg
          className="bar-chart-svg"
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Y-axis line */}
          <line
            x1={PADDING.left}
            y1={PADDING.top}
            x2={PADDING.left}
            y2={PADDING.top + plotH}
            className="bar-chart-axis"
          />
          {/* X-axis line */}
          <line
            x1={PADDING.left}
            y1={PADDING.top + plotH}
            x2={PADDING.left + plotW}
            y2={PADDING.top + plotH}
            className="bar-chart-axis"
          />

          {/* Y-axis ticks */}
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
                  className="bar-chart-axis"
                />
                <text
                  x={PADDING.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  className="bar-chart-tick-label"
                >
                  {formatValue(tickVal, format)}
                </text>
                {frac > 0 && (
                  <line
                    x1={PADDING.left + 1}
                    y1={y}
                    x2={PADDING.left + plotW}
                    y2={y}
                    className="bar-chart-gridline"
                  />
                )}
              </g>
            )
          })}

          {/* Bars */}
          {values.map((val, i) => {
            const barH = (val / maxVal) * plotH
            const x = PADDING.left + gap + i * (barW + gap)
            const y = PADDING.top + plotH - barH
            return (
              <g key={i}>
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={barH}
                  fill={color}
                  rx={2}
                  className={`bar-chart-bar${onDrilldown ? ' bar-chart-bar-clickable' : ''}`}
                  onClick={onDrilldown ? () => onDrilldown(dimensionField, rows[i][dimensionField]) : undefined}
                />
                {showValues && (
                  <text
                    x={x + barW / 2}
                    y={y - 6}
                    textAnchor="middle"
                    className="bar-chart-value-label"
                  >
                    {formatValue(val, format)}
                  </text>
                )}
                {/* X-axis label */}
                <text
                  x={x + barW / 2}
                  y={PADDING.top + plotH + 16}
                  textAnchor="middle"
                  className="bar-chart-bar-label"
                >
                  {truncateLabel(labels[i])}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    )
  }

  // Horizontal orientation
  const barCount = values.length
  const gap = Math.max(4, plotH * 0.1 / barCount)
  const barH = Math.max(8, (plotH - gap * (barCount + 1)) / barCount)

  return (
    <div className="bar-chart-container">
      <svg
        className="bar-chart-svg"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Y-axis line */}
        <line
          x1={PADDING.left}
          y1={PADDING.top}
          x2={PADDING.left}
          y2={PADDING.top + plotH}
          className="bar-chart-axis"
        />
        {/* X-axis line */}
        <line
          x1={PADDING.left}
          y1={PADDING.top + plotH}
          x2={PADDING.left + plotW}
          y2={PADDING.top + plotH}
          className="bar-chart-axis"
        />

        {/* Bars */}
        {values.map((val, i) => {
          const barW = (val / maxVal) * plotW
          const x = PADDING.left
          const y = PADDING.top + gap + i * (barH + gap)
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={barH}
                fill={color}
                rx={2}
                className={`bar-chart-bar${onDrilldown ? ' bar-chart-bar-clickable' : ''}`}
                onClick={onDrilldown ? () => onDrilldown(dimensionField, rows[i][dimensionField]) : undefined}
              />
              {showValues && (
                <text
                  x={x + barW + 6}
                  y={y + barH / 2 + 4}
                  textAnchor="start"
                  className="bar-chart-value-label"
                >
                  {formatValue(val, format)}
                </text>
              )}
              {/* Y-axis label */}
              <text
                x={PADDING.left - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                className="bar-chart-bar-label"
              >
                {truncateLabel(labels[i])}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
