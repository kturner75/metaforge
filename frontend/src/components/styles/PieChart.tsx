/**
 * PieChart — presentation component for the "aggregate/pie-chart" style.
 *
 * Renders grouped aggregate data as an SVG pie or donut chart with legend.
 * Does NOT own data fetching — receives data through props.
 */

import type { PresentationProps } from '@/lib/viewTypes'

export interface PieChartStyleConfig {
  /** groupBy field used for slice labels */
  dimensionField: string
  /** Measure result column used for slice size */
  measureField: string
  /** Render as donut (hollow center) */
  donut?: boolean
  /** Show legend alongside chart (default: true) */
  showLegend?: boolean
  /** Show percentage labels on slices (default: true) */
  showPercent?: boolean
  /** Custom color palette */
  colors?: string[]
  /** Number format: number, percent, currency */
  format?: string
}

const DEFAULT_COLORS = [
  '#2361a9', '#e67e22', '#27ae60', '#e74c3c', '#9b59b6',
  '#1abc9c', '#f39c12', '#3498db', '#e91e63', '#00bcd4',
]

const SVG_SIZE = 240
const CENTER = SVG_SIZE / 2
const OUTER_RADIUS = 100
const INNER_RADIUS = 60
const LABEL_RADIUS = 75

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

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  }
}

function describeArc(
  cx: number,
  cy: number,
  outerR: number,
  innerR: number,
  startAngle: number,
  endAngle: number,
): string {
  const sweep = endAngle - startAngle
  const largeArc = sweep > 180 ? 1 : 0

  const outerStart = polarToCartesian(cx, cy, outerR, startAngle)
  const outerEnd = polarToCartesian(cx, cy, outerR, endAngle)

  if (innerR > 0) {
    const innerStart = polarToCartesian(cx, cy, innerR, startAngle)
    const innerEnd = polarToCartesian(cx, cy, innerR, endAngle)
    return [
      `M ${outerStart.x} ${outerStart.y}`,
      `A ${outerR} ${outerR} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
      `L ${innerEnd.x} ${innerEnd.y}`,
      `A ${innerR} ${innerR} 0 ${largeArc} 0 ${innerStart.x} ${innerStart.y}`,
      'Z',
    ].join(' ')
  }

  return [
    `M ${cx} ${cy}`,
    `L ${outerStart.x} ${outerStart.y}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
    'Z',
  ].join(' ')
}

export function PieChart({
  data,
  styleConfig,
  isLoading,
  error,
  onDrilldown,
}: PresentationProps<PieChartStyleConfig>) {
  if (isLoading) {
    return <div className="pie-chart-container pie-chart-loading">Loading...</div>
  }

  if (error) {
    return <div className="pie-chart-container pie-chart-error">{error}</div>
  }

  const rows = data?.data ?? []
  if (rows.length === 0) {
    return <div className="pie-chart-container pie-chart-empty">No data</div>
  }

  const {
    dimensionField,
    measureField,
    donut = false,
    showLegend = true,
    showPercent = true,
    colors = DEFAULT_COLORS,
    format,
  } = styleConfig

  const values = rows.map((row) => {
    const raw = row[measureField]
    return typeof raw === 'number' ? raw : Number(raw) || 0
  })
  const labels = rows.map((row) => String(row[dimensionField] ?? ''))
  const total = values.reduce((sum, v) => sum + v, 0)

  if (total === 0) {
    return <div className="pie-chart-container pie-chart-empty">No data</div>
  }

  const innerR = donut ? INNER_RADIUS : 0

  // Build slices
  const slices: { path: string; color: string; label: string; value: number; pct: number; midAngle: number }[] = []
  let currentAngle = 0
  for (let i = 0; i < values.length; i++) {
    const pct = (values[i] / total) * 100
    const sweepAngle = (values[i] / total) * 360
    // Avoid zero-width slices
    if (sweepAngle < 0.5) {
      currentAngle += sweepAngle
      continue
    }
    const endAngle = currentAngle + sweepAngle
    const midAngle = currentAngle + sweepAngle / 2
    const path = describeArc(CENTER, CENTER, OUTER_RADIUS, innerR, currentAngle, endAngle)
    slices.push({
      path,
      color: colors[i % colors.length],
      label: labels[i],
      value: values[i],
      pct,
      midAngle,
    })
    currentAngle = endAngle
  }

  return (
    <div className="pie-chart-container">
      <div className="pie-chart-layout">
        <svg
          className="pie-chart-svg"
          viewBox={`0 0 ${SVG_SIZE} ${SVG_SIZE}`}
          preserveAspectRatio="xMidYMid meet"
        >
          {slices.map((slice, i) => (
            <path
              key={i}
              d={slice.path}
              fill={slice.color}
              className={`pie-chart-slice${onDrilldown ? ' pie-slice-clickable' : ''}`}
              onClick={onDrilldown ? () => onDrilldown(dimensionField, slice.label) : undefined}
            />
          ))}
          {showPercent &&
            slices
              .filter((s) => s.pct >= 5)
              .map((slice, i) => {
                const labelR = donut ? (OUTER_RADIUS + INNER_RADIUS) / 2 : LABEL_RADIUS
                const pos = polarToCartesian(CENTER, CENTER, labelR, slice.midAngle)
                return (
                  <text
                    key={i}
                    x={pos.x}
                    y={pos.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className="pie-chart-percent-label"
                  >
                    {Math.round(slice.pct)}%
                  </text>
                )
              })}
        </svg>
        {showLegend && (
          <ul className="pie-chart-legend">
            {slices.map((slice, i) => (
              <li
                key={i}
                className={`pie-chart-legend-item${onDrilldown ? ' pie-slice-clickable' : ''}`}
                onClick={onDrilldown ? () => onDrilldown(dimensionField, slice.label) : undefined}
              >
                <span
                  className="pie-chart-legend-swatch"
                  style={{ background: slice.color }}
                />
                <span className="pie-chart-legend-label">{slice.label}</span>
                <span className="pie-chart-legend-value">
                  {formatValue(slice.value, format)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
