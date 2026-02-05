import type { FieldComponentProps } from '@/lib/types'

export function TextArea({ value, onChange, field, disabled, error }: FieldComponentProps<string>) {
  return (
    <textarea
      className={`field-textarea ${error ? 'field-error' : ''}`}
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
      disabled={disabled}
      placeholder={field.displayName}
      rows={3}
    />
  )
}
