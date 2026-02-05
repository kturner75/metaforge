# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MetaForge is a metadata-driven full-stack framework for data-centric web applications (CRMs, admin panels, dashboards). Metadata in YAML is the single source of truth for entities, fields, validations, and UI behavior.

## Development Commands

### Backend (from `/backend`)
```bash
pip install -e ".[dev]"      # Install with dev dependencies
uvicorn metaforge.api:app --reload  # Run dev server on :8000
pytest                       # Run tests
pytest tests/test_foo.py -k test_name  # Run single test
ruff check src               # Lint
ruff format src              # Format
```

### Frontend (from `/frontend`)
```bash
npm install                  # Install dependencies
npm run dev                  # Run dev server on :5173
npm run build                # Production build
npm test                     # Run tests
npm run lint                 # Lint
```

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (SQLite for dev, PostgreSQL for prod)
- **Frontend**: React 18, TanStack Query, Vite, TypeScript
- **Metadata**: YAML files in `/metadata/` directory

## Architecture

### Metadata-Driven Design
- Entities defined in `/metadata/entities/*.yaml`
- Reusable blocks in `/metadata/blocks/*.yaml` (AuditTrail, AddressBlock, ContactInfo)
- Runtime user-saved views stored in database

### Rich Field Types
`text`, `name`, `description`, `email`, `phone`, `url`, `checkbox`, `picklist`, `multi_picklist`, `date`, `datetime`, `currency`, `percent`, `number`, `address`, `attachment`, `relation`

### API Pattern
- Generic query: `POST /query/{entity}` with fields, filter, sort, groupBy, aggregate
- Standard REST CRUD: `POST/GET/PUT/DELETE /entities/{entity}`

### Key React Components
- `<EntityGrid>` - Auto-generates columns/formatters/filters from metadata
- `<EntityForm>` - Create/edit with validation from metadata
- `<EntityDetail>` - Display entity details

## Design Goals
- Monolith-first for simplicity
- Framework handles 80-90% of CRUD/UI boilerplate
- End-users customize filters/views/dashboards without dev intervention
- AI-assisted entity/screen generation at dev-time
