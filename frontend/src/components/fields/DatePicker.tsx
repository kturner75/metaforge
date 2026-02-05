import type { FieldComponentProps } from '@/lib/types'

export function DatePicker({ value, onChange, field, disabled, error }: FieldComponentProps<string | null>) {
  // value is ISO date string (YYYY-MM-DD)
  return (
    <input
      type="date"
      className={`field-input ${error ? 'field-error' : ''}`}
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value || null)}
      disabled={disabled}
      placeholder={field.displayName}
    />
  )
}
