/**
 * FieldRenderer - resolves field type to component and renders it.
 */

import type { FieldMetadata, UIContext } from '@/lib/types'
import { getFieldComponent } from '@/lib/fieldRegistry'

interface FieldRendererProps {
  field: FieldMetadata
  context: UIContext
  value: unknown
  onChange?: (value: unknown) => void
  disabled?: boolean
  error?: string
}

export function FieldRenderer({
  field,
  context,
  value,
  onChange,
  disabled,
  error,
}: FieldRendererProps) {
  const Component = getFieldComponent(field.type, context)

  // Get context-specific props from field UI config
  const uiConfig = field.ui[context]

  return (
    <Component
      value={value}
      onChange={onChange}
      field={field}
      disabled={disabled}
      error={error}
      mode={field.type === 'multi_picklist' || (context === 'filter' && field.type === 'picklist') ? 'multi' : 'single'}
      {...uiConfig}
    />
  )
}
