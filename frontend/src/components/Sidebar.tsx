/**
 * Sidebar — left navigation with entity links.
 *
 * Phase 1: Reads from static entityRoutes.
 * Phase 2: Will read from navigation metadata.
 */

import { NavLink } from 'react-router-dom'
import { entityRoutes } from '@/lib/routeConfig'

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-mark">Mf</div>
        <span className="sidebar-title">MetaForge</span>
      </div>
      <nav className="sidebar-nav">
        {entityRoutes.map((route) => (
          <NavLink
            key={route.slug}
            to={`/${route.slug}`}
            className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
          >
            {route.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
