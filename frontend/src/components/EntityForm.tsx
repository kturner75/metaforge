/**
 * EntityForm - renders a create/edit form for an entity using metadata.
 */

import { useState, useMemo, useEffect } from 'react'
import { useEntityMetadata } from '@/hooks/useApi'
import { FieldRenderer } from './FieldRenderer'
import type { ValidationErrorBody } from '@/lib/api'

interface EntityFormProps {
  entity: string
  defaultValues?: Record<string, unknown>
  fields?: string[]
  onSubmit: (data: Record<string, unknown>) => void
  onCancel?: () => void
  isSubmitting?: boolean
  serverErrors?: ValidationErrorBody | null
}

export function EntityForm({
  entity,
  defaultValues,
  fields: fieldOverride,
  onSubmit,
  onCancel,
  isSubmitting,
  serverErrors,
}: EntityFormProps) {
  const { data: metadata, isLoading } = useEntityMetadata(entity)
  const [formData, setFormData] = useState<Record<string, unknown>>(defaultValues ?? {})
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({})

  // Sync defaultValues when they change (e.g., after loading existing record)
  useEffect(() => {
    if (defaultValues) {
      setFormData(defaultValues)
    }
  }, [defaultValues])

  // Build per-field error map from server validation errors
  const serverFieldErrors = useMemo(() => {
    if (!serverErrors) return {}
    const map: Record<string, string> = {}
    for (const err of serverErrors.errors) {
      if (err.field) {
        // Accumulate multiple errors per field
        map[err.field] = map[err.field]
          ? `${map[err.field]}; ${err.message}`
          : err.message
      }
    }
    return map
  }, [serverErrors])

  // Non-field-level server errors (no field key, or general errors)
  const generalErrors = useMemo(() => {
    if (!serverErrors) return []
    return serverErrors.errors.filter((e) => !e.field)
  }, [serverErrors])

  // Merge client + server errors, client takes precedence (shown during typing)
  const mergedErrors = useMemo(() => {
    return { ...serverFieldErrors, ...clientErrors }
  }, [serverFieldErrors, clientErrors])

  // Determine editable fields
  const editableFields = useMemo(() => {
    if (!metadata) return []

    const fields = fieldOverride
      ? metadata.fields.filter((f) => fieldOverride.includes(f.name))
      : metadata.fields

    return fields.filter((f) => !f.readOnly && !f.primaryKey)
  }, [metadata, fieldOverride])

  const handleChange = (fieldName: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [fieldName]: value }))
    // Clear client error when field is edited
    if (clientErrors[fieldName]) {
      setClientErrors((prev) => {
        const next = { ...prev }
        delete next[fieldName]
        return next
      })
    }
  }

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {}

    for (const field of editableFields) {
      const value = formData[field.name]
      const rules = field.validation
      if (!rules) continue

      const isEmpty = value === undefined || value === null || value === ''

      // Required check
      if (rules.required && isEmpty) {
        newErrors[field.name] = `${field.displayName} is required`
        continue // Skip further checks on empty required fields
      }

      // Skip remaining checks if value is empty (non-required field)
      if (isEmpty) continue

      // String length checks
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

      // Numeric range checks
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

      // Pattern check
      if (rules.pattern && typeof value === 'string') {
        try {
          const regex = new RegExp(rules.pattern)
          if (!regex.test(value)) {
            newErrors[field.name] = `${field.displayName} is not in the expected format`
          }
        } catch {
          // Invalid regex in metadata — skip client-side check, server will catch it
        }
      }
    }

    setClientErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (validate()) {
      onSubmit(formData)
    }
  }

  if (isLoading) {
    return <div className="loading">Loading...</div>
  }

  if (!metadata) {
    return <div className="error">Entity not found</div>
  }

  return (
    <form className="entity-form" onSubmit={handleSubmit}>
      {generalErrors.length > 0 && (
        <div className="form-errors">
          {generalErrors.map((err, i) => (
            <div key={i} className="form-error-banner">{err.message}</div>
          ))}
        </div>
      )}

      {editableFields.map((field) => (
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

      <div className="form-actions">
        {onCancel && (
          <button type="button" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </button>
        )}
        <button type="submit" className="primary" disabled={isSubmitting}>
          {isSubmitting ? 'Saving...' : 'Save'}
        </button>
      </div>
    </form>
  )
}
