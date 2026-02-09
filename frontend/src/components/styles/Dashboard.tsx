/**
 * Dashboard — compose/dashboard style component.
 *
 * Renders a CSS grid of panels, each containing a ConfiguredComponent
 * (KPI cards, charts, grids, etc.) driven by YAML config. The Dashboard
 * itself does no data fetching — each panel resolves its own config and
 * delegates data loading to ConfiguredComponent.
 */

import { useSavedConfig } from '@/hooks/useViewConfig'
import { ConfiguredComponent } from '@/components/ConfiguredComponent'
import type { ComposeProps, DashboardStyleConfig, DashboardPanel } from '@/lib/viewTypes'

export function Dashboard({ styleConfig }: ComposeProps) {
  const typedConfig = styleConfig as unknown as DashboardStyleConfig
  const columns = typedConfig.columns ?? 3
  const gap = typedConfig.gap ?? 16
  const panels = typedConfig.panels ?? []

  if (panels.length === 0) {
    return null
  }

  return (
    <div
      className="dashboard"
      style={{
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: `${gap}px`,
      }}
    >
      {panels.map((panel, i) => (
        <DashboardPanelCard key={panel.componentConfig + i} panel={panel} />
      ))}
    </div>
  )
}

/**
 * DashboardPanelCard — resolves a config ID and renders it inside a panel card.
 *
 * Separated as its own component so useSavedConfig follows React hook rules
 * (not called inside a loop or conditionally).
 */
function DashboardPanelCard({ panel }: { panel: DashboardPanel }) {
  const { data: childConfig, isLoading } = useSavedConfig(panel.componentConfig)

  const style: React.CSSProperties = {}
  if (panel.colSpan && panel.colSpan > 1) style.gridColumn = `span ${panel.colSpan}`
  if (panel.rowSpan && panel.rowSpan > 1) style.gridRow = `span ${panel.rowSpan}`

  return (
    <div className="dashboard-panel" style={style}>
      {panel.label && (
        <div className="dashboard-panel-label">{panel.label}</div>
      )}
      <div className="dashboard-panel-content">
        {isLoading && <div className="dashboard-panel-loading">Loading...</div>}
        {!isLoading && !childConfig && (
          <div className="dashboard-panel-error">Config not found: {panel.componentConfig}</div>
        )}
        {childConfig && (
          <ConfiguredComponent config={childConfig} compact />
        )}
      </div>
    </div>
  )
}
