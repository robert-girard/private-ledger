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
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r backend/requirements.txt
   ```

3. Run the frontend typecheck and backend typecheck:

   ```bash
   npm run typecheck
   ```

4. Start the backend locally:

   ```bash
   uvicorn app.main:app --app-dir backend --reload
   ```

5. Build and run the full deployment container:

   ```bash
   docker compose up --build
   ```

Required environment variables:

- `APP_HOST`: host binding for local backend runs, defaults to `0.0.0.0`
- `APP_PORT`: public port exposed by Docker Compose, defaults to `8000`

The FastAPI app serves `frontend/dist` directly when those assets exist. The
container build performs the frontend compilation step automatically.

## Notes

- Keep v1 local-only by default.
- Defer AI-assisted features to a later phase.
- Extend this README during implementation instead of replacing it wholesale.
