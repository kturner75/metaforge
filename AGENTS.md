# Repository Guidelines

## Project Structure & Module Organization
- `backend/src/metaforge/` houses the Python package (API, auth, metadata, validation, persistence).
- `backend/tests/` contains pytest-based backend tests.
- `frontend/src/` contains the React app (components, hooks, and entry points).
- `metadata/` holds YAML definitions (`metadata/entities/`, `metadata/blocks/`) and is the source of truth.
- `docs/adr/` stores architecture decision records.

## Build, Test, and Development Commands
Run commands from the relevant subdirectory.

```bash
# backend (from /backend)
pip install -e ".[dev]"        # install dev dependencies
uvicorn metaforge.api:app --reload  # run API on :8000
pytest                         # run all backend tests
ruff check src                 # lint
ruff format src                # format
```

```bash
# frontend (from /frontend)
npm install                    # install dependencies
npm run dev                    # run Vite dev server on :5173
npm run build                  # production build
npm test                       # run Vitest
npm run lint                   # lint
```

## Coding Style & Naming Conventions
- Python uses 4-space indentation; Ruff is configured with a 100-char line length.
- Backend tests follow `test_*.py` naming in `backend/tests/`.
- Frontend uses 2-space indentation (see `frontend/src/`) and single quotes in TS/TSX.
- React components are PascalCase; hooks are `useX`.
- Keep metadata filenames aligned with the `entity:` name to avoid confusion.

## Testing Guidelines
- Backend: pytest + pytest-asyncio; run `pytest` or a single test like `pytest tests/test_api_integration.py -k test_name`.
- Frontend: Vitest via `npm test`; for new tests, follow Vitest defaults (e.g., `*.test.tsx`).

## Commit & Pull Request Guidelines
- No commit history exists yet, so there is no enforced message convention.
- Use short, imperative subjects (e.g., “Add contact validator”) until a standard is adopted.
- PRs should include a concise summary, testing notes, and screenshots for UI changes.

## Configuration & Data Tips
- Metadata in `/metadata` drives both backend and UI behavior; update it alongside code changes.
- Local development uses SQLite by default, while production targets PostgreSQL.
