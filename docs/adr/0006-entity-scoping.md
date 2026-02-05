# ADR-0006: Entity Scoping (Global vs Tenant)

## Status
Accepted

## Context
MetaForge supports multi-tenant applications where most data is isolated per tenant. However, some data should be shared globally:
- Reference data (government codes, industry standards)
- System configuration
- Shared lookup tables

This scoping affects:
- Row-level access control
- Sequence generation
- Configured validators (Layer 3)
- Query filtering

## Decision
Entities declare their scope in metadata. Default is `tenant`.

### Metadata

```yaml
# /metadata/entities/contract.yaml
name: Contract
scope: tenant              # Default - isolated per tenant

# /metadata/entities/country_code.yaml
name: CountryCode
scope: global              # Shared across all tenants
```

### Scope Behaviors

| Aspect | `scope: tenant` | `scope: global` |
|--------|-----------------|-----------------|
| Row access | Filtered by `tenant_id` | All users see all rows |
| Create | `tenant_id` auto-set from context | `tenant_id` is null |
| Sequences | Scoped to tenant | Global sequence |
| Configured validators | Can have tenant-specific rules | Only global validators |
| Mutations | Users can only modify own tenant | Requires elevated permission |

### Database Schema

```sql
-- Tenant-scoped entity
CREATE TABLE contract (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,    -- Always set
    ...
);
CREATE INDEX idx_contract_tenant ON contract(tenant_id);

-- Global entity
CREATE TABLE country_code (
    id UUID PRIMARY KEY,
    tenant_id UUID NULL,        -- Always null for global
    ...
);
```

### Query Behavior

```python
class QueryService:
    def query(self, entity: str, filter: dict, ctx: UserContext) -> list[dict]:
        metadata = get_entity_metadata(entity)

        if metadata.scope == "tenant":
            # Auto-inject tenant filter
            filter = {
                "and": [
                    {"field": "tenant_id", "op": "eq", "value": ctx.tenant_id},
                    filter
                ]
            }

        return self._execute_query(entity, filter)
```

### Permissions
- Tenant-scoped: Users implicitly filtered to their tenant
- Global:
  - Read: All authenticated users (or configurable)
  - Write: Requires explicit permission (e.g., `admin` role or `manage_reference_data`)

## Consequences

### Positive
- Clear separation of shared vs isolated data
- Reference data maintained once, used by all tenants
- Automatic tenant filtering reduces bugs

### Negative
- Must carefully choose scope - changing later requires migration
- Global write access needs careful permission design

### Future Considerations
- `scope: tenant_shared` - Tenant can create records visible to other tenants (marketplace scenarios)
- `scope: tenant_hierarchy` - Parent tenant data visible to child tenants
