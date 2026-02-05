import type { FieldComponentProps } from '@/lib/types'

export function TextInput({ value, onChange, field, disabled, error }: FieldComponentProps<string>) {
  return (
    <input
      type={field.type === 'email' ? 'email' : 'text'}
      className={`field-input ${error ? 'field-error' : ''}`}
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
      disabled={disabled}
      placeholder={field.displayName}
    />
  )
}
