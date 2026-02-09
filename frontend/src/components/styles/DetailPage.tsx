/**
 * DetailPage — compose/detail-page style component.
 *
 * Renders an entity detail page with:
 * - A header section displaying key field values
 * - Tabbed child views (grids, charts, etc.) filtered by the parent record
 *
 * Unlike PresentationProps-based styles, this component manages its own data
 * fetching via useRecordData (for the header) and delegates child rendering
 * to ConfiguredComponent instances with parentContext for contextFilter injection.
 */

import { useState, useMemo } from 'react'
import { useEntityMetadata } from '@/hooks/useApi'
import { useRecordData } from '@/hooks/useRecordData'
import { useSavedConfig } from '@/hooks/useViewConfig'
import { ConfiguredComponent } from '@/components/ConfiguredComponent'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { ComposeProps, DetailPageStyleConfig } from '@/lib/viewTypes'
import type { FieldMetadata } from '@/lib/types'

export function DetailPage({ config, styleConfig }: ComposeProps) {
  const typedConfig = styleConfig as unknown as DetailPageStyleConfig
  const entityName = config.entityName ?? config.dataConfig.entityName ?? ''
  const recordId = config.dataConfig.recordId as string ?? ''

  const { data: metadata } = useEntityMetadata(entityName)
  const recordData = useRecordData({ entityName, recordId })

  const record = recordData.data?.data?.[0] ?? null
  const [activeTabIndex, setActiveTabIndex] = useState(0)

  // Resolve header fields metadata
  const headerFieldsMeta: FieldMetadata[] = useMemo(() => {
    if (!metadata) return []
    return (typedConfig.headerFields ?? [])
      .map((name) => metadata.fields.find((f) => f.name === name))
      .filter(Boolean) as FieldMetadata[]
  }, [metadata, typedConfig.headerFields])

  const tabs = typedConfig.tabs ?? []
  const isFullMode = typedConfig.tabMode === 'full'
  const activeTab = tabs[activeTabIndex]

  /** For relation fields, prefer the hydrated display value over the raw ID. */
  const fieldValue = (row: Record<string, unknown>, field: FieldMetadata) =>
    field.type === 'relation'
      ? (row[`${field.name}_display`] ?? row[field.name])
      : row[field.name]

  if (recordData.error) {
    return <div className="error">{recordData.error}</div>
  }

  if (recordData.isLoading || !metadata) {
    return (
      <div className="detail-page">
        <div className="detail-page-loading">Loading...</div>
      </div>
    )
  }

  if (!record) {
    return (
      <div className="detail-page">
        <div className="detail-page-empty">Record not found</div>
      </div>
    )
  }

  return (
    <div className={`detail-page ${isFullMode ? 'detail-page--full' : 'detail-page--inline'}`}>
      {/* Header Section */}
      <div className="detail-page-header">
        {headerFieldsMeta.map((field) => (
          <div key={field.name} className="detail-page-header-field">
            <span className="detail-page-header-label">{field.displayName}</span>
            <span className="detail-page-header-value">
              <FieldRenderer
                field={field}
                context="display"
                value={fieldValue(record, field)}
              />
            </span>
          </div>
        ))}
      </div>

      {/* Tabs + Content */}
      {tabs.length > 0 && (
        isFullMode ? (
          <div className="detail-page-full-layout">
            <div className="detail-page-tab-sidebar">
              {tabs.map((tab, i) => (
                <button
                  key={i}
                  className={`detail-page-tab-btn ${i === activeTabIndex ? 'active' : ''}`}
                  onClick={() => setActiveTabIndex(i)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="detail-page-tab-content">
              {activeTab && (
                <TabPanel
                  key={activeTab.componentConfig}
                  configId={activeTab.componentConfig}
                  recordId={recordId}
                  compact={false}
                />
              )}
            </div>
          </div>
        ) : (
          <div className="detail-page-inline-layout">
            <div className="detail-page-tab-bar">
              {tabs.map((tab, i) => (
                <button
                  key={i}
                  className={`detail-page-tab-btn ${i === activeTabIndex ? 'active' : ''}`}
                  onClick={() => setActiveTabIndex(i)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="detail-page-tab-content">
              {activeTab && (
                <TabPanel
                  key={activeTab.componentConfig}
                  configId={activeTab.componentConfig}
                  recordId={recordId}
                  compact={true}
                />
              )}
            </div>
          </div>
        )
      )}
    </div>
  )
}

/**
 * TabPanel — resolves a config ID and renders a ConfiguredComponent.
 *
 * Separated as its own component so useSavedConfig follows React hook rules
 * (not called conditionally). The parentContext prop triggers contextFilter
 * injection in ConfiguredComponent, automatically filtering child data
 * by the parent record.
 */
function TabPanel({
  configId,
  recordId,
  compact,
}: {
  configId: string
  recordId: string
  compact: boolean
}) {
  const { data: childConfig, isLoading } = useSavedConfig(configId)

  if (isLoading) {
    return <div className="detail-page-tab-loading">Loading...</div>
  }

  if (!childConfig) {
    return <div className="detail-page-tab-error">Tab config not found: {configId}</div>
  }

  return (
    <ConfiguredComponent
      config={childConfig}
      parentContext={{ recordId }}
      compact={compact}
    />
  )
}
