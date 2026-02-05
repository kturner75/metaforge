# ADR-0007: Agent Skills Architecture

## Status
Accepted

## Context
MetaForge is metadata-driven: entities, fields, validations, defaults, and UI behavior are all declared as configuration rather than code. This creates a natural surface for AI assistance — the AI doesn't generate code, it generates **configuration** that the framework already knows how to consume.

Two audiences benefit from this:

1. **Developers** (dev-time): scaffolding entities, writing validation rules, defining defaults, building views — all as YAML metadata committed to source control.
2. **End users** (runtime): configuring filters, views, charts, and dashboards inside the running application — stored as Layer 3 configuration in the database.

Both audiences produce the same metadata structures. The framework renders from configuration regardless of origin. This means a single AI skill can serve both contexts — the only difference is where the output is persisted.

### Motivating Example
A user is on a Contact Search List. The default filters show name, email, and company. The user says:

> "show me active, unhealthy"

The AI knows the Contact entity has a `status` picklist (with "active") and a `healthStatus` picklist (with "unhealthy"). It produces a filter configuration:

```yaml
filters:
  - field: status
    operator: eq
    value: active
  - field: healthStatus
    operator: eq
    value: unhealthy
```

The filter applies immediately — live data, no deployment. The AI then asks about scoping: save as a personal filter, or share with the team? The result is a row in a Layer 3 configuration table, consumed by the same Search List component that reads developer-authored YAML.

## Decision

### Skills as Metadata-Native Operations

A **skill** is a scoped capability that takes natural-language intent plus metadata context and produces validated, typed configuration. Skills are the unit of AI interaction in MetaForge.

#### Skill Definition

```yaml
skill:
  name: create-filter
  domain: views              # what part of the system it touches
  description: Create or modify entity filters from natural language

  context:                   # what the skill receives automatically
    - entityMetadata         # fields, types, options, relations
    - currentView            # active component context (search list, grid, etc.)
    - userPermissions        # sharing scope, role

  inputSchema:               # structured params (post-NL-parsing)
    entityName: string
    intent: string           # the natural language description
    currentFilters: FilterConfig[]  # existing filters to modify

  outputSchema:              # what the skill produces
    $ref: FilterConfig       # same schema the UI components consume

  verify:                    # validation before applying
    - expressionsParse       # any DSL expressions must be syntactically valid
    - fieldsExist            # referenced fields must exist on the entity
    - valuesValid            # filter values must match field type/options

  targets:                   # where output can be persisted
    - layer3                 # database (runtime, user-scoped)
    - yaml                   # source-controlled metadata (dev-time)
```

#### Core Skill Catalog

| Skill | Domain | Output Schema | Description |
|-------|--------|--------------|-------------|
| `create-filter` | views | `DataConfig.filters` | Build entity filters from natural language |
| `configure-view` | views | `ComponentConfig` | Configure any data pattern + presentation style |
| `create-chart` | views | `ComponentConfig` (aggregate) | Summary visualizations (bar, pie, line, KPI) |
| `configure-dashboard` | views | `ComponentConfig` (compose) | Dashboard layout and panel composition |
| `switch-style` | views | `presentation` only | Swap presentation style, keeping data config intact |
| `add-validation-rule` | validation | `ValidatorConfig` | Validation rules from business requirements |
| `add-default` | validation | `DefaultConfig` | Default values and computed fields |
| `create-entity` | entities | `EntityModel` | Entity scaffolding from description |
| `add-field` | entities | `FieldDefinition` | Add fields to existing entities |
| `add-relation` | entities | `FieldDefinition` | Define entity relationships |

### Context Assembly

Every skill invocation receives relevant metadata context so the AI can generate valid output. The **context assembler** gathers this automatically based on the skill's declared `context` requirements:

```
User intent + Skill definition
        │
        ▼
┌─────────────────────┐
│  Context Assembler   │
│                      │
│  • Entity metadata   │  ← MetadataLoader (existing)
│  • Field types       │  ← FieldTypeRegistry (existing)
│  • Function registry │  ← Expression functions (existing)
│  • Current view      │  ← UI component state
│  • User permissions  │  ← Auth context (existing)
│  • Existing config   │  ← Layer 3 tables
└──────────┬──────────┘
           │
           ▼
     LLM generates
     structured output
           │
           ▼
┌─────────────────────┐
│  Output Verifier     │
│                      │
│  • Schema validation │
│  • Expression parse  │
│  • Field existence   │
│  • Value validation  │
└──────────┬──────────┘
           │
           ▼
     Verified config
           │
     ┌─────┴─────┐
     ▼           ▼
   YAML       Layer 3
  (dev)      (runtime)
```

### Composability

Skills can compose into **plans** — ordered sequences where each step's output feeds into subsequent steps. A higher-order skill decomposes a complex request into a plan of atomic skills.

Example: "Create a Project entity with tasks, statuses, due dates, and warn if overdue"

```
Plan:
  1. create-entity     → EntityModel (Project: name, status, dueDate, owner)
  2. add-relation      → FieldDefinition (Task.projectId → Project)
  3. add-default       → DefaultConfig (status defaults to "draft")
  4. add-validation    → ValidatorConfig (warn if dueDate < today and status != "completed")
```

The plan is presented to the user as a structured preview. Each step can be individually reviewed, modified, or removed before execution. Steps execute sequentially — later steps receive the accumulated context from earlier steps.

### Hybrid Interaction Model

The interaction follows a three-phase loop:

```
Phase 1: Natural Language
  User describes intent → AI generates configuration

Phase 2: Structured Editor
  Generated config displayed in typed editor → User refines
  AI assists inline (suggests expressions, auto-completes field references)

Phase 3: Verify & Apply
  Output validated against schemas → Applied to target (YAML or Layer 3)
  User confirms scope (personal, team, role-based)
```

The user can enter at any phase. Power users may go straight to the structured editor. The AI is available as a copilot in Phase 2, not just as the entry point in Phase 1.

### Dev-Time vs Runtime

The same skill definition serves both contexts. The difference is routing:

| Aspect | Dev-Time | Runtime |
|--------|----------|---------|
| **Target** | YAML files in `metadata/` | Layer 3 database tables |
| **Scope** | Global (all tenants) | Tenant-scoped (or user-scoped) |
| **Review** | Code review / PR | Admin approval or self-service |
| **Rollback** | Git revert | Soft delete / version history |
| **Promotion** | n/a | Promote from Layer 3 to YAML (graduate to code) |

"Promotion" is a notable capability: a tenant admin configures a filter or validation rule at runtime. If it proves generally useful, a developer can promote it from Layer 3 to Layer 2 (source-controlled YAML), making it a permanent part of the application.

### Safety Boundaries

Skills never produce arbitrary code. All output conforms to defined schemas:

- **Expression DSL** (ADR-0002): sandboxed evaluation, no arbitrary execution
- **Schema validation**: output must match the declared `outputSchema`
- **Field existence**: referenced fields must exist on the target entity
- **Value validation**: picklist values must be valid options, types must match
- **Permission checks**: user must have permission to create/modify the target configuration
- **Scope enforcement**: tenant-scoped output cannot reference cross-tenant data

The verifier runs before any configuration is applied. Invalid output is rejected with an explanation, and the AI can retry or the user can fix manually in the structured editor.

### LLM Integration

The LLM integration layer is intentionally thin. The intelligence comes from:

1. **Rich context** — entity metadata, field types, existing config
2. **Constrained output** — typed schemas, not freeform text
3. **Verification** — parse and validate before applying

The framework is LLM-agnostic. Skills define what context to provide and what output to expect. The LLM adapter handles serialization, prompting, and response parsing. Different models can be swapped without changing skill definitions.

## Consequences

### Positive
- AI generates the same configuration developers write — no special runtime or interpretation layer
- End users get self-service configuration without developer involvement or deployments
- The expression DSL (ADR-0002) serves as a safe, verifiable target for AI-generated logic
- Composable skills enable complex workflows from simple building blocks
- Configuration promotion provides a path from experimental runtime config to permanent source-controlled metadata

### Negative
- Layer 3 configuration schemas must be comprehensive — every configurable aspect of every component needs a schema (see ADR-0008)
- LLM quality varies — verification catches syntax errors but not semantic mistakes (e.g., a valid but wrong filter)
- Two persistence targets (YAML + database) adds complexity to the skill executor

### Risks
- **Schema completeness**: If the configuration vocabulary is too narrow, skills can't express what users want. Mitigation: design schemas to be extensible, iterate based on real usage.
- **Context window limits**: Complex entities with many fields may exceed LLM context. Mitigation: context assembler selects relevant fields, not all fields.
- **User trust**: Users need to understand and verify what the AI configured. Mitigation: structured editor always shows the result; never apply without user confirmation.

### Dependencies
- ADR-0008 (UI Component Configuration Model): defines data patterns, presentation styles, and the ComponentConfig schema that view skills target
- ADR-0002 (Expression Language DSL): provides the target language for generated validation/default expressions
- ADR-0001 (Validation Architecture): Layer 3 validators are the persistence target for validation skills
