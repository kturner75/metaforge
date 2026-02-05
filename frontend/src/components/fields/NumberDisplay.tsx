import type { FieldComponentProps } from '@/lib/types'

export function NumberDisplay({ value, field }: FieldComponentProps<number | null>) {
  if (value === null || value === undefined) {
    return <span className="field-empty">—</span>
  }

  let formatted: string

  if (field.type === 'currency') {
    formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value)
  } else if (field.type === 'percent') {
    formatted = new Intl.NumberFormat('en-US', {
      style: 'percent',
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(value / 100)
  } else {
    formatted = new Intl.NumberFormat('en-US').format(value)
  }

  return <span className="field-text field-text-number">{formatted}</span>
}
