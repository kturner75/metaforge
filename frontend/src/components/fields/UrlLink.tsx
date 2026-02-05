import type { FieldComponentProps } from '@/lib/types'

export function UrlLink({ value }: FieldComponentProps<string | null>) {
  if (value === null || value === undefined || value === '') {
    return <span className="field-empty">—</span>
  }

  return (
    <a
      className="field-url"
      href={value}
      target="_blank"
      rel="noopener noreferrer"
    >
      {value.replace(/^https?:\/\//, '')}
    </a>
  )
}
