# ADR-0001: Three-Layer Validation Architecture

## Status
Accepted

## Context
MetaForge needs a validation system that supports:
- Common reusable validators (date ranges, uniqueness, etc.)
- Application-specific business rules defined in metadata
- Dynamic, tenant-scoped validation rules stored in the database

## Decision
We will implement a three-layer validation architecture:

### Layer 0: Field-Level Rules
Basic constraints defined on fields: `required`, `min`, `max`, `minLength`, `maxLength`, `pattern`.

### Layer 1: Canned Validators (Framework)
Reusable validators shipped with MetaForge, explicitly declared in entity metadata:
- `dateRange` - Validate start/end date relationships
- `unique` - Field uniqueness (global or tenant-scoped)
- `conditionalRequired` - Required based on condition
- `fieldComparison` - Compare two field values
- `immutable` - Prevent field changes after create
- `referenceExists` - Foreign key must exist
- `referenceActive` - Referenced record must be active
- `noActiveChildren` - Safe delete validation

### Layer 2: Application Validators
Custom validators defined in source-controlled metadata:
- Expression validators using the DSL (see ADR-0002)
- Custom coded validators with explicit registration

### Layer 3: Configured Validators
Dynamic validators stored in database, scoped to tenant:
- Same structure as Layer 2
- Managed via admin UI or API
- Filtered by `tenant_id` from user context

## Validation Behavior

### Execution
- All layers run for every validation (no short-circuit)
- All errors and warnings are collected and returned together
- Validators within a layer run in parallel (no dependencies)

### Strictness
- Higher layers can only add stricter rules, not relax lower layer rules
- Layer 0/1/2 rules are global; Layer 3 adds tenant-specific constraints

### Timing
- Default: validators run on `create` and `update`
- Can specify: `on: [create]`, `on: [update]`, `on: [delete]`
- Delete validators run before delete to prevent unsafe deletions

### Severity
- `error` - Blocks the save operation
- `warning` - Allows save but requires explicit user acknowledgment

## Consequences

### Positive
- Clear separation of framework, application, and tenant-specific rules
- Consistent validation interface across all layers
- Supports both declarative and coded validators

### Negative
- Three layers add complexity to understand and debug
- Tenant-scoped validators require careful security review

### Risks
- Performance: Many validators across layers could slow saves
- Mitigation: Run validators in parallel, cache compiled expressions
