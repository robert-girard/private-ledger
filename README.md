# Private Ledger

Private Ledger is a self-hosted, privacy-first personal finance application for local-only household budgeting and transaction analysis.

## Status

Planning stage. Initial implementation work is tracked in [tasks/prd.json](/home/robert/repos/private-ledger/tasks/prd.json).

## Key Docs

- Condensed implementation PRD: [tasks/prd-private-ledger.md](/home/robert/repos/private-ledger/tasks/prd-private-ledger.md)
- Ralph task plan: [tasks/prd.json](/home/robert/repos/private-ledger/tasks/prd.json)
- Ralph progress log: [tasks/progress.txt](/home/robert/repos/private-ledger/tasks/progress.txt)

## Planned Stack

- Backend: FastAPI
- Frontend: Vite + React + TypeScript
- Database: SQLite
- Deployment: Docker Compose

## Local Setup

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Install toolchain dependencies:

   ```bash
   npm install
   npm --prefix frontend install
   uv sync --project backend --group dev
   ```

3. Run the frontend typecheck and backend typecheck:

   ```bash
   npm run typecheck
   ```

4. Start the backend locally:

   ```bash
   uv run --project backend uvicorn app.main:app --app-dir backend --reload
   ```

5. Start the frontend dev server in a second terminal when working on the SPA:

   ```bash
   npm --prefix frontend run dev
   ```

6. Build and run the full deployment container:

   ```bash
   docker compose up --build
   ```

Required environment variables:

- `APP_HOST`: host binding for local backend runs, defaults to `0.0.0.0`
- `APP_PORT`: public port exposed by Docker Compose, defaults to `8000`
- `DATABASE_URL`: SQLite database location, defaults to `sqlite:///data/private-ledger.db`
- `PASSWORD_PEPPER`: server-side secret appended during password hashing; set a long random value outside development
- `AUTH_SECRET_KEY`: HMAC secret used for access and refresh token signing
- `ACCESS_TOKEN_TTL_MINUTES`: access token lifetime in minutes, defaults to `15`
- `REFRESH_TOKEN_TTL_DAYS`: refresh token lifetime in days, defaults to `14`

The FastAPI app serves `frontend/dist` directly when those assets exist. The
container build performs the frontend compilation step automatically.

## Developer Running Notes

- Local backend-only development: run `uvicorn app.main:app --app-dir backend --reload` and use `http://127.0.0.1:8000/api/health` for a quick smoke check.
- Local backend-only development: run `uv run --project backend uvicorn app.main:app --app-dir backend --reload` and use `http://127.0.0.1:8000/api/health` for a quick smoke check.
- Python environment management: use `uv sync --project backend --group dev` to install or refresh backend dependencies and dev tools.
- Backend checks: run `uv run --project backend pyright app` and `uv run --project backend pytest` from the repo root or use the root `npm run typecheck` and `npm test` wrappers.
- First admin bootstrap: run `uv run --project backend python -m app.bootstrap_admin --email admin@example.com --display-name "Household Admin"` and provide the password when prompted.
- Local frontend development: run `npm --prefix frontend run dev` and use the Vite server for UI iteration; the current default address is `http://127.0.0.1:5173`.
- Backend-served SPA verification: after frontend changes, rebuild assets with `npm --prefix frontend run build` so FastAPI serves the latest `frontend/dist` output.
- Full-stack container verification: use `docker compose up --build` to rebuild the SPA and package it into the FastAPI container.
- Environment setup: `docker compose` reads `.env` directly, so keep `.env.example` and the local `.env` in sync when new required variables are introduced.

## Notes

- Keep v1 local-only by default.
- Defer AI-assisted features to a later phase.
- Extend this README during implementation instead of replacing it wholesale.
