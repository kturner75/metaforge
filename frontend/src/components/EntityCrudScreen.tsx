/**
 * EntityCrudScreen — generic screen router for any screen type.
 *
 * Reads the screen slug from route params, fetches the screen definition,
 * determines mode (list/create/edit/detail) from the URL path,
 * and delegates all rendering to ConfiguredComponent.
 *
 * Supports screen types:
 * - entity: Full CRUD (list/create/edit/detail) with view config references
 * - dashboard: Single compose/dashboard view
 *
 * Falls back to legacy routeConfig.ts if no screen metadata exists.
 */

import { useMemo, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import type { FilterGroup } from '@/lib/types'
import { getRouteBySlug } from '@/lib/routeConfig'
import { useEntityMetadata, useEntity } from '@/hooks/useApi'
import { useEntityCrud } from '@/hooks/useEntityCrud'
import { useResolvedConfig, useSavedConfig } from '@/hooks/useViewConfig'
import { useScreen } from '@/hooks/useNavigation'
import { ConfiguredComponent } from './ConfiguredComponent'
import { WarningDialog } from './WarningDialog'
import { Breadcrumb } from './Breadcrumb'
import { getRecordLabel } from '@/lib/entityUtils'
import type { ConfigBase } from '@/lib/viewTypes'
import type { BreadcrumbItem } from './Breadcrumb'

type ScreenMode = 'list' | 'create' | 'edit' | 'detail'

function useScreenMode(): { mode: ScreenMode; id?: string } {
  const { id } = useParams<{ slug: string; id: string }>()
  const location = useLocation()
  const path = location.pathname

  if (path.endsWith('/new')) return { mode: 'create' }
  if (id && path.endsWith('/edit')) return { mode: 'edit', id }
  if (id) return { mode: 'detail', id }
  return { mode: 'list' }
}

/** Build a fallback config when no saved/resolved config exists for this entity+style. */
function autoConfig(
  entityName: string,
  pattern: 'query' | 'record',
  style: string,
  dataConfig: Record<string, unknown> = {}
): ConfigBase {
  return {
    id: `auto:${entityName}-${style}`,
    name: `${entityName} ${style}`,
    entityName,
    pattern,
    style,
    scope: 'global',
    source: 'auto',
    dataConfig,
    styleConfig: {},
  }
}

export function EntityCrudScreen() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const { mode, id } = useScreenMode()

  // Fetch screen definition from navigation metadata (with routeConfig fallback)
  const { data: screen } = useScreen(slug)
  const routeConfig = slug ? getRouteBySlug(slug) : undefined
  const entityName = screen?.entityName ?? routeConfig?.entityName ?? ''
  const screenType = screen?.type ?? 'entity'
  const baseUrl = `/${slug}`

  // Drilldown filter: passed via location state when navigating from an aggregate component.
  const location = useLocation()
  const drilldownFilter = (location.state as { drilldownFilter?: FilterGroup } | null)?.drilldownFilter ?? null
  const clearDrilldown = useCallback(() => {
    navigate(baseUrl, { replace: true, state: null })
  }, [navigate, baseUrl])

  const { data: metadata } = useEntityMetadata(entityName)
  const crud = useEntityCrud(entityName, baseUrl)

  // --- Config resolution ---
  // Screen YAML can specify config IDs for each mode (e.g., views.list = "yaml:contact-grid").
  // When specified, we fetch by ID. Otherwise, we fall back to resolving by entity+style.

  const screenListConfigId = screen?.views?.list
  const screenDetailConfigId = screen?.views?.detail
  const screenCreateConfigId = screen?.views?.create
  const screenEditConfigId = screen?.views?.edit
  const screenDefaultConfigId = screen?.views?.default // for dashboard screens

  // List view config
  const { data: screenListConfig } = useSavedConfig(screenListConfigId)
  const { data: resolvedGridConfig, isError: gridConfigError } = useResolvedConfig(
    screenListConfigId ? '' : entityName, // skip resolve when screen specifies a config ID
    'grid'
  )
  const listConfig: ConfigBase | null = useMemo(() => {
    const base = screenListConfig ?? resolvedGridConfig ?? (gridConfigError ? autoConfig(entityName, 'query', 'grid') : null)
    if (!base || !drilldownFilter) return base
    // Merge drilldown filter with any existing filter from the config
    const existingFilter = base.dataConfig?.filter
    const mergedFilter: FilterGroup = existingFilter
      ? { operator: 'and', conditions: [...existingFilter.conditions, ...drilldownFilter.conditions] }
      : drilldownFilter
    return { ...base, dataConfig: { ...base.dataConfig, filter: mergedFilter } }
  }, [screenListConfig, resolvedGridConfig, gridConfigError, entityName, drilldownFilter])

  // Form config (create/edit share a config, with recordId injected for edit)
  const { data: screenCreateConfig } = useSavedConfig(screenCreateConfigId)
  const { data: screenEditConfig } = useSavedConfig(screenEditConfigId)
  const { data: resolvedFormConfig, isError: formConfigError } = useResolvedConfig(
    (screenCreateConfigId && screenEditConfigId) ? '' : entityName,
    'form'
  )
  const formConfig = useCallback(
    (recordId?: string): ConfigBase => {
      const screenForm = recordId ? screenEditConfig : screenCreateConfig
      const base = screenForm ?? resolvedFormConfig ?? (formConfigError ? autoConfig(entityName, 'record', 'form') : null)
      if (!base) return autoConfig(entityName, 'record', 'form', recordId ? { recordId } : {})
      return { ...base, dataConfig: { ...base.dataConfig, recordId: recordId ?? null } }
    },
    [screenCreateConfig, screenEditConfig, resolvedFormConfig, formConfigError, entityName]
  )

  // Dashboard config for entity list view (optional — renders below the grid)
  const { data: resolvedDashboardConfig } = useResolvedConfig(entityName, 'dashboard')

  // Dashboard screen default config (for type === 'dashboard')
  const { data: dashboardDefaultConfig } = useSavedConfig(screenDefaultConfigId)

  // Detail config: screen-specified or resolve by entity+style
  const { data: screenDetailSavedConfig } = useSavedConfig(screenDetailConfigId)
  const { data: resolvedDetailPageConfig } = useResolvedConfig(
    screenDetailConfigId ? '' : entityName,
    'detail-page'
  )
  const { data: resolvedDetailConfig, isError: detailConfigError } = useResolvedConfig(
    screenDetailConfigId ? '' : entityName,
    'detail'
  )
  const detailConfig = useCallback(
    (recordId: string): ConfigBase => {
      // Screen-specified detail config takes priority
      if (screenDetailSavedConfig) {
        return {
          ...screenDetailSavedConfig,
          dataConfig: { ...screenDetailSavedConfig.dataConfig, recordId },
        }
      }
      // Prefer compose/detail-page config if available (entity overview page)
      if (resolvedDetailPageConfig) {
        return {
          ...resolvedDetailPageConfig,
          dataConfig: { ...resolvedDetailPageConfig.dataConfig, recordId },
        }
      }
      // Fall back to record/detail
      const base = resolvedDetailConfig ?? (detailConfigError ? autoConfig(entityName, 'record', 'detail') : null)
      if (!base) return autoConfig(entityName, 'record', 'detail', { recordId })
      return { ...base, dataConfig: { ...base.dataConfig, recordId } }
    },
    [screenDetailSavedConfig, resolvedDetailPageConfig, resolvedDetailConfig, detailConfigError, entityName]
  )

  const handleRowClick = useCallback(
    (row: Record<string, unknown>) => {
      navigate(`${baseUrl}/${row.id}`)
    },
    [navigate, baseUrl]
  )

  const handleCreateSubmit = useCallback(
    (data: Record<string, unknown>) => crud.handleCreate(data),
    [crud]
  )

  const handleUpdateSubmit = useCallback(
    (data: Record<string, unknown>) => {
      if (id) crud.handleUpdate(id, data)
    },
    [crud, id]
  )

  const handleCancel = useCallback(() => {
    crud.clearErrors()
    navigate(baseUrl)
  }, [crud, navigate, baseUrl])

  const handleEdit = useCallback(() => {
    if (id) navigate(`${baseUrl}/${id}/edit`)
  }, [navigate, baseUrl, id])

  const displayName = metadata?.displayName ?? entityName
  const pluralName = metadata?.pluralName ?? `${entityName}s`
  const screenName = screen?.name

  // Entity-level operation permissions (default true while metadata loads to avoid flicker)
  const canCreate = metadata?.operations?.create ?? true
  const canUpdate = metadata?.operations?.update ?? true
  const canDelete = metadata?.operations?.delete ?? true

  // Fetch the current record (for detail/edit modes) to display its label in the breadcrumb
  const needsRecord = mode === 'detail' || mode === 'edit'
  const { data: recordData } = useEntity(entityName, needsRecord ? id : undefined)
  const recordLabel = getRecordLabel(recordData?.data as Record<string, unknown> | undefined, metadata)

  // Build breadcrumb items based on current screen mode
  const breadcrumbItems = useMemo((): BreadcrumbItem[] => {
    const listCrumb = { label: screenName ?? pluralName, href: baseUrl }
    if (mode === 'list') return [{ label: screenName ?? pluralName }]
    if (mode === 'create') return [listCrumb, { label: `New ${displayName}` }]
    if (mode === 'detail') return [listCrumb, { label: recordLabel ?? id ?? '' }]
    if (mode === 'edit') return [
      listCrumb,
      { label: recordLabel ?? id ?? '', href: id ? `${baseUrl}/${id}` : undefined },
      { label: 'Edit' },
    ]
    return [listCrumb]
  }, [mode, screenName, pluralName, displayName, baseUrl, id, recordLabel])

  // For unknown screens (no screen YAML and no routeConfig), show error
  if (!screen && !routeConfig) {
    return <div className="error">Screen not found</div>
  }

  // Redirect from create/edit if the user lacks permission (metadata has loaded)
  if (metadata && mode === 'create' && !canCreate) {
    navigate(baseUrl, { replace: true })
    return null
  }
  if (metadata && mode === 'edit' && !canUpdate) {
    navigate(id ? `${baseUrl}/${id}` : baseUrl, { replace: true })
    return null
  }

  // --- Dashboard screen type ---
  if (screenType === 'dashboard' && mode === 'list') {
    return (
      <div className="dashboard-screen">
        <div className="entity-crud-header">
          <h1>{screenName ?? 'Dashboard'}</h1>
        </div>
        {dashboardDefaultConfig ? (
          <ConfiguredComponent config={dashboardDefaultConfig} />
        ) : (
          <div className="loading">Loading dashboard...</div>
        )}
      </div>
    )
  }

  // --- Entity CRUD screen type ---
  return (
    <>
      {mode === 'list' && (
        <>
          <Breadcrumb items={breadcrumbItems} />
          <div className="entity-crud-header">
            <h1>{screenName ?? pluralName}</h1>
            {canCreate && (
              <button className="primary" onClick={() => navigate(`${baseUrl}/new`)}>
                New {displayName}
              </button>
            )}
          </div>
          {drilldownFilter && (
            <div className="drilldown-filter-badge">
              <span>
                Filtered by:{' '}
                {drilldownFilter.conditions.map((c) => {
                  const cond = c as { field: string; value: unknown }
                  return `${cond.field} = ${cond.value}`
                }).join(', ')}
              </span>
              <button className="drilldown-filter-clear" onClick={clearDrilldown}>
                ✕ Clear filter
              </button>
            </div>
          )}
          {listConfig && (
            <ConfiguredComponent config={listConfig} onRowClick={handleRowClick} />
          )}
          {!listConfig && <div className="loading">Loading...</div>}
          {resolvedDashboardConfig && (
            <ConfiguredComponent config={resolvedDashboardConfig} />
          )}
        </>
      )}

      {mode === 'create' && (
        <>
          <Breadcrumb items={breadcrumbItems} />
          <div className="form-container">
            <h2>New {displayName}</h2>
            <ConfiguredComponent
              config={formConfig()}
              onSubmit={handleCreateSubmit}
              onCancel={handleCancel}
              isSubmitting={crud.isCreating}
              serverErrors={crud.validationErrors}
            />
          </div>
        </>
      )}

      {mode === 'edit' && id && (
        <>
          <Breadcrumb items={breadcrumbItems} />
          <div className="form-container">
            <div className="form-header">
              <h2>Edit {displayName}</h2>
              {canDelete && (
                <button className="danger" onClick={() => crud.handleDelete(id)}>
                  Delete
                </button>
              )}
            </div>
            <ConfiguredComponent
              config={formConfig(id)}
              onSubmit={handleUpdateSubmit}
              onCancel={handleCancel}
              isSubmitting={crud.isUpdating}
              serverErrors={crud.validationErrors}
            />
          </div>
        </>
      )}

      {mode === 'detail' && id && (
        <div className="detail-view-container">
          <div className="detail-view-header">
            <Breadcrumb items={breadcrumbItems} />
            {canUpdate && <button onClick={handleEdit}>Edit</button>}
          </div>
          <ConfiguredComponent config={detailConfig(id)} />
        </div>
      )}

      {crud.pendingWarnings && (
        <WarningDialog
          warnings={crud.pendingWarnings.warnings}
          onProceed={crud.handleAcknowledge}
          onCancel={crud.handleDismissWarnings}
          isPending={crud.isAcknowledging}
        />
      )}
    </>
  )
}
