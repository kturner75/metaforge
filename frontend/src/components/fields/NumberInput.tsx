import type { FieldComponentProps } from '@/lib/types'

export function NumberInput({ value, onChange, field, disabled, error }: FieldComponentProps<number | null>) {
  return (
    <input
      type="number"
      className={`field-input field-input-number ${error ? 'field-error' : ''}`}
      value={value ?? ''}
      onChange={(e) => {
        const raw = e.target.value
        onChange?.(raw === '' ? null : Number(raw))
      }}
      disabled={disabled}
      placeholder={field.displayName}
      min={field.validation?.min}
      max={field.validation?.max}
      step="any"
    />
  )
}
