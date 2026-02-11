# ADR-0010: Declarative Auth & Permissions Model

## Status
Proposed

## Context
MetaForge currently has a working auth system with:
- **JWT tokens**: access (15min), refresh (7d), password reset
- **Role hierarchy**: `readonly` < `user` < `manager` < `admin`
- **Entity-level access**: hardcoded rules in `permissions.py` — all authenticated users can read; create/update requires `user+`; delete requires `manager+`; global entity writes require `admin`
- **Tenant isolation**: automatic `tenant_id` filtering for tenant-scoped entities (ADR-0006)

This works for bootstrapping, but real applications need:
1. **Per-entity permission overrides** — not all entities should follow the same role thresholds
2. **Row-level access** — a sales rep should only see their own deals, a manager sees their team's deals
3. **Field-level access** — salary fields hidden from non-HR roles, SSN redacted except for authorized users
4. **Metadata-driven** — permissions declared in YAML alongside entities, not scattered across Python code

### Requirements
- Permissions are part of the metadata, co-located with entity definitions
- Role hierarchy remains the foundation, with per-entity and per-field overrides
- Row-level policies compose with tenant filtering (ADR-0006), not replace it
- Field-level policies affect both API responses and UI rendering
- The UI uses the same permission metadata to show/hide fields and actions

## Decision

### Permission Declaration in Entity Metadata

Each entity can declare permissions that override the global defaults:

```yaml
# metadata/entities/deal.yaml
name: Deal
scope: tenant

permissions:
  # Entity-level: which roles can perform which operations
  access:
    read: user           # default: readonly
    create: user         # default: user
    update: user         # default: user
    delete: manager      # default: manager

  # Row-level: filter rows based on user context
  rowPolicies:
    - name: ownerOnly
      roles: [user]
      filter:
        field: ownerId
        op: eq
        value: context.userId
      description: "Users see only their own deals"

    - name: teamDeals
      roles: [manager]
      filter:
        field: teamId
        op: eq
        value: context.teamId
      description: "Managers see their team's deals"

    # admin has no row policy — sees all tenant records

  # Field-level: hide or redact fields by role
  fieldPolicies:
    - field: commission
      read: manager       # below manager: field omitted from response
      write: admin        # only admin can set commission

    - field: internalNotes
      read: user          # readonly users cannot see
      write: manager      # users can read but not edit
```

### Entity-Level Access

The `access` block maps operations to minimum role levels. This replaces the hardcoded rules in `permissions.py`:

```yaml
permissions:
  access:
    read: readonly        # minimum role to read (default: readonly)
    create: user          # minimum role to create (default: user)
    update: user          # minimum role to update (default: user)
    delete: manager       # minimum role to delete (default: manager)
```

Entities without an `access` block use the framework defaults (current behavior). Global entities (ADR-0006) additionally require `admin` for writes unless explicitly overridden.

### Row-Level Access Policies

Row policies inject additional query filters based on the user's role and context. They compose **on top of** tenant filtering — tenant isolation always applies first for tenant-scoped entities.

#### Resolution Rules

1. Policies are evaluated from most restrictive role upward
2. The **first matching policy** for the user's role applies (most specific wins)
3. If no policy matches the user's role, no additional row filter is applied (full access within tenant)
4. Higher roles inherit access — a `manager` policy also applies to `admin` unless `admin` has its own policy

```python
def get_row_filter(entity: EntityMetadata, user: UserContext) -> Filter | None:
    """Returns the row-level filter for this user, or None for full access."""
    if not entity.permissions or not entity.permissions.row_policies:
        return None

    # Find the most specific policy for the user's role
    for policy in entity.permissions.row_policies:
        if user.role in policy.roles:
            return evaluate_filter(policy.filter, user)

    # No matching policy — no additional restriction
    return None
```

#### Filter Expressions

Row policy filters use the same `FilterCondition` structure as query filters, with `context.*` references resolved from the user context:

```yaml
filter:
  field: ownerId
  op: eq
  value: context.userId      # resolved at query time
```

Supported context references:
- `context.userId` — current user's ID
- `context.tenantId` — current tenant ID
- `context.roles` — user's role list
- `context.teamId` — user's team (when team model is implemented)

Compound filters use the same `and`/`or` structure as query filters:

```yaml
filter:
  operator: or
  conditions:
    - field: ownerId
      op: eq
      value: context.userId
    - field: sharedWith
      op: contains
      value: context.userId
```

### Field-Level Access Policies

Field policies control visibility and editability per role:

```yaml
fieldPolicies:
  - field: salary
    read: manager          # roles below manager: field omitted from API response
    write: admin           # roles below admin: field is read-only
```

#### Enforcement Points

| Point | Behavior |
|-------|----------|
| **API read** (GET, query) | Fields below the user's `read` level are omitted from the response |
| **API write** (POST, PUT) | Fields below the user's `write` level are silently ignored in the payload |
| **Metadata endpoint** | `GET /api/metadata/{entity}` includes field-level `access` annotations for the current user |
| **UI rendering** | Frontend reads field access from metadata to hide fields or render as read-only |

#### Metadata Response Enrichment

The metadata endpoint annotates fields with the current user's effective permissions:

```json
{
  "name": "salary",
  "type": "currency",
  "access": {
    "read": true,
    "write": false
  }
}
```

The frontend uses this to:
- Hide fields from grids/forms/detail views when `read: false`
- Render fields as read-only in forms when `write: false`
- Hide columns from column pickers
- Exclude fields from filter/sort options

### Permission Resolution Flow

```
Request arrives
  │
  ├─ 1. Authenticate (JWT → UserContext)
  │
  ├─ 2. Entity-level check
  │    └─ Can this role perform this operation on this entity?
  │    └─ If no: 403 Forbidden
  │
  ├─ 3. Tenant filter (ADR-0006)
  │    └─ If scope: tenant → inject tenant_id filter
  │
  ├─ 4. Row-level filter
  │    └─ Find matching row policy for user's role
  │    └─ Inject additional filter conditions
  │
  ├─ 5. Execute query / operation
  │
  └─ 6. Field-level filter
       └─ Strip fields the user cannot read from response
       └─ On write: strip fields the user cannot write from payload
```

### Admin UI

An admin screen will allow tenant admins to manage:
- Custom roles beyond the base hierarchy (future — requires role metadata extension)
- Role assignments for tenant members
- Visibility into effective permissions per user per entity

This is a runtime UI concern, not a metadata change — built as a compose-pattern screen (ADR-0008) once the permission model is implemented.

## Consequences

### Positive
- Permissions co-located with entity metadata — single source of truth
- Row-level policies compose naturally with existing tenant filtering
- Field-level policies enforce both API security and UI rendering from the same definition
- Frontend gets permission hints from the metadata endpoint — no duplicate permission logic
- Existing role hierarchy preserved; per-entity overrides are additive

### Negative
- Row-level policies with `context.*` references add query complexity
- Field stripping on every response has a (small) performance cost
- Per-entity permission overrides increase the surface area developers must review
- Field-level policies on relation fields may interact subtly with display value hydration

### Risks
- **Policy conflicts**: Multiple row policies could produce contradictory filters. Mitigation: first-match-wins rule with explicit role targeting; document that policies should be ordered from most to least restrictive.
- **Performance**: Row-level filters on non-indexed fields could slow queries. Mitigation: recommend indexing fields used in row policies.
- **Complexity creep**: Full ABAC (attribute-based access control) is tempting but premature. Mitigation: start with role-based policies with context references; evaluate ABAC only if real use cases demand it.

### Alternatives Considered
- **Separate permissions file**: Permissions in a dedicated YAML file per entity. Rejected: co-location with the entity definition is more discoverable and reduces drift.
- **Full ABAC from the start**: Attribute-based policies with arbitrary conditions. Rejected: too complex for the initial implementation; role-based with context references covers 90% of use cases.
- **Permissions as code only**: Define in Python, not YAML. Rejected: breaks the metadata-driven philosophy; permissions should be visible to the AI skills layer (ADR-0007) and the admin UI.

### Dependencies
- ADR-0006 (Entity Scoping): row-level policies compose on top of tenant filtering
- ADR-0001 (Validation Architecture): permission checks run before validation
- ADR-0008 (UI Component Configuration): field-level access affects which fields appear in view configs
- ADR-0007 (Agent Skills): skills need permission context to generate valid configurations
