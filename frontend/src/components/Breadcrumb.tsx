/**
 * Breadcrumb — context-aware navigation trail.
 *
 * Renders a `/`-separated list of crumbs. All crumbs except the last are
 * clickable links. The last crumb represents the current page and is
 * rendered as plain text.
 */

import { Link } from 'react-router-dom'

export interface BreadcrumbItem {
  label: string
  href?: string // undefined = current (non-linked) crumb
}

interface BreadcrumbProps {
  items: BreadcrumbItem[]
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  if (items.length === 0) return null

  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      {items.map((item, i) => {
        const isLast = i === items.length - 1
        return (
          <span key={i} className="breadcrumb-item">
            {i > 0 && <span className="breadcrumb-separator" aria-hidden="true">/</span>}
            {isLast || !item.href ? (
              <span className={isLast ? 'breadcrumb-current' : 'breadcrumb-inactive'}>
                {item.label}
              </span>
            ) : (
              <Link className="breadcrumb-link" to={item.href}>
                {item.label}
              </Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
