/**
 * AppLayout — shell layout with sidebar and content area.
 */

import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

interface AppLayoutProps {
  userLabel: string
  onLogout: () => void
}

export function AppLayout({ userLabel, onLogout }: AppLayoutProps) {
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-main">
        <header className="app-header">
          <span className="subtitle">{userLabel}</span>
          <button className="ghost" onClick={onLogout}>
            Logout
          </button>
        </header>
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
