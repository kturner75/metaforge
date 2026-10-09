# MetaForge Framework Specification – Initial Implementation Guide
(Working name: MetaForge – a metadata-driven full-stack framework for data-centric web applications)

## 1. Core Principles & Goals
- Metadata is the single source of truth: Entities, fields, blocks, views, validations, defaults, and UI hints defined in YAML/JSON.
- Designed for data-centric apps (CRMs, admin panels, reporting tools, internal dashboards).
- Monolith-first architecture for simplicity, easier deployment, and lower ops overhead.
- Highly configurable/self-service: End-users/power users customize filters, views, dashboards via UI without dev intervention.
- Clear contracts: Backend persistence & API, frontend UI components.
- Minimal app code: Framework abstracts 80-90% of CRUD/UI boilerplate; custom code only for edge cases (e.g., custom validators or renderers).
- AI-native:
    - Dev-time: Guided prompts to generate entities/screens/views.
    - Runtime: NL questions → dynamic query → render in same components → save as view.
- Acceleration target: 5x+ dev speed, especially on frontend self-service grids/forms.

## 2. Tech Stack (Initial Choices)
### Backend
- Language: Python 3.12+
- Persistence: Tables are created from metadata at startup. SQLite is the default (`data/metaforge.db`). Set `DATABASE_URL` to a `postgresql://` URL to use PostgreSQL. Storage types are text, integer, and real (PostgreSQL maps real to double precision). Address and attachment values are stored as text.
- Metadata store: YAML files in `/metadata/` (entities, blocks, views, screens). Runtime user-saved views live in the database.

### Frontend
- Framework: React
- Styling/Theming support
- UI Components designed to work hand-in-hand with the entity metadata
    - Search List, Edit Forms, Data Grids
    - User Configurable Filters, Views that leverage entity metadata

### Local Dev
Nothing in the project depends on a specific IDE. From the repo root:

```bash
# Backend (http://localhost:8000)
cd backend
pip install -e ".[dev]"
uvicorn metaforge.api:app --reload

# Frontend (http://localhost:5173), in another shell
cd frontend
npm install
npm run dev
```

Database URL, seed scripts, and test logins are in [docs/development.md](docs/development.md). Use whatever virtualenv you create; the seed commands below assume a repo-root `.venv`.

### Auth Setup (Local Dev)
- Seed a test user + tenant memberships:
  - `cd backend && ../.venv/bin/python -m metaforge.scripts.seed_auth`
- The script prints example `curl` commands + UI credentials for login.
- Default UI login (if unchanged):
  - `admin@example.com / admin123`
  - `user@example.com / user123`
- If login fails (e.g., demo data already existed), reset passwords:
  - `cd backend && ../.venv/bin/python -m metaforge.scripts.seed_auth --reset`

## 3. Metadata Schema (YAML Example)
Entities defined in `/metadata/entities/*.yaml`

```yaml
entity: Invoice
abbreviation: INV
displayName: Invoice
pluralName: Invoices

includes:
  - block: AuditTrail

fields:
  - name: id
    type: id
    primaryKey: true
  - name: amount
    type: currency
    validation:
      required: true
      min: 0
  - name: dueDate
    type: date
  - name: status
    type: picklist
    options:
      - { value: pending, label: Pending }
      - { value: paid, label: Paid }
      - { value: overdue, label: Overdue }
    default: pending
  - name: customerId
    type: relation
    relation:
      entity: Customer
      displayField: name
      onDelete: setNull

defaults:
  - field: dueDate
    expression: addDays(today(), 30)
    policy: if_null

hooks:
  beforeSave:
    - name: recalculateTotals
      on: [create, update]
```

The loader reads `includes`, `fields`, `defaults`, and `hooks`. It does not read a field-level `calculated` key or an entity-level `lifecycle` block. Computed values are `defaults` expressions (`addDays`, `today`, `concat`, and the other functions in `validation/expressions/builtins.py`). Save and delete side effects are hook declarations (ADR-0009) plus a Python function registered with `@hook`. Relations are `relation` fields, not a top-level `relations` list. Picklist `options` are `{value, label}` objects. `metadata/blocks/address.yaml` still has a `calculated` entry on `latLong`; the loader drops it. An `auditable` flag is stored on the entity model and does not pull in AuditTrail — include the block explicitly.

Rich field types (the registry in `backend/src/metaforge/core/types.py`):

id, uuid, string, name, text, description, email, phone, url, checkbox, boolean, picklist, multi_picklist, date, datetime, currency, percent, number, address, attachment, relation

Blocks (reusable): /metadata/blocks/*.yaml

AuditTrail: createdBy/At, updatedBy/At (auto-populated via context)
AddressBlock: street, city, state (picklist), postalCode, country, latLong
ContactInfo: firstName, lastName, email, phone

## 4. Persistence & API Contract

Adapter interface: Load metadata → generate tables/models → CRUD + query.
Generic endpoint: `POST /api/query/{entity}`
Payload: `{ fields, filter, sort, groupBy, aggregate, limit, offset }`
Relation fields come back with hydrated display values. Formatting follows the field-type registry.

CRUD: `POST /api/entities/{entity}`, `GET /api/entities/{entity}/{id}`, `PUT` and `DELETE` on the same path.
Migrations: Alembic diff from metadata changes (preview/apply).

## 5. UI Components & Self-Service

Screens render through the style registry in `frontend/src/components/styles/`. Query grids are `QueryGrid` (`query/grid`). Create and edit use `RecordForm` (`record/form`). A single record uses `RecordDetail` (`record/detail`). Dashboards are YAML for the `compose/dashboard` style (see `metadata/views/contacts-dashboard.yaml`). There is no `EntityDetail` component and no drag-and-drop dashboard builder.

`EntityGrid` and `EntityForm` are still in the tree. `EntityGrid` takes `entity`, plus optional `fields`, `defaultFilter`, `defaultSort`, and `onRowClick`. Both render from metadata with `FieldRenderer`. They do not use TanStack Table, React Hook Form, or Zod. Those three packages are listed in `frontend/package.json` and are not imported anywhere under `frontend/src`. Grids are HTML tables. Forms keep field state in React and check constraints from metadata.

Saved views are metadata: YAML files, plus database rows for user-saved configs.

## 6. AI Integration Hooks

Dev-time: `metaforge new entity`, plus the MCP server (`python -m metaforge.mcp`, or `metaforge mcp`) for metadata, CRUD, and the design sandbox. A proposal for packaging that server with Cursor skills and YAML rules is in [docs/design/cursor-plugin.md](docs/design/cursor-plugin.md).

Runtime natural-language chat (a question turned into a query and a saved view) is not built. The in-product agent-skills runtime in ADR-0007 is accepted and unimplemented.

## 7. Artifact Structure
Should be clean and organized for metadata (entities, validators, components, views)
