import type { FieldComponentProps } from '@/lib/types'

export function Badge({ value, field }: FieldComponentProps<string | null>) {
  if (value === null || value === undefined) {
    return <span className="field-empty">—</span>
  }

  // Find label from options
  const option = field.options?.find((o) => o.value === value)
  const label = option?.label ?? value

  return <span className={`field-badge field-badge-${value}`}>{label}</span>
}
