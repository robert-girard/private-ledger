# AGENTS.md

This file defines the root-level guidance for agents working in this repository. Add concise, reusable notes here as implementation progresses.

## Project State

- The repository is in planning and scaffolding stage.
- The current implementation plan lives in [tasks/prd.json](/home/robert/repos/private-ledger/tasks/prd.json).
- The current human-readable implementation PRD lives in [tasks/prd-private-ledger.md](/home/robert/repos/private-ledger/tasks/prd-private-ledger.md).

## Working Rules

- Keep changes tightly scoped to the current story.
- Prefer simple, local-first architecture decisions that match the v1 PRD.
- Do not introduce AI, cloud sync, or external network dependencies into v1 unless the task explicitly requires it.
- Update this file only with reusable conventions or non-obvious project rules.
- Put story-specific notes in [tasks/progress.txt](/home/robert/repos/private-ledger/tasks/progress.txt), not here.

## Expected Conventions

- Add stack-specific instructions once backend, frontend, and tooling are created.
- Add testing and verification commands once they exist.
- Add directory-level `AGENTS.md` files later if a subdirectory develops its own patterns.

## Codebase Patterns

- FastAPI is responsible for serving the compiled SPA from `frontend/dist`; keep frontend build output and backend static asset paths aligned when changing deployment wiring.
- The Vite dev server proxies `/api` to `http://127.0.0.1:8000`; local frontend work can talk to the backend without hardcoding full API origins.
- Frontend CSV export actions still need bearer auth, so SPA export buttons should fetch the file with the access token and trigger the download client-side instead of relying on unauthenticated plain links.
- Python dependency management uses `uv` with `backend/pyproject.toml` and `backend/uv.lock`; prefer `uv run --project backend ...` and `uv sync --project backend --group dev` over ad hoc virtualenv commands.
- SQLite schema changes should ship as ordered SQL files in `backend/migrations`, and the backend startup path applies them through `app.db.migrations.initialize_database`.
- Initial operator bootstrap uses `python -m app.bootstrap_admin`; password hashing depends on `PASSWORD_PEPPER`, so auth-related work must preserve that env var in local and container runs.
- Auth endpoints live under `app.api.auth`; refresh-token rotation works by writing old token JTIs into `refresh_token_blocklist`, so refresh and logout changes must keep the JWT service and blocklist table behavior aligned.
- User-scoped APIs should resolve the current user through `app.dependencies.auth.get_current_user` and filter private models by `user_id`; merchant and merchant alias records remain instance-scoped and should not be user-filtered.
- CSV parser profiles live under `app.importing`; unknown headers should return a manual-mapping requirement object instead of raising or silently guessing.
- Import preview uploads are staged under `IMPORT_STORAGE_DIR/<user-id>/...` and recorded as `imports` rows with temp `stored_path` values, so later import-commit work should reuse that staged file instead of re-uploading.
- Import commits should reuse the staged CSV on the `imports` row, normalize merchant names before dedupe, and build transaction hashes from `user_id`, `posted_on`, `amount`, and normalized merchant text.
- Merchant registry actions should keep merchant records instance-scoped, but any historical recategorization or transaction reassignment must still be filtered to the authenticated user’s records.
- Merchant detail UIs can render recent transaction context from `/api/transactions?merchant_id=...` and filter the global `/api/merchant-aliases` response client-side by `merchant_id`, so the current backend contract does not need a merchant-specific detail endpoint for basic review panels.
- Recurring subscription detection now lives in `app.services.subscriptions`; detection should stay deterministic by grouping negative transactions per user on merchant or normalized description and upserting through `/api/subscriptions/detect` rather than ad hoc one-off queries.
- Subscription detail views should show charge matches only, so recent-match queries need the same `user_id` filter plus `Transaction.amount < 0` to avoid income rows polluting recurring-spend history.
- Subscription UI can stay on the current lightweight shell by using `/api/subscriptions` for the table, `/api/subscriptions/{id}` for recent matches, and `/api/subscriptions/detect` as an explicit user-triggered refresh instead of trying to auto-detect on every page load.
- Budget generation belongs in `app.services.budgets`; generate month recommendations into persisted inactive `budgets` rows first, then flip activation separately so the UI can edit the same stored rows before going live.
- The Budget Creator UI is a three-step shell flow over the budget endpoints: fixed subscription review, variable category review, then activation summary; keep it on the shared SPA shell until routing becomes necessary.
- Dashboard aggregation now lives in `app.services.dashboard`; summary and burn-down calculations should refresh active budget `spent_amount` first and exclude transfer merchants from spend math before projecting or flagging categories.
- Transaction query work should extend the main `/api/transactions` endpoint with filters and reuse the same filter set for `/api/transactions/export`, so the UI can export exactly the rows it is reviewing.
