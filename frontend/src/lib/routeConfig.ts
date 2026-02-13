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
}

export const entityRoutes: EntityRouteConfig[] = [
  {
    slug: 'contacts',
    entityName: 'Contact',
    label: 'Contacts',
  },
  {
    slug: 'companies',
    entityName: 'Company',
    label: 'Companies',
  },
  {
    slug: 'categories',
    entityName: 'Category',
    label: 'Categories',
  },
]

export function getRouteBySlug(slug: string): EntityRouteConfig | undefined {
  return entityRoutes.find((r) => r.slug === slug)
}

export function getRouteByEntity(entityName: string): EntityRouteConfig | undefined {
  return entityRoutes.find((r) => r.entityName === entityName)
}
