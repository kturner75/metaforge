/**
 * Sidebar — metadata-driven navigation with sections, icons, and permission filtering.
 *
 * Fetches the navigation tree from the API and renders grouped screen links.
 * Falls back to static entityRoutes while the API is loading.
 */

import { NavLink } from 'react-router-dom'
import { useNavigation } from '@/hooks/useNavigation'
import { entityRoutes } from '@/lib/routeConfig'
import type { NavSection } from '@/lib/screenTypes'

/** Simple icon map — emoji stand-ins for named icons. Replace with an icon library later. */
const ICON_MAP: Record<string, string> = {
  users: '👥',
  building: '🏢',
  'bar-chart': '📊',
  shield: '🛡️',
  tag: '🏷️',
  settings: '⚙️',
  'dollar-sign': '💰',
  calendar: '📅',
  list: '📋',
  grid: '▦',
}

/** Fallback navigation sections from static routes (shown while API loads). */
const fallbackSections: NavSection[] = [
  {
    name: 'CRM',
    screens: entityRoutes.map((r) => ({
      slug: r.slug,
      label: r.label,
      icon: null,
      type: 'entity',
    })),
  },
]

export function Sidebar() {
  const { data: nav } = useNavigation()

  const sections = nav?.sections ?? fallbackSections

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-mark">Mf</div>
        <span className="sidebar-title">MetaForge</span>
      </div>
      <nav className="sidebar-nav">
        {sections.map((section) => (
          <div key={section.name} className="sidebar-section">
            <div className="sidebar-section-label">{section.name}</div>
            {section.screens.map((screen) => (
              <NavLink
                key={screen.slug}
                to={`/${screen.slug}`}
                className={({ isActive }) =>
                  `sidebar-link${isActive ? ' active' : ''}${screen.isDraft ? ' sidebar-link--draft' : ''}`
                }
              >
                {screen.icon && (
                  <span className="sidebar-icon">
                    {ICON_MAP[screen.icon] ?? '•'}
                  </span>
                )}
                <span className="sidebar-link-label">{screen.label}</span>
                {screen.isDraft && (
                  <span className="sidebar-draft-badge">DRAFT</span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}
