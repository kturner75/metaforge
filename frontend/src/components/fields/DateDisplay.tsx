import type { FieldComponentProps } from '@/lib/types'

function formatDate(iso: string | null, includeTime: boolean): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    ...(includeTime && { hour: 'numeric', minute: '2-digit' }),
  }
  return d.toLocaleDateString('en-US', options)
}

export function DateDisplay({ value, field }: FieldComponentProps<string | null>) {
  if (value === null || value === undefined) {
    return <span className="field-empty">—</span>
  }

  const includeTime = field.type === 'datetime'
  return <span className="field-text">{formatDate(value, includeTime)}</span>
}
