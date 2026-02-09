/**
 * EntityCrudScreen — generic CRUD screen for any entity.
 *
 * Reads the entity slug from route params, determines mode (list/create/edit/detail)
 * from the URL path, and delegates all rendering to ConfiguredComponent.
 */

import { useMemo, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { getRouteBySlug } from '@/lib/routeConfig'
import { useEntityMetadata } from '@/hooks/useApi'
import { useEntityCrud } from '@/hooks/useEntityCrud'
import { useResolvedConfig } from '@/hooks/useViewConfig'
import { ConfiguredComponent } from './ConfiguredComponent'
import { WarningDialog } from './WarningDialog'
import type { ConfigBase } from '@/lib/viewTypes'

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

  const routeConfig = slug ? getRouteBySlug(slug) : undefined
  const entityName = routeConfig?.entityName ?? ''
  const baseUrl = `/${slug}`

  const { data: metadata } = useEntityMetadata(entityName)
  const crud = useEntityCrud(entityName, baseUrl)

  // Resolve grid config for list view (falls back to auto-generated)
  const { data: resolvedGridConfig, isError: gridConfigError } = useResolvedConfig(entityName, 'grid')
  const listConfig: ConfigBase | null = useMemo(() => {
    if (resolvedGridConfig) return resolvedGridConfig
    if (gridConfigError) return autoConfig(entityName, 'query', 'grid')
    return null // still loading
  }, [resolvedGridConfig, gridConfigError, entityName])

  // Resolve form config (falls back to auto-generated)
  const { data: resolvedFormConfig, isError: formConfigError } = useResolvedConfig(entityName, 'form')
  const formConfig = useCallback(
    (recordId?: string): ConfigBase => {
      const base = resolvedFormConfig ?? (formConfigError ? autoConfig(entityName, 'record', 'form') : null)
      if (!base) return autoConfig(entityName, 'record', 'form', recordId ? { recordId } : {})
      return { ...base, dataConfig: { ...base.dataConfig, recordId: recordId ?? null } }
    },
    [resolvedFormConfig, formConfigError, entityName]
  )

  // Resolve dashboard config for list view (optional — renders below the grid)
  const { data: resolvedDashboardConfig } = useResolvedConfig(entityName, 'dashboard')

  // Resolve detail configs: prefer compose/detail-page, fall back to record/detail
  const { data: resolvedDetailPageConfig } = useResolvedConfig(entityName, 'detail-page')
  const { data: resolvedDetailConfig, isError: detailConfigError } = useResolvedConfig(entityName, 'detail')
  const detailConfig = useCallback(
    (recordId: string): ConfigBase => {
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
    [resolvedDetailPageConfig, resolvedDetailConfig, detailConfigError, entityName]
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

  const handleBack = useCallback(() => {
    navigate(baseUrl)
  }, [navigate, baseUrl])

  const handleEdit = useCallback(() => {
    if (id) navigate(`${baseUrl}/${id}/edit`)
  }, [navigate, baseUrl, id])

  const displayName = metadata?.displayName ?? entityName
  const pluralName = metadata?.pluralName ?? `${entityName}s`

  if (!routeConfig) {
    return <div className="error">Entity not found</div>
  }

  return (
    <>
      {mode === 'list' && (
        <>
          <div className="entity-crud-header">
            <h1>{pluralName}</h1>
            <button className="primary" onClick={() => navigate(`${baseUrl}/new`)}>
              New {displayName}
            </button>
          </div>
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
      )}

      {mode === 'edit' && id && (
        <div className="form-container">
          <div className="form-header">
            <h2>Edit {displayName}</h2>
            <button className="danger" onClick={() => crud.handleDelete(id)}>
              Delete
            </button>
          </div>
          <ConfiguredComponent
            config={formConfig(id)}
            onSubmit={handleUpdateSubmit}
            onCancel={handleCancel}
            isSubmitting={crud.isUpdating}
            serverErrors={crud.validationErrors}
          />
        </div>
      )}

      {mode === 'detail' && id && (
        <div className="detail-view-container">
          <div className="detail-view-header">
            <button onClick={handleBack}>&larr; Back to list</button>
            <button onClick={handleEdit}>Edit</button>
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
