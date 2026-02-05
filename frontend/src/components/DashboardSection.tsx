/**
 * DashboardSection — optional KPI + aggregate chart widgets for list views.
 *
 * Only rendered when the route config provides dashboardConfigIds.
 */

import { useState } from 'react'
import { useSavedConfig } from '@/hooks/useViewConfig'
import { ConfiguredComponent } from './ConfiguredComponent'
import type { EntityRouteConfig } from '@/lib/routeConfig'

interface DashboardSectionProps {
  dashboardConfig: NonNullable<EntityRouteConfig['dashboardConfigIds']>
}

export function DashboardSection({ dashboardConfig }: DashboardSectionProps) {
  const aggregates = dashboardConfig.aggregates ?? []
  const [selectedAggIndex, setSelectedAggIndex] = useState(0)

  const { data: kpiConfig } = useSavedConfig(dashboardConfig.kpi)
  const selectedAgg = aggregates[selectedAggIndex]
  const { data: aggConfig } = useSavedConfig(selectedAgg?.id)

  return (
    <>
      {kpiConfig && (
        <div className="kpi-section">
          <ConfiguredComponent config={kpiConfig} />
        </div>
      )}

      {aggregates.length > 0 && (
        <div className="aggregate-section">
          <h3>Summary</h3>
          {aggregates.length > 1 && (
            <div className="style-selector">
              <label>Chart:</label>
              <select
                value={selectedAggIndex}
                onChange={(e) => setSelectedAggIndex(Number(e.target.value))}
              >
                {aggregates.map((agg, i) => (
                  <option key={agg.id} value={i}>
                    {agg.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          {aggConfig ? (
            <ConfiguredComponent config={aggConfig} />
          ) : (
            <div className="loading">Loading...</div>
          )}
        </div>
      )}
    </>
  )
}
