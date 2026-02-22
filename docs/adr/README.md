# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for MetaForge.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-validation-architecture.md) | Three-Layer Validation Architecture | Accepted |
| [0002](0002-expression-language-dsl.md) | Expression Language DSL | Accepted |
| [0003](0003-defaulting-lifecycle.md) | Entity Save Lifecycle with Defaulting | Accepted |
| [0004](0004-warning-acknowledgment-flow.md) | Validation Warning Acknowledgment Flow | Accepted |
| [0005](0005-message-interpolation.md) | Validation Message Interpolation | Accepted |
| [0006](0006-entity-scoping.md) | Entity Scoping (Global vs Tenant) | Accepted |
| [0007](0007-agent-skills.md) | Agent Skills Architecture | Accepted |
| [0008](0008-ui-component-configuration.md) | UI Component Configuration Model | Accepted |
| [0009](0009-hook-system.md) | Entity Lifecycle Hook System | Accepted |
| [0010](0010-auth-permissions-model.md) | Declarative Auth & Permissions Model | Proposed |
| [0011](0011-navigation-screen-metadata.md) | Navigation & Screen Metadata | Accepted |
| [0012](0012-persistence-migrations.md) | Persistence & Migrations Strategy | Proposed |
| [0013](0013-entity-design-sandbox.md) | AI-Assisted Entity Design Sandbox | Proposed |

## Creating New ADRs

Use the format `NNNN-short-title.md` where `NNNN` is a zero-padded sequence number.

## When to Write an ADR

Create an ADR for decisions that impact:
- metadata schema or lifecycle
- validation semantics or error contracts
- persistence or migration behavior
- API surface or generated endpoints
- UI generation rules or field rendering semantics

### Template

```markdown
# ADR-NNNN: Title

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-XXXX

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult because of this change?
```
