/**
 * Screen and navigation types — metadata-driven routing and navigation.
 */

export interface ScreenNav {
  section: string
  order: number
  icon: string | null
  label: string
  requiredRole: string | null
}

export interface ScreenConfig {
  slug: string
  name: string
  type: 'entity' | 'dashboard' | 'admin' | 'custom'
  entityName: string | null
  nav: ScreenNav
  views: Record<string, string> // mode → config ID (e.g., "list" → "yaml:contact-grid")
}

export interface NavSection {
  name: string
  screens: NavScreenItem[]
}

export interface NavScreenItem {
  slug: string
  label: string
  icon: string | null
  type: string
}

export interface NavigationResponse {
  sections: NavSection[]
  defaultScreen: string
}
