# Private Ledger PRD

Source: [doc/PrivateLedger_PRD_v1.3.md](/home/robert/repos/private-ledger/doc/PrivateLedger_PRD_v1.3.md)

## Overview

Private Ledger is a privacy-first, self-hosted personal finance application for technically fluent individuals and households. The v1 MVP lets users import bank CSVs, normalize and deduplicate transactions, manage merchants and categories, generate a rule-based baseline budget, review subscriptions, and view dashboard and reporting analytics. All financial data stays on local hardware by default.

The product is intended to run as a Docker Compose deployment with a FastAPI backend serving a Vite + React SPA and persisting data in SQLite. AI-assisted categorization, natural-language querying, and any external network-dependent automation are explicitly out of scope for v1.

## Goals

- Keep all financial data local by default with no outbound network dependency in normal v1 use.
- Let a user import roughly three months of CSV history and reach a usable baseline budget in under five minutes.
- Support overlapping CSV uploads without creating duplicate transactions.
- Provide a merchant management workflow that gives users explicit control over display names, aliases, transfer flags, and categories before any future automation layer exists.
- Support multi-user household deployments with strict per-user data isolation and a single operator-friendly self-hosted setup flow.

## User Stories

Note: the split `tasks/prd.json` plan now includes a dedicated Import Wizard frontend story so the implementation order matches the human-readable PRD. Merchant Manager should still come after import preview, transaction commit, and merchant backend actions so committed data exists before merchant review begins.

### US-001: Set up and authenticate into a self-hosted instance
**Description:** As a technical household operator, I want to start the stack with Docker Compose and sign in securely so that I can administer a local-only finance app.

**Acceptance Criteria:**
- [ ] `docker compose up` starts the application stack successfully in a clean environment
- [ ] FastAPI serves the compiled SPA directly
- [ ] Users can authenticate with Argon2id-hashed passwords
- [ ] Access and refresh token flows work with logout revocation
- [ ] Typecheck passes
- [ ] Tests pass

### US-002: Import bank CSVs with auto-detection and manual mapping
**Description:** As a user, I want to upload CSVs from supported banks and correct column mappings when needed so that transaction imports are reliable without editing files manually.

**Acceptance Criteria:**
- [ ] Import Wizard accepts one or more CSV files up to 25 MB each
- [ ] Known bank profiles detect TD, RBC, Tangerine, CIBC, and Scotiabank exports
- [ ] Unsupported headers fall back to a manual column-mapping UI
- [ ] Preview shows parsed rows before commit
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Verify in browser using playwright-cli skill

### US-003: Deduplicate and normalize imported transactions
**Description:** As a user, I want overlapping uploads to skip duplicates while preserving valid transactions so that my ledger stays accurate.

**Acceptance Criteria:**
- [ ] Transactions normalize date, amount, and merchant fields before insert
- [ ] A deterministic dedupe hash prevents duplicate inserts on overlapping uploads
- [ ] Import results show counts for new, skipped, and failed rows
- [ ] Duplicate prevention produces zero false positives for fixture-backed overlapping imports
- [ ] Typecheck passes
- [ ] Tests pass

### US-004: Review and manage merchants centrally
**Description:** As a user, I want merchant records to be auto-created and editable so that transaction labeling becomes consistent over time.

**Acceptance Criteria:**
- [ ] New merchants are auto-created during import with an `unreviewed` status
- [ ] Merchant Manager lists display name, raw name, category, transaction count, last seen, and transfer flag
- [ ] Users can edit display names, categories, alias rules, and merge merchants
- [ ] Users can bulk-assign categories and trigger historical re-categorization
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Verify in browser using playwright-cli skill

### US-005: Search, filter, and update transactions
**Description:** As a user, I want a transaction manager with filters and inline edits so that I can quickly correct and audit my ledger.

**Acceptance Criteria:**
- [ ] Transaction Manager supports filters for date range, category, merchant, amount range, import source, and categorization status
- [ ] An uncategorized view shows only transactions missing a category
- [ ] Users can override transaction categories inline without leaving the table
- [ ] Bulk re-categorize and bulk delete are available for selected rows
- [ ] Filtered results can be exported as CSV
- [ ] Typecheck passes
- [ ] Verify in browser using playwright-cli skill

### US-006: Detect recurring spending and manage subscriptions
**Description:** As a user, I want recurring charges detected from history and editable in a subscriptions page so that fixed spending is visible before budgeting.

**Acceptance Criteria:**
- [ ] The system detects recurring monthly, annual, and variable subscriptions using deterministic rules
- [ ] Subscriptions page lists detected and manually entered subscriptions
- [ ] Users can activate, deactivate, and edit recurring entries
- [ ] Subscription detail views show recent matching transactions
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Verify in browser using playwright-cli skill

### US-007: Generate and activate a baseline budget
**Description:** As a user, I want a baseline budget generated from subscriptions and historical category averages so that I can begin budgeting immediately after import.

**Acceptance Criteria:**
- [ ] Budget Creator pre-fills fixed subscriptions and variable category limits from historical data
- [ ] Seasonal or limited-history cases degrade gracefully using the best available average
- [ ] Users can review, edit, and activate a monthly budget
- [ ] A first usable baseline can be generated within five minutes of initial CSV import in end-to-end testing
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Verify in browser using playwright-cli skill

### US-008: View budget health and recent activity on the dashboard
**Description:** As a user, I want a dashboard summarizing budget progress, recent transactions, and attention items so that I can understand my financial state at a glance.

**Acceptance Criteria:**
- [ ] Dashboard shows total budgeted, spent to date, and projected month-end
- [ ] Budget burn-down is visible by category with threshold-based colors
- [ ] Upcoming subscriptions, unreviewed merchants, and recent transactions are shown
- [ ] Alert banners highlight categories over warning thresholds
- [ ] Typecheck passes
- [ ] Verify in browser using playwright-cli skill

### US-009: Analyze spending through reports
**Description:** As a user, I want interactive reports for spending flow, category breakdown, trends, and top merchants so that I can understand where my money goes.

**Acceptance Criteria:**
- [ ] Reports page supports a global date range selector
- [ ] Money flow, category breakdown, monthly trend, budget-vs-actual, top merchants, and income-vs-expenses views are available
- [ ] Clicking report segments can navigate to filtered transaction views where applicable
- [ ] Each report panel supports CSV export of its underlying dataset
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Verify in browser using playwright-cli skill

### US-010: Isolate household users and enforce core security controls
**Description:** As an operator, I want multiple household users to share one instance safely so that each user’s financial data remains private.

**Acceptance Criteria:**
- [ ] User-scoped financial records are isolated at the API and persistence layers
- [ ] Instance-level merchant registry remains shared while budgets and transactions remain per-user
- [ ] Auth endpoints are rate limited and repeated failures trigger lockout behavior
- [ ] Uploaded files are stored with sandboxed UUID filenames
- [ ] User A cannot access User B's private financial data in automated tests
- [ ] Typecheck passes
- [ ] Tests pass

### US-011: Operate and maintain the system as a local product
**Description:** As a technical operator, I want a documented deployment and maintenance workflow so that I can run, back up, and update the application reliably.

**Acceptance Criteria:**
- [ ] README and `.env` documentation cover local deployment and required secrets
- [ ] Dependencies are version-pinned for backend and frontend tooling
- [ ] A clean-environment smoke test verifies first-time setup
- [ ] Backup and export paths for the local database are documented or implemented for v1 scope
- [ ] Typecheck passes
- [ ] Tests pass

## Functional Requirements

- FR-1: The system must run as a self-hosted Docker Compose deployment with FastAPI serving a compiled React SPA.
- FR-2: The system must support CSV import for TD, RBC, Tangerine, CIBC, and Scotiabank in v1.
- FR-3: The import flow must support both known-profile auto-detection and manual column mapping.
- FR-4: Imported transactions must be normalized and deduplicated using a deterministic hash strategy.
- FR-5: The system must auto-create merchant records from imported transactions and allow alias, category, display-name, merge, and transfer-rule management.
- FR-6: The transaction manager must support filtering, inline categorization changes, bulk actions, and CSV export.
- FR-7: The system must detect recurring transactions and expose them on a subscriptions page with edit controls.
- FR-8: The system must generate a rule-based baseline budget from fixed recurring expenses and historical variable spending.
- FR-9: The dashboard must surface budget state, recent activity, and actionable warnings.
- FR-10: The reports area must expose money flow, category breakdown, trends, budget-vs-actual, top merchants, and summary analytics.
- FR-11: The application must support multiple household users with strict data isolation for private records.
- FR-12: Authentication must use secure password hashing, token rotation, and revocation-backed logout.
- FR-13: The v1 system must avoid outbound internet access by default during normal operation.

## Non-Goals

- AI or LLM features, including Ollama integration, cloud AI providers, AI categorization, and natural-language querying
- Bank API or open banking integrations such as Plaid, Flinks, or MX
- Mobile-native apps or a mobile-first responsive redesign
- Investment account tracking
- Foreign exchange automation with live rates
- Email or push notifications
- OCR receipt scanning
- Shared transaction splitting across users
- Public self-registration

## Design Considerations

- Keep the primary information architecture aligned to six v1 pages: Dashboard, Transactions, Import, Subscriptions, Merchant Manager, and Reports.
- Favor clear, data-dense desktop layouts because the primary operator and users are technically fluent and v1 is desktop-first.
- Use obvious affordances for uncategorized or unreviewed financial data so cleanup work is visible.
- Preserve fast navigation between reports and transaction detail views.

## Technical Considerations

- Backend: FastAPI on Python 3.12+ with OpenAPI generation and SQLite persistence via SQLAlchemy.
- Frontend: Vite + React 18 + TypeScript SPA served as static assets by FastAPI.
- Auth: JWT access tokens, refresh tokens, Argon2id password hashing, and server-side token revocation storage.
- API typing: Generate frontend types from OpenAPI with `openapi-typescript`.
- Security: HSTS and CSP headers, no outbound network access by default, auth rate limiting, sandboxed upload storage.
- Testing: Unit tests for parser coverage, integration tests for deduplication and user isolation, smoke tests for deployment and key UI flows.

## Success Metrics

- Deduplication accuracy: zero false positives on overlapping uploads in automated integration tests.
- Baseline generation time: less than five minutes from first CSV upload to a usable budget in end-to-end testing.
- CSV coverage: supported v1 bank formats parse correctly through fixture-backed tests.
- Merchant coverage: all imported transactions can be assigned to a merchant record.
- Multi-user isolation: no cross-user data exposure in auth and authorization tests.
- Setup simplicity: clean-environment startup works with a single documented Docker Compose flow.

## Open Questions

- Is Scotiabank required for the initial v1 cut or can it trail TD, RBC, Tangerine, and CIBC if parser scope needs to shrink?
- Should admin-driven password reset be included in v1 or deferred until email infrastructure exists?
- Does v1 need any mobile-responsive guarantee beyond basic usability on smaller screens?
- Should the reports Sankey diagram model income as one aggregate node or distinct income sources in v1?
- Is backup/export considered mandatory product functionality in v1 or sufficient as operator documentation and database file handling?
