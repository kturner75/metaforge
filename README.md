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
- Persistence: Dynamic model generation from metadata at startup (reflect/create tables programmatically).
    - Start with PostgreSQL (JSONB for complex types like address/attachment).
- Metadata store: YAML files in `/metadata/` (entities, blocks, views); optional DB table for runtime user-saved views.

### Frontend
- Framework: React
- Styling/Theming support
- UI Components designed to work hand-in-hand with the entity metadata
    - Search List, Edit Forms, Data Grids
    - User Configurable Filters, Views that leverage entity metadata

### Local Dev (IntelliJ)
- Set Project SDK to the repo `.venv` interpreter (`.venv/bin/python`)
- Run configurations are checked in under `.idea/runConfigurations`:
  - Backend API (FastAPI via `backend/run_api.py`)
  - Frontend Dev (`npm run dev`)
  - Full Stack (compound)
  - Backend Sanity Check (prints interpreter + verifies `uvicorn`)

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
displayName: Invoices
auditable: true  # auto-includes AuditTrail block

includes:
  - block: AuditTrail
  - block: AddressBlock
    prefix: billing_

fields:
  - name: id
    type: uuid
    fixed: true
    primaryKey: true
  - name: amount
    type: currency
    currencyCode: USD
    validation: { required: true, min: 0 }
  - name: dueDate
    type: date
    default: { calculated: "now() + 30 days" }
  - name: status
    type: picklist
    options: ["pending", "paid", "overdue"]
    default: "pending"
  - name: customerName
    type: string
    calculated: { expression: "related.Customer.name" }
    readOnly: true
  - name: totalWithTax
    type: number
    calculated: { expression: "amount * (1 + taxRate)" }

relations:
  - name: customer
    to: Customer
    type: belongsTo
    foreignKey: customerId

lifecycle:
  onCreate: ["setCreatedBy"]
  onUpdate: ["updateUpdatedAt", "recalculateTotals"]
```

Rich Field Types (registry):

text, name, description, email, phone, url, checkbox, picklist, multi_picklist, date, datetime, currency, percent, number, address (object), attachment (array<url>), relation

Blocks (reusable): /metadata/blocks/*.yaml

AuditTrail: createdBy/At, updatedBy/At (auto-populated via context)
AddressBlock: street, city, state (picklist), postalCode, country, latLong
ContactInfo: firstName, lastName, email, phone

## 4. Persistence & API Contract

Adapter interface: Load metadata → generate tables/models → CRUD + query.
Generic endpoint: POST /query/{entity}
Payload: { fields: [...], filter: {...}, sort: [...], groupBy: [...], aggregate: {sum: "amount"}, limit, offset }
Resolves calculated/relational fields, rich-type formatting.

CRUD: Standard REST (POST /entities/{entity}, GET /entities/{entity}/{id}, etc.)
Migrations: Alembic diff from metadata changes (preview/apply).

## 5. UI Components & Self-Service

<EntityGrid entity="Invoice" viewId?="overdue" />
Props: entity (required), viewId (saved view), fields (override), defaultSort, editable, showAggregates
Behavior: Introspects metadata → auto columns/formatters/filters/editors (from rich types), TanStack Table under hood.
User actions: Add/remove columns, set filters/groups/sorts/aggregates → save as view metadata.

<EntityForm entity="Invoice" /> for create/edit (React Hook Form + Zod from metadata)
<EntityDetail entity="Invoice" id="..." />
Dashboard configurator: Drag-drop fields, layout → save view metadata.

## 6. AI Integration Hooks

Dev-time CLI/agent: "add-entity Invoice" → prompt for fields/types/blocks → generate YAML + stubs.
Runtime chat: NL "show overdue invoices by customer" → parse → query payload → render in EntityGrid → optional save view.

## 7. Artifact Structure
Should be clean and organized for metadata (entities, validators, components, views)
