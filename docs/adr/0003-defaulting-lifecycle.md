# ADR-0003: Entity Save Lifecycle with Defaulting

## Status
Accepted

## Context
Entity saves need a well-defined lifecycle that:
- Applies default values before validation
- Supports computed/derived fields
- Handles conditional defaults
- Ensures defaults are applied in correct order when they depend on each other

## Decision
We will implement a three-phase save lifecycle: Defaults → Validation → Persist.

### Phase 1: Defaults (Sequential)
Defaults run in declared order because they may compound on each other.

#### Default Types

| Type | Source | When Applied |
|------|--------|--------------|
| Static | Field `default: "value"` | Value is null/blank |
| Auto | Field `auto: now` or `auto: context.userId` | Always (system-managed) |
| Computed | `defaults[]` with `expression` | Per policy and conditions |

#### Defaulting Policy

| Policy | Behavior |
|--------|----------|
| `default` | Apply only when field value is null or empty string |
| `overwrite` | Always apply, replacing any existing value |

#### Metadata Structure

```yaml
fields:
  - name: status
    type: picklist
    default: draft           # Static default

  - name: createdAt
    type: datetime
    auto: now                # System auto-populate

  - name: createdBy
    type: relation
    auto: context.userId     # From user context

defaults:
  # Computed default (policy: default is implicit)
  - field: fullName
    expression: 'concat(firstName, " ", lastName)'
    policy: overwrite        # Always recompute
    on: [create, update]

  # Conditional default
  - field: priority
    value: "high"
    policy: default          # Only if null
    when: 'customer.tier == "enterprise"'
    on: [create]

  # Compounding defaults (order matters)
  - field: regionCode
    expression: 'lookupRegion(state)'
    on: [create]

  - field: contractCode
    expression: 'concat(regionCode, "-", sequence("contract"))'
    on: [create]
    # Works because regionCode was computed above
```

### Phase 2: Validation (Parallel)
After defaults are applied, validation runs. See ADR-0001.
- All validators run (no short-circuit)
- All errors/warnings collected
- Validators have no dependencies, can run in parallel

### Phase 3: Persist
If validation passes (no errors, or warnings acknowledged):
- Before hooks execute
- Database write
- After hooks execute
- Return saved record

## Circular Dependency Detection
At application startup, metadata is validated:
- Build dependency graph from default expressions
- Detect cycles using topological sort
- Fail startup if cycles detected

```
MetadataValidationError: Metadata validation failed:
  - Contract: Circular default dependency: fieldA -> fieldB -> fieldA
```

## Timing Options

| Value | When Default Runs |
|-------|-------------------|
| `on: [create]` | Only on new record creation |
| `on: [update]` | Only on record updates |
| `on: [create, update]` | Both (default if omitted) |

## Consequences

### Positive
- Clear, predictable lifecycle
- Computed fields with proper ordering
- Conditional logic for complex defaulting
- Early detection of configuration errors

### Negative
- Sequential default execution may be slower than parallel
- Order-dependent defaults require careful documentation
- Policy distinction (default vs overwrite) adds cognitive load

### Risks
- Complex default chains hard to debug
- Mitigation: Logging of default application in dev mode
