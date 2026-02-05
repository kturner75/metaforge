import type { FieldComponentProps } from '@/lib/types'

export function MultiPicklistBadges({ value, field }: FieldComponentProps<string[] | null>) {
  if (!value || !Array.isArray(value) || value.length === 0) {
    return <span className="field-empty">—</span>
  }

  return (
    <span className="field-multi-badges">
      {value.map((v) => {
        const option = field.options?.find((o) => o.value === v)
        const label = option?.label ?? v
        return (
          <span key={v} className={`field-badge field-badge-${v}`}>
            {label}
          </span>
        )
      })}
    </span>
  )
}
