# ADR-0009: Entity Lifecycle Hook System

## Status
Accepted

## Context
The entity save lifecycle (ADR-0003) currently follows a fixed three-phase pipeline: Defaults → Validation → Persist. ADR-0003 mentions "before hooks execute / after hooks execute" in Phase 3, but no hook architecture has been defined.

Real-world applications need extension points for logic that doesn't fit into defaults or validation:
- **Audit logging**: record who changed what, when
- **Side effects**: send email on status change, sync to external system
- **Derived data**: update denormalized counts, recompute parent summaries
- **Cascading operations**: archive child records when parent is archived
- **Access control enforcement**: custom row-level checks beyond tenant scoping

Without a hook system, this logic either gets shoehorned into validators (wrong semantics — validators report errors, not execute side effects) or hardcoded into API endpoints (bypassed by bulk operations or internal callers).

### Requirements
- Hooks declared in entity metadata (YAML), not scattered across code
- Clear execution order relative to the existing lifecycle phases
- Support for both synchronous (blocking) and fire-and-forget patterns
- Access to before/after state for change detection
- Hooks must not break the safety guarantees of the validation layer

## Decision

### Hook Points

We will add four hook points to the entity lifecycle:

```
Phase 1: Defaults (existing)
Phase 2: Validation (existing)
    ↓
  beforeSave       ← NEW: post-validation, pre-persist
    ↓
Phase 3: Persist
    ↓
  afterSave        ← NEW: post-persist, same transaction
    ↓
  afterCommit      ← NEW: post-commit, side effects
```

Additionally, for delete operations:

```
  beforeDelete     ← NEW: pre-delete, can abort
    ↓
  Delete
    ↓
  afterCommit      ← reused for delete side effects
```

| Hook | Timing | Can Abort? | Has DB Access? | Use Case |
|------|--------|-----------|----------------|----------|
| `beforeSave` | After validation passes, before persist | Yes (throw error) | Yes (same txn) | Transform data, enforce custom rules, set computed fields that depend on validation passing |
| `afterSave` | After persist, before commit | Yes (throw rolls back) | Yes (same txn) | Update related records, maintain denormalized data |
| `afterCommit` | After transaction commits | No | New transaction | Send notifications, sync external systems, enqueue jobs |
| `beforeDelete` | Before delete executes | Yes (throw error) | Yes (same txn) | Custom delete guards beyond `noActiveChildren` |

### Metadata Declaration

Hooks are declared per-entity in metadata, referencing registered hook implementations:

```yaml
# metadata/entities/contract.yaml
name: Contract
scope: tenant

hooks:
  beforeSave:
    - name: computeContractValue
      on: [create, update]
      description: "Recalculate total value from line items"

    - name: enforceApprovalWorkflow
      on: [update]
      when: 'status != original.status && status == "approved"'
      description: "Require manager role for approval transitions"

  afterSave:
    - name: updateCompanySummary
      on: [create, update, delete]
      description: "Recalculate company's total contract value"

  afterCommit:
    - name: sendStatusChangeEmail
      on: [update]
      when: 'status != original.status'
      description: "Notify stakeholders of status changes"

  beforeDelete:
    - name: archiveInsteadOfDelete
      description: "Soft-delete by setting status to archived"
```

### Hook Context

Every hook receives a `HookContext` with full state:

```python
@dataclass
class HookContext:
    entity_name: str
    operation: str              # "create", "update", "delete"
    record: dict                # current record (post-defaults, post-validation)
    original: dict | None       # previous record (update only)
    changes: dict | None        # diff of changed fields (update only)
    user_context: UserContext    # auth context (userId, tenantId, roles)
    db: DatabaseSession         # for beforeSave/afterSave (same transaction)
```

### Hook Registration

Hooks are Python functions registered with a decorator, similar to how canned validators work:

```python
from metaforge.hooks import hook

@hook("computeContractValue")
async def compute_contract_value(ctx: HookContext) -> HookResult:
    line_items = await ctx.db.query("ContractLineItem", {
        "field": "contractId", "op": "eq", "value": ctx.record["id"]
    })
    total = sum(item["amount"] for item in line_items)
    return HookResult(update={"totalValue": total})

@hook("sendStatusChangeEmail")
async def send_status_change_email(ctx: HookContext) -> None:
    # afterCommit — fire and forget, no return value
    await email_service.send(
        template="status-change",
        to=ctx.record["ownerEmail"],
        data={"old": ctx.original["status"], "new": ctx.record["status"]}
    )
```

### HookResult

`beforeSave` and `afterSave` hooks return a `HookResult` that can modify the record:

```python
@dataclass
class HookResult:
    update: dict | None = None     # fields to merge into the record
    abort: str | None = None       # error message to abort the save
```

- `update` fields are merged into the record before persist (beforeSave) or applied as an additional update (afterSave)
- `abort` raises a validation-style error and rolls back the transaction
- `afterCommit` hooks return `None` — they cannot modify or abort

### Execution Order

1. Hooks within a hook point execute **sequentially in declared order** (like defaults in ADR-0003)
2. Each hook's `update` output is merged before the next hook runs (compounding)
3. If any hook aborts, subsequent hooks in that point do not run
4. `afterCommit` hooks run sequentially but failures are logged, not propagated (the save already succeeded)

### Conditional Execution

Hooks support the same `when:` expression syntax as defaults (ADR-0002/0003) and the same `on:` timing as validators (ADR-0001):

- `on: [create]` — only runs on create
- `on: [update]` — only runs on update
- `on: [create, update]` — default if omitted
- `when: 'expression'` — evaluated against the record; hook skipped if false

### Updated Full Lifecycle

```
Create/Update Request
  │
  ├─ Phase 1: Apply Defaults (ADR-0003)
  │    └─ Static → Auto → Computed (sequential)
  │
  ├─ Phase 2: Validate (ADR-0001)
  │    └─ All layers in parallel → collect errors/warnings
  │    └─ If errors: return 422
  │    └─ If warnings without token: return 202
  │
  ├─ Phase 3a: beforeSave hooks (sequential)
  │    └─ Can update record fields
  │    └─ Can abort (rolls back, returns error)
  │
  ├─ Phase 3b: Persist to database
  │
  ├─ Phase 3c: afterSave hooks (sequential, same transaction)
  │    └─ Can update related records
  │    └─ Can abort (rolls back entire transaction)
  │
  ├─ Phase 3d: Commit transaction
  │
  └─ Phase 4: afterCommit hooks (sequential, fire-and-forget)
       └─ Side effects, notifications, external syncs
       └─ Failures logged but do not affect response
```

## Consequences

### Positive
- Clear, well-defined extension points for application logic
- Metadata-declared hooks are discoverable and documented
- Conditional execution via `when:` keeps simple cases simple
- Transaction boundaries are explicit — developers know what can roll back
- Same expression DSL (ADR-0002) used for conditions

### Negative
- Sequential hook execution may slow saves when many hooks are declared
- Hooks that modify records (`update` in HookResult) create implicit data flow
- `afterCommit` failures are silent from the caller's perspective

### Risks
- **Hook ordering dependencies**: Hooks within a point run in declared order, but cross-entity hook interactions are not managed. Mitigation: document that hooks should be self-contained; cross-entity side effects belong in `afterSave` or `afterCommit`.
- **Performance**: Many hooks with database queries could slow saves. Mitigation: monitor hook execution time in dev mode; consider parallel execution for independent hooks in a future iteration.
- **Testing**: Hooks with side effects are harder to test in isolation. Mitigation: `HookContext` is a plain dataclass, easy to construct in tests.

### Alternatives Considered
- **Event bus / pub-sub**: More decoupled but harder to reason about ordering and transaction boundaries. Better suited to a microservices architecture; MetaForge is monolith-first.
- **Middleware-style pipeline**: Every hook wraps the next in a chain. More flexible but harder to declare in YAML and reason about.
- **Expression-only hooks**: Limit hooks to DSL expressions (no Python). Too restrictive — side effects and external calls need real code.

### Dependencies
- ADR-0003 (Defaulting Lifecycle): hooks extend the existing save lifecycle
- ADR-0001 (Validation Architecture): hooks run after validation; `abort` produces validation-style errors
- ADR-0002 (Expression Language DSL): `when:` conditions use the expression evaluator
