import type { FieldComponentProps } from '@/lib/types'

export function CurrencyInput({ value, onChange, field, disabled, error }: FieldComponentProps<number | null>) {
  return (
    <div className={`field-currency-wrapper ${error ? 'field-error' : ''}`}>
      <span className="field-currency-symbol">$</span>
      <input
        type="number"
        className="field-currency-input"
        value={value ?? ''}
        onChange={(e) => {
          const raw = e.target.value
          onChange?.(raw === '' ? null : Number(raw))
        }}
        disabled={disabled}
        placeholder="0.00"
        min={field.validation?.min}
        max={field.validation?.max}
        step="0.01"
      />
    </div>
  )
}
