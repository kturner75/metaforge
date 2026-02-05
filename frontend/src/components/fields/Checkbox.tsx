import type { FieldComponentProps } from '@/lib/types'

export function Checkbox({ value, onChange, field, disabled }: FieldComponentProps<boolean | null>) {
  return (
    <label className="field-checkbox">
      <input
        type="checkbox"
        checked={!!value}
        onChange={(e) => onChange?.(e.target.checked)}
        disabled={disabled}
      />
      <span className="field-checkbox-label">{field.displayName}</span>
    </label>
  )
}
