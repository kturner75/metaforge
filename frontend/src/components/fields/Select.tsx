import type { FieldComponentProps } from '@/lib/types'

interface SelectProps extends FieldComponentProps<string | string[]> {
  mode?: 'single' | 'multi'
}

export function Select({ value, onChange, field, disabled, error, mode = 'single' }: SelectProps) {
  const options = field.options ?? []

  if (mode === 'multi') {
    const selectedValues = Array.isArray(value) ? value : value ? [value] : []

    const handleChange = (optionValue: string) => {
      if (selectedValues.includes(optionValue)) {
        onChange?.(selectedValues.filter((v) => v !== optionValue))
      } else {
        onChange?.([...selectedValues, optionValue])
      }
    }

    return (
      <div className={`field-multi-select ${error ? 'field-error' : ''}`}>
        {options.map((option) => (
          <label key={option.value} className="field-multi-option">
            <input
              type="checkbox"
              checked={selectedValues.includes(option.value)}
              onChange={() => handleChange(option.value)}
              disabled={disabled}
            />
            {option.label}
          </label>
        ))}
      </div>
    )
  }

  return (
    <select
      className={`field-select ${error ? 'field-error' : ''}`}
      value={(value as string) ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
      disabled={disabled}
    >
      <option value="">Select {field.displayName}...</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}
