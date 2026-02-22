# Development Setup

Practical reference for running MetaForge locally — database config, seed data, and test credentials.

## Running the Stack

```bash
# Backend (from /backend)
pip install -e ".[dev]"
uvicorn metaforge.api:app --reload      # http://localhost:8000

# Frontend (from /frontend)
npm install
npm run dev                              # http://localhost:5173
```

---

## Database Configuration

The backend resolves the database URL in this priority order:

| Priority | Mechanism | Example |
|---|---|---|
| 1 | `DATABASE_URL` env var | `postgresql://user@localhost/metaforge` |
| 2 | `METAFORGE_DB_PATH` env var (legacy SQLite) | `/path/to/metaforge.db` |
| 3 | Default (no env vars) | `{project_root}/data/metaforge.db` |

**Source:** `backend/src/metaforge/persistence/config.py`

### PostgreSQL (recommended for dev)

PostgreSQL 17 runs via Homebrew. The dev database is `metaforge`:

```bash
# Create the database (first time only)
createdb metaforge

# Set for your shell session
export DATABASE_URL=postgresql://kevinturner@localhost/metaforge

# Or set it in your JetBrains run configuration environment variables
```

### SQLite (fallback)

No configuration needed — if `DATABASE_URL` is unset the backend creates `data/metaforge.db` at the project root automatically.

---

## Seed Scripts

All seed scripts respect `DATABASE_URL`. Run them in order:

```bash
cd backend

# 1. Auth — tenant + all four role users
DATABASE_URL=postgresql://kevinturner@localhost/metaforge \
  python -m metaforge.scripts.seed_auth

# 2. Contacts — 10 companies + 29 contacts (varied status/industry)
DATABASE_URL=postgresql://kevinturner@localhost/metaforge \
  python -m metaforge.scripts.seed_contacts

# 3. Categories — 20 categories in a 3-level hierarchy (for tree view)
DATABASE_URL=postgresql://kevinturner@localhost/metaforge \
  python -m metaforge.scripts.seed_categories
```

Add `--reset` to any script to wipe and recreate its data.

---

## Test Credentials

All users belong to the **Demo Company** tenant (`slug: demo`).

| Email | Password | Role | Notes field (ADR-0010) |
|---|---|---|---|
| `admin@example.com` | `admin123` | admin | read ✓ write ✓ |
| `manager@example.com` | `manager123` | manager | read ✓ write ✓ |
| `user@example.com` | `user123` | user | read ✓ write ✗ |
| `readonly@example.com` | `readonly123` | readonly | read ✗ write ✗ |

The `notes` field on Contact has field-level policies applied — useful for manually verifying permission enforcement across the role hierarchy.

### Quick login test

```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin123"}' \
  | python3 -m json.tool
```

---

## Seed Data Overview

### Companies (10)

| Name | Industry |
|---|---|
| Acme Corp | Technology |
| Globex Industries | Manufacturing |
| Initech Solutions | Technology |
| Umbrella Financial | Finance |
| Soylent Media | Media |
| Vandelay Import | Retail |
| Prestige Worldwide | Consulting |
| Bluth Company | Real Estate |
| Pied Piper Inc | Technology |
| Dunder Mifflin | Manufacturing |

### Contacts (29)

- **15 active**, **9 leads**, **5 inactive**
- Spread across all 10 companies + 3 standalone contacts
- All have notes, phone numbers, and email addresses

### Categories (20)

Three-level hierarchy for tree-view testing:
- **Technology** → Frontend (React, Vue, Angular), Backend (Python, Node.js, Go), DevOps (Docker, Kubernetes)
- **Business** → Marketing (Content, SEO), Sales (Enterprise, Inside), Finance
