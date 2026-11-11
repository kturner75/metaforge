# ADR-0016: Namespaced Extensions Map and Descriptions on Entities and Fields

## Status
Proposed

## Context

ADR-0015 makes MetaForge a library that a host application embeds. A host needs to keep its own metadata next to MetaForge's: Engram, the first host, wants interview help text and a preferred source on fields, and sections and collection rules on entities.

Today it has nowhere to put them:

- **The loader drops what it doesn't know.** `MetadataLoader` keeps a fixed set of keys. `description` is allowed by both JSON Schemas but never reaches `EntityModel` or `FieldDefinition`, and any other key is silently discarded.
- **The two schemas disagree.** `fieldDef` has `additionalProperties: true`, so a host key on a field passes validation and then vanishes in the loader. `entityFile` has `additionalProperties: false`, so a host key on an entity fails validation outright. Engram worked around this by keeping entity-level data in its own `views/` and `collection.yaml` files.
- **Nothing is reserved for hosts.** If hosts add top-level keys, MetaForge can't add a key with the same name later without breaking them.

## Decision

### 1. One `extensions` map, keyed by namespace
Entities and fields (including fields defined in blocks) accept an `extensions` map. Each key is a namespace chosen by the host, typically its own name, and each value is an object the host owns:

```yaml
entity: Employer
description: A company that sponsors a benefit plan.
extensions:
  hostapp:
    sections: [identity, contacts]
fields:
  - name: ein
    type: string
    description: Federal Employer Identification Number.
    extensions:
      hostapp:
        help: "Format: 12-3456789."
        preferredSource: document
```

MetaForge hard-codes no namespace name, so a host can pick or rename its key without a MetaForge change.

### 2. MetaForge checks the shape, never the contents
The schema (`$defs/extensionsMap`) and the loader both require namespace keys to match `^[a-z][a-z0-9_.-]*$` and each value to be an object. What is inside a namespace is opaque to MetaForge: it is loaded, deep-copied per entity and returned unchanged.

### 3. The `metaforge` namespace is reserved
It is held for MetaForge's own future or experimental keys, so the framework never collides with a host.

### 4. A malformed map fails at load time
The loader raises `ValueError` naming the entity or field when `extensions` is not a map, a namespace is invalid, or a namespace value is not an object. The point of this ticket is that metadata stops disappearing silently, so a typo should fail loudly rather than be dropped.

### 5. `description` is kept everywhere
`EntityModel.description` and `FieldDefinition.description` hold the plain-text description (empty string when absent).

### 6. Both are part of the public metadata surface
`GET /api/metadata/{entity}` and the MCP `get_entity_metadata` tool return `description` and `extensions` on the entity and on every field. `EntityModel.extension(ns)` and `FieldDefinition.extension(ns)` return one namespace's object, or `{}`.

## Alternatives Considered

- **Prefixed top-level keys (`x-hostapp-help`).** No new structure, but every host key mixes with MetaForge's own, the schemas still need loosening per key, and grouping a host's data takes string parsing.
- **Hosts register a JSON Schema per namespace.** MetaForge would validate the contents too. Worth adding once a second host exists; for now it adds an API and a registration step for one consumer. The opaque map leaves room for it later.
- **Keep host metadata in separate files (Engram's current workaround).** No MetaForge change, but the host's data drifts from the entity it describes and has to be joined by name.
- **Warn and drop a malformed map.** Matches the loader's general leniency, but repeats the silent-loss problem this ADR fixes.

## Consequences

### Positive
- A host keeps its metadata in the same YAML as the entity, and it survives the loader, the API and MCP.
- Entity-level host data is no longer blocked by the entity schema.
- MetaForge can grow new top-level keys without colliding with hosts.

### Negative
- Extensions are visible to every API and MCP client that can read entity metadata, so they must never hold secrets. Today `GET /api/metadata/{entity}` answers without a token even when auth is on, so in practice that means anyone who can reach the server. A server-only namespace, or requiring auth on the metadata endpoints, would be a later change.
- One malformed `extensions` block stops the whole metadata load, which is stricter than the loader's handling of other unknown keys.
- MetaForge cannot catch a typo inside a namespace; that stays the host's job.

### Risks
- Hosts may lean on `extensions` for data MetaForge should own (for example UI hints that belong in MF-005's `ui:` block). Reviews should move anything general into core metadata.

## Related ADRs
- [ADR-0008](0008-ui-component-configuration.md) — UI Component Configuration Model
- [ADR-0015](0015-embeddable-library.md) — MetaForge as an Embeddable Library
