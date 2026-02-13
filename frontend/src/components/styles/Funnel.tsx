/**
 * Funnel — presentation component for the "aggregate/funnel" style.
 *
 * Renders grouped aggregate data as a stage-based funnel chart where
 * bars are centered and decrease in width from the widest (largest value)
 * to the narrowest.
 *
 * Does NOT own data fetching — receives data through props.
 */

import type { PresentationProps } from '@/lib/viewTypes'

export interface FunnelStyleConfig {
  /** groupBy field for stage labels */
  stageField: string
  /** Measure result column for bar width */
  measureField: string
  /** Explicit ordering of stages from top to bottom */
  stageOrder?: string[]
  /** Show percentage of first (top) stage (default: true) */
  showPercent?: boolean
  /** Show raw numeric values (default: true) */
  showValues?: boolean
}

const CHART_WIDTH = 500
const PADDING = { top: 10, right: 20, bottom: 10, left: 20 }
const BAR_HEIGHT = 44
const BAR_GAP = 8

const DEFAULT_COLORS = [
  'var(--brand)',
  'var(--brand-strong)',
  '#6366f1',
  '#8b5cf6',
  '#a78bfa',
  '#c4b5fd',
  '#ddd6fe',
  '#ede9fe',
]

function formatValue(raw: unknown): string {
  if (raw === null || raw === undefined) return '\u2014'
  const num = typeof raw === 'number' ? raw : Number(raw)
  if (isNaN(num)) return String(raw)
  return num.toLocaleString()
}

export function Funnel({
  data,
  styleConfig,
  isLoading,
  error,
}: PresentationProps<FunnelStyleConfig>) {
  if (isLoading) {
    return <div className="funnel-container funnel-loading">Loading...</div>
  }

  if (error) {
    return <div className="funnel-container funnel-error">{error}</div>
  }

  const rows = data?.data ?? []
  if (rows.length === 0) {
    return <div className="funnel-container funnel-empty">No data</div>
  }

  const { stageField, measureField, stageOrder, showPercent = true, showValues = true } = styleConfig

  // Sort rows by stageOrder if provided, otherwise keep data order
  let orderedRows = rows
  if (stageOrder && stageOrder.length > 0) {
    const orderMap = new Map(stageOrder.map((s, i) => [s, i]))
    orderedRows = [...rows].sort((a, b) => {
      const aIdx = orderMap.get(String(a[stageField] ?? '')) ?? 999
      const bIdx = orderMap.get(String(b[stageField] ?? '')) ?? 999
      return aIdx - bIdx
    })
  }

  const values = orderedRows.map((row) => {
    const raw = row[measureField]
    return typeof raw === 'number' ? raw : Number(raw) || 0
  })
  const labels = orderedRows.map((row) => String(row[stageField] ?? ''))
  const maxVal = Math.max(...values, 1)
  const topVal = values[0] || 1

  const plotW = CHART_WIDTH - PADDING.left - PADDING.right
  const totalHeight = PADDING.top + orderedRows.length * (BAR_HEIGHT + BAR_GAP) - BAR_GAP + PADDING.bottom
  const maxBarWidth = plotW * 0.85
  const centerX = PADDING.left + plotW / 2

  return (
    <div className="funnel-container">
      <svg
        className="funnel-svg"
        viewBox={`0 0 ${CHART_WIDTH} ${totalHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {orderedRows.map((_, i) => {
          const barW = Math.max(20, (values[i] / maxVal) * maxBarWidth)
          const x = centerX - barW / 2
          const y = PADDING.top + i * (BAR_HEIGHT + BAR_GAP)
          const color = DEFAULT_COLORS[i % DEFAULT_COLORS.length]
          const pct = Math.round((values[i] / topVal) * 100)

          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={BAR_HEIGHT}
                fill={color}
                rx={4}
                className="funnel-bar"
              />
              {/* Stage label — left side */}
              <text
                x={PADDING.left}
                y={y + BAR_HEIGHT / 2 + 5}
                textAnchor="start"
                className="funnel-stage-label"
              >
                {labels[i]}
              </text>
              {/* Value and percent — right side */}
              <text
                x={CHART_WIDTH - PADDING.right}
                y={y + BAR_HEIGHT / 2 + 5}
                textAnchor="end"
                className="funnel-stage-value"
              >
                {showValues && formatValue(values[i])}
                {showValues && showPercent && '  '}
                {showPercent && (
                  <tspan className="funnel-stage-percent">({pct}%)</tspan>
                )}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
