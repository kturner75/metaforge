import type { FieldComponentProps } from '@/lib/types'

export function BooleanBadge({ value }: FieldComponentProps<boolean | null>) {
  if (value === null || value === undefined) {
    return <span className="field-empty">—</span>
  }

  const label = value ? 'Yes' : 'No'
  const cls = value ? 'field-badge-yes' : 'field-badge-no'

  return <span className={`field-badge ${cls}`}>{label}</span>
}
