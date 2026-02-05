import type { FieldComponentProps } from '@/lib/types'

export function DateTimePicker({ value, onChange, field, disabled, error }: FieldComponentProps<string | null>) {
  // value is ISO datetime string; HTML datetime-local needs "YYYY-MM-DDThh:mm"
  const toLocalValue = (iso: string | null): string => {
    if (!iso) return ''
    // Handle both "2024-01-15T10:30:00Z" and "2024-01-15T10:30"
    return iso.slice(0, 16)
  }

  const toISOValue = (local: string): string | null => {
    if (!local) return null
    return new Date(local).toISOString()
  }

  return (
    <input
      type="datetime-local"
      className={`field-input ${error ? 'field-error' : ''}`}
      value={toLocalValue(value)}
      onChange={(e) => onChange?.(toISOValue(e.target.value))}
      disabled={disabled}
      placeholder={field.displayName}
    />
  )
}
