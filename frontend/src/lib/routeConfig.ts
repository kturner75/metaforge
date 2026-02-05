/**
 * Static entity route definitions.
 *
 * Adding CRUD for a new entity requires only a new entry here.
 * Phase 2 will replace this with metadata-driven navigation.
 */

export interface EntityRouteConfig {
  /** URL path segment, e.g. "contacts" */
  slug: string
  /** Canonical entity name matching YAML, e.g. "Contact" */
  entityName: string
  /** Display label for navigation */
  label: string
  /** Optional dashboard widget config IDs for the list view */
  dashboardConfigIds?: {
    kpi?: string
    aggregates?: { id: string; label: string }[]
  }
}

export const entityRoutes: EntityRouteConfig[] = [
  {
    slug: 'contacts',
    entityName: 'Contact',
    label: 'Contacts',
    dashboardConfigIds: {
      kpi: 'yaml:contact-count',
      aggregates: [
        { id: 'yaml:contact-status-bar', label: 'Bar Chart' },
        { id: 'yaml:contact-status-pie', label: 'Pie Chart' },
        { id: 'yaml:contact-status-summary', label: 'Summary Grid' },
      ],
    },
  },
  {
    slug: 'companies',
    entityName: 'Company',
    label: 'Companies',
  },
]

export function getRouteBySlug(slug: string): EntityRouteConfig | undefined {
  return entityRoutes.find((r) => r.slug === slug)
}

export function getRouteByEntity(entityName: string): EntityRouteConfig | undefined {
  return entityRoutes.find((r) => r.entityName === entityName)
}
