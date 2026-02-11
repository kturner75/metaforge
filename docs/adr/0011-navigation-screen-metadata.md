# ADR-0011: Navigation & Screen Metadata

## Status
Proposed

## Context
MetaForge currently uses a static `routeConfig.ts` file to define entity routes. Adding a new entity requires manually adding an entry. The sidebar, breadcrumbs, and route structure are all hardcoded in React components.

This creates several problems:
1. **Manual wiring**: Every new entity requires a code change to `routeConfig.ts`
2. **No non-entity screens**: Dashboards, admin pages, and overview screens have no standard routing model
3. **No ordering or grouping**: Navigation sections, icon assignments, and menu ordering are ad-hoc
4. **No breadcrumb context**: Navigating from a Company detail to a Contact detail loses the "came from Company" context
5. **No permission-aware navigation**: All entities appear in the sidebar regardless of the user's access level

The existing comment in `routeConfig.ts` (line 5) already anticipates this: "Phase 2 will replace this with metadata-driven navigation."

### Design Choice: Entity Overview / Detail Page
The `tasks.md` design decisions section documents the approach for entity detail pages: the compose pattern (ADR-0008) with `DetailPage` style handles record headers with tabbed child views. Screens as a first-class concept should build on this foundation, not replace it.

## Decision

### Screen as a First-Class Concept

A **screen** is a routable page in the application. Every screen has a URL, a place in navigation, and a component configuration that determines what it renders. Entity CRUD screens are one type; dashboards, admin pages, and custom screens are others.

```yaml
# metadata/screens/contacts.yaml
screen:
  name: Contacts
  slug: contacts
  type: entity                  # entity | dashboard | admin | custom
  entityName: Contact

  # Navigation placement
  nav:
    section: CRM
    order: 1
    icon: users
    label: Contacts              # defaults to screen name

  # What to render for each mode
  views:
    list: yaml:contact-grid            # config ID for list view
    detail: yaml:company-detail-page   # config ID for detail/overview
    create: yaml:contact-form
    edit: yaml:contact-form
```

```yaml
# metadata/screens/sales-dashboard.yaml
screen:
  name: Sales Dashboard
  slug: sales-dashboard
  type: dashboard

  nav:
    section: Analytics
    order: 1
    icon: bar-chart
    label: Sales

  views:
    default: yaml:sales-dashboard      # compose/dashboard config
```

```yaml
# metadata/screens/user-admin.yaml
screen:
  name: User Management
  slug: admin/users
  type: admin
  entityName: User

  nav:
    section: Admin
    order: 1
    icon: shield
    label: Users
    requiredRole: admin                # only visible to admins

  views:
    list: yaml:user-grid
    detail: yaml:user-detail
    create: yaml:user-form
    edit: yaml:user-form
```

### Navigation Metadata

Navigation structure is derived from screen metadata, not defined separately:

```yaml
# Computed at startup from all screen definitions:
navigation:
  sections:
    - name: CRM
      order: 1
      screens:
        - { slug: contacts, label: Contacts, icon: users, order: 1 }
        - { slug: companies, label: Companies, icon: building, order: 2 }
        - { slug: deals, label: Deals, icon: dollar-sign, order: 3 }

    - name: Analytics
      order: 2
      screens:
        - { slug: sales-dashboard, label: Sales, icon: bar-chart, order: 1 }

    - name: Admin
      order: 99
      requiredRole: admin
      screens:
        - { slug: admin/users, label: Users, icon: shield, order: 1 }
        - { slug: admin/settings, label: Settings, icon: settings, order: 2 }
```

#### Section Ordering
- Sections are ordered by their `order` value (ascending)
- Screens within a section are ordered by their `order` value
- Sections with no visible screens (due to permissions) are hidden

#### Permission-Aware Navigation
- `nav.requiredRole` on a screen or section hides it from users below that role
- Entity-level permissions (ADR-0010) also apply — if a user can't read an entity, its screen is hidden
- The navigation API returns only screens the current user can access

### Screen Types

| Type | URL Pattern | Behavior |
|------|-------------|----------|
| `entity` | `/:slug`, `/:slug/new`, `/:slug/:id`, `/:slug/:id/edit` | Full CRUD routing, delegates to view configs per mode |
| `dashboard` | `/:slug` | Single view, renders a compose-pattern config |
| `admin` | `/admin/:slug` or custom | Admin-specific screens with elevated permission requirements |
| `custom` | configurable | Renders a specified component config |

### Route Generation

Routes are generated at startup from screen metadata. The current `routeConfig.ts` is replaced by a `useScreens()` hook that fetches navigation metadata from the API:

```
GET /api/navigation
→ Returns sections, screens, and permissions for the current user
```

```
GET /api/screens/:slug
→ Returns the full screen definition including view config references
```

The `AppLayout` and `Sidebar` components consume this API instead of importing a static config.

### Breadcrumb System

Breadcrumbs are derived from navigation context and route history:

```
Navigation path:
  CRM > Contacts > Acme Corp > Related Contacts > Jane Doe

Breadcrumb trail:
  Contacts / Acme Corp / Jane Doe
```

#### Breadcrumb Rules

1. **Entity list** → `[Section] / [Entity Label]` → `CRM / Contacts`
2. **Entity detail** → `[Entity Label] / [Record Display Name]` → `Contacts / Jane Doe`
3. **Related record** (navigated from parent detail page) → `[Parent Entity] / [Parent Record] / [Child Record]` → `Companies / Acme Corp / Jane Doe`
4. **Dashboard** → `[Section] / [Dashboard Label]` → `Analytics / Sales`

The "related record" breadcrumb requires tracking the navigation source. When a user clicks a contact from a Company detail page, the URL includes a `from` parameter:

```
/contacts/123?from=companies/456
```

The breadcrumb component resolves this to show the parent context. If no `from` parameter exists (direct navigation), the breadcrumb shows the standard entity list as the parent.

### Backend API

Two new endpoints:

```
GET /api/navigation
```
Returns the navigation tree for the current user, filtered by permissions:
```json
{
  "sections": [
    {
      "name": "CRM",
      "order": 1,
      "screens": [
        { "slug": "contacts", "label": "Contacts", "icon": "users", "type": "entity" }
      ]
    }
  ]
}
```

```
GET /api/screens/:slug
```
Returns the full screen definition:
```json
{
  "name": "Contacts",
  "slug": "contacts",
  "type": "entity",
  "entityName": "Contact",
  "views": {
    "list": "yaml:contact-grid",
    "detail": "yaml:contact-detail-page",
    "create": "yaml:contact-form",
    "edit": "yaml:contact-form"
  }
}
```

### Migration Path

1. Load screen metadata from `metadata/screens/*.yaml` at startup
2. Generate a default screen definition for any entity that has view configs but no screen file (backward compatibility)
3. Remove `routeConfig.ts` once all entities have screen metadata
4. Sidebar and routing components switch from static import to API-driven

## Consequences

### Positive
- Adding a new entity + screen is purely a YAML addition — no code changes
- Navigation ordering, grouping, and icons are explicit and easy to rearrange
- Permission-aware navigation prevents users from seeing screens they can't access
- Breadcrumbs provide meaningful context when navigating between related records
- Dashboard and admin screens are first-class citizens alongside entity CRUD
- AI skills (ADR-0007) can generate screen definitions as part of entity scaffolding

### Negative
- One more YAML file per entity (screen + entity + views)
- Navigation API adds a request on initial load (mitigated by caching)
- Breadcrumb `from` parameter adds complexity to URL management
- Default screen generation for backward compatibility is temporary complexity

### Risks
- **Deep nesting**: Screens referencing screens (dashboard of dashboards) could create complex navigation trees. Mitigation: limit to two levels (section → screen); compose-pattern handles nested content within a screen.
- **Stale navigation cache**: Permission changes don't immediately update the sidebar. Mitigation: invalidate navigation cache on role/permission changes; short stale time.
- **Screen proliferation**: Many screens with slight variations. Mitigation: screens reference view configs, not duplicate them; the same view config can be used across multiple screens.

### Alternatives Considered
- **Derive screens from entities automatically**: No separate screen metadata — generate from entity + view configs. Rejected: doesn't handle dashboards, admin screens, or custom ordering. Automatic generation is the fallback, not the primary mechanism.
- **Separate navigation.yaml file**: One central file defining all navigation. Rejected: becomes a merge conflict magnet in teams; co-locating nav config with screen definitions is more modular.
- **Client-side breadcrumb tracking**: Use browser history instead of URL parameters. Rejected: breaks on direct URL access and page refresh.

### Dependencies
- ADR-0008 (UI Component Configuration): screens reference component configs for rendering
- ADR-0010 (Auth & Permissions): screen visibility filtered by entity-level and role-level permissions
- ADR-0007 (Agent Skills): `create-entity` skill should also generate a screen definition
