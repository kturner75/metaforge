/**
 * RecordForm — presentation component for the "record/form" style.
 *
 * Renders an editable form with configurable sections, collapsible groups,
 * and client+server validation. Create vs edit mode is determined by
 * whether dataConfig.recordId is present.
 *
 * Does NOT own data fetching or mutations — receives data through props
 * and delegates submit/cancel to parent callbacks.
 */

import { useState, useMemo, useEffect, useCallback } from 'react'
import { FieldRenderer } from '@/components/FieldRenderer'
import type { PresentationProps } from '@/lib/viewTypes'
import type { FieldMetadata } from '@/lib/types'

export interface FormSection {
  label?: string
  fields: string[]
  columns?: 1 | 2
  collapsible?: boolean
  defaultExpanded?: boolean
}

export interface FormStyleConfig {
  sections?: FormSection[]
}

const AUTO_FIELD_NAMES = new Set([
  'id', 'tenantId', 'createdAt', 'updatedAt', 'createdBy', 'updatedBy',
])

function isAutoField(field: FieldMetadata): boolean {
  return field.primaryKey === true || AUTO_FIELD_NAMES.has(field.name)
}

function isEditableField(field: FieldMetadata): boolean {
  if (field.access?.write === false) return false
  return !field.readOnly && !field.primaryKey
}

export function RecordForm({
  data,
  metadata,
  styleConfig,
  dataConfig,
  isLoading,
  error,
  onSubmit,
  onCancel,
  isSubmitting,
  serverErrors,
}: PresentationProps<FormStyleConfig>) {
  const isEditMode = !!dataConfig.recordId
  const record = data?.data?.[0] ?? null

  const [formData, setFormData] = useState<Record<string, unknown>>({})
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({})
  const [collapsedSections, setCollapsedSections] = useState<Set<number>>(new Set())

  // Seed form data: empty for create, record data for edit
  useEffect(() => {
    if (isEditMode && record) {
      setFormData(record)
    } else if (!isEditMode) {
      setFormData({})
    }
  }, [isEditMode, record])

  // Build sections from config or auto-generate
  const sections = useMemo(() => {
    if (!metadata) return []

    if (styleConfig.sections && styleConfig.sections.length > 0) {
      return styleConfig.sections.map((section, index) => {
        const fieldsMeta = section.fields
          .map((name) => metadata.fields.find((f) => f.name === name))
          .filter((f): f is FieldMetadata => !!f && isEditableField(f))
        return {
          label: section.label,
          columns: section.columns ?? 1,
          collapsible: section.collapsible ?? false,
          defaultExpanded: section.defaultExpanded ?? true,
          fieldsMeta,
          index,
        }
      })
    }

    // Auto-generate: all editable non-auto fields in one section
    const editableFields = metadata.fields.filter(
      (f) => !isAutoField(f) && isEditableField(f)
    )
    return [
      {
        label: undefined,
        columns: 1 as const,
        collapsible: false,
        defaultExpanded: true,
        fieldsMeta: editableFields,
        index: 0,
      },
    ]
  }, [metadata, styleConfig.sections])

  // Initialize collapsed state from section defaults
  useEffect(() => {
    const initialCollapsed = new Set<number>()
    for (const section of sections) {
      if (section.collapsible && !section.defaultExpanded) {
        initialCollapsed.add(section.index)
      }
    }
    setCollapsedSections(initialCollapsed)
  }, [sections])

  // All editable fields across all sections (for validation)
  const allEditableFields = useMemo(
    () => sections.flatMap((s) => s.fieldsMeta),
    [sections]
  )

  // Server error maps
  const serverFieldErrors = useMemo(() => {
    if (!serverErrors) return {}
    const map: Record<string, string> = {}
    for (const err of serverErrors.errors) {
      if (err.field) {
        map[err.field] = map[err.field]
          ? `${map[err.field]}; ${err.message}`
          : err.message
      }
    }
    return map
  }, [serverErrors])

  const generalErrors = useMemo(() => {
    if (!serverErrors) return []
    return serverErrors.errors.filter((e) => !e.field)
  }, [serverErrors])

  const mergedErrors = useMemo(
    () => ({ ...serverFieldErrors, ...clientErrors }),
    [serverFieldErrors, clientErrors]
  )

  const handleChange = useCallback((fieldName: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [fieldName]: value }))
    setClientErrors((prev) => {
      if (!prev[fieldName]) return prev
      const next = { ...prev }
      delete next[fieldName]
      return next
    })
  }, [])

  const validate = useCallback((): boolean => {
    const newErrors: Record<string, string> = {}

    for (const field of allEditableFields) {
      const value = formData[field.name]
      const rules = field.validation
      if (!rules) continue

      const isEmpty = value === undefined || value === null || value === ''

      if (rules.required && isEmpty) {
        newErrors[field.name] = `${field.displayName} is required`
        continue
      }

      if (isEmpty) continue

      if (typeof value === 'string') {
        if (rules.minLength != null && value.length < rules.minLength) {
          newErrors[field.name] = `${field.displayName} must be at least ${rules.minLength} characters`
          continue
        }
        if (rules.maxLength != null && value.length > rules.maxLength) {
          newErrors[field.name] = `${field.displayName} must be at most ${rules.maxLength} characters`
          continue
        }
      }

      if (typeof value === 'number') {
        if (rules.min != null && value < rules.min) {
          newErrors[field.name] = `${field.displayName} must be at least ${rules.min}`
          continue
        }
        if (rules.max != null && value > rules.max) {
          newErrors[field.name] = `${field.displayName} must be at most ${rules.max}`
          continue
        }
      }

      if (rules.pattern && typeof value === 'string') {
        try {
          const regex = new RegExp(rules.pattern)
          if (!regex.test(value)) {
            newErrors[field.name] = `${field.displayName} is not in the expected format`
          }
        } catch {
          // Invalid regex in metadata — skip, server will catch it
        }
      }
    }

    setClientErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }, [allEditableFields, formData])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (validate() && onSubmit) {
      onSubmit(formData)
    }
  }

  const toggleSection = (index: number) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  if (error) {
    return <div className="error">{error}</div>
  }

  if (!metadata) {
    return <div className="error">Entity not found</div>
  }

  if (isLoading) {
    return (
      <div className="record-form">
        <div className="record-form-loading">Loading...</div>
      </div>
    )
  }

  if (isEditMode && !record) {
    return (
      <div className="record-form">
        <div className="record-form-empty">Record not found</div>
      </div>
    )
  }

  return (
    <form className="record-form" onSubmit={handleSubmit}>
      {generalErrors.length > 0 && (
        <div className="form-errors">
          {generalErrors.map((err, i) => (
            <div key={i} className="form-error-banner">{err.message}</div>
          ))}
        </div>
      )}

      {sections.map((section) => {
        const isCollapsed = collapsedSections.has(section.index)

        return (
          <div key={section.index} className="record-form-section">
            {section.label && (
              <div
                className={`record-form-section-header${section.collapsible ? ' collapsible' : ''}`}
                onClick={section.collapsible ? () => toggleSection(section.index) : undefined}
              >
                {section.collapsible && (
                  <span className={`record-form-chevron${isCollapsed ? '' : ' expanded'}`}>
                    &#9654;
                  </span>
                )}
                <span>{section.label}</span>
              </div>
            )}

            {!isCollapsed && (
              <div
                className="record-form-fields"
                style={{ '--form-columns': section.columns } as React.CSSProperties}
              >
                {section.fieldsMeta.map((field) => (
                  <div key={field.name} className="form-field">
                    <label htmlFor={field.name}>
                      {field.displayName}
                      {field.validation?.required && <span className="required">*</span>}
                    </label>

                    <FieldRenderer
                      field={field}
                      context="edit"
                      value={formData[field.name]}
                      onChange={(value) => handleChange(field.name, value)}
                      disabled={isSubmitting}
                      error={mergedErrors[field.name]}
                    />

                    {mergedErrors[field.name] && (
                      <span className="error-message">{mergedErrors[field.name]}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}

      <div className="record-form-actions">
        {onCancel && (
          <button type="button" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </button>
        )}
        <button type="submit" className="primary" disabled={isSubmitting || !onSubmit}>
          {isSubmitting ? 'Saving...' : 'Save'}
        </button>
      </div>
    </form>
  )
}
