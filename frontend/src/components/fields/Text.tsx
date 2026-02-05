import type { FieldComponentProps } from '@/lib/types'

export function Text({ value }: FieldComponentProps<string | null>) {
  if (value === null || value === undefined) {
    return <span className="field-empty">—</span>
  }

  return <span className="field-text">{value}</span>
}
