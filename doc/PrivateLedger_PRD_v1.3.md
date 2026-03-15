  
**PRODUCT REQUIREMENTS DOCUMENT**

**Private Ledger**

*Version 1.3  ·  Draft*  
March 2026

## **Document Information**

| Document Status | Draft — v1.3 |
| :---- | :---- |
| **Project Name** | Private Ledger |
| **Author** | — |
| **Last Updated** | March 2026 |
| **Target Milestone** | v1 MVP / v2 AI Expansion |
| **Primary Audience** | Solo technical developer; self-hosting household users |

# **1\.  Executive Summary**

Private Ledger is a privacy-first, locally-deployed personal finance application built for technically fluent individuals and households who refuse to surrender their financial data to third-party cloud services. Unlike SaaS alternatives such as YNAB, Monarch Money, or Mint, every byte of transaction data remains on the user's own hardware.

The application's core differentiator is an auto-generated baseline budget derived from historical transaction patterns — subscriptions, recurring utilities, and variable essentials. The v1 MVP delivers this entirely through deterministic rule-based logic and a manual merchant management layer, giving users full control over how transactions are categorised before any AI assistance is introduced. LLM integration (Ollama, cloud AI, NL queries) is explicitly deferred to v2 — the data model and API surface are designed to accommodate it cleanly when the time comes.

The v1 UI comprises six primary pages: Dashboard, Transaction Manager, Import Wizard, Subscriptions, Merchant Manager, and Reports. The Reports page provides Monarch Money-style visual analytics including a money flow diagram, category spend breakdown, monthly trend charts, and a top merchants view. The Merchant Manager gives users a clean interface for setting display names, canonical categories, and alias rules — the manual foundation that LLM categorisation will eventually augment.

The frontend is a Vite \+ React 18 SPA (TypeScript), compiled to a static asset bundle that FastAPI serves directly. This reduces the Docker Compose stack to a single application service, lowering memory overhead on home hardware and keeping all business logic in one Python runtime.

The system is packaged as a Docker Compose stack requiring a single command to run, and targets a highly technical solo developer as the primary operator, with a multi-user household as the target end-user group.

# **2\.  Goals & Success Metrics**

## **2.1  Product Goals**

* Privacy-absolute: zero financial data leaves the local network by default.

* Zero cold-start friction: import 3 months of bank CSVs and receive a usable budget baseline within 5 minutes.

* Resilient ingestion: handle overlapping CSV uploads from TD and RBC without introducing duplicate transactions.

* Merchant clarity: users can assign clean display names and categories to all merchants before any automation touches the data.

* Household-ready: multiple users can operate isolated profiles on a single deployed instance.

## **2.2  Success Metrics (v1 MVP)**

| Metric | Target | Measurement Method |
| :---- | :---- | :---- |
| **Deduplication accuracy** | 0% false positives on overlapping uploads | Automated integration test suite |
| **Baseline generation time** | \< 5 min from first CSV upload | End-to-end timing test |
| **CSV auto-detection coverage** | TD, RBC, Tangerine, CIBC formats | Fixture-based unit tests per bank format |
| **Merchant Manager coverage** | 100% of transactions assignable to a merchant record | UI smoke test post-import |
| **Multi-user isolation** | User A cannot read User B's data | Penetration test / auth unit tests |
| **Setup complexity** | Single docker compose up command | Verified in clean-VM smoke test |

# **3\.  Target Audience & Personas**

## **3.1  Primary Operator — The Developer**

A technically proficient solo developer who deploys and maintains the instance. Comfortable with Docker, Linux, and Python. Values control over the stack; contributes fixes upstream. Likely running the app on a home server or NAS device.

## **3.2  End Users — Household Members**

Non-technical members of the household who interact with the UI only. Need a clean, legible dashboard and a simple import flow. Should never need to touch Docker or environment variables. Their mental model is: 'I upload my CSV, I see my budget.'

## **3.3  Out-of-Scope Users (v1)**

* Freelancers or small business owners requiring invoice tracking or P\&L reporting.

* Users needing bank API (Open Banking / Plaid) connectivity — CSV-first only in v1.

* Users on mobile-only devices — responsive design is a v2 consideration.

# **4\.  Technical Architecture**

## **4.1  Stack Overview**

| Layer | Technology | Rationale |
| :---- | :---- | :---- |
| **Frontend** | Vite \+ React 18 (TypeScript) | SPA compiled to a static dist/ bundle. No Node.js server process. FastAPI mounts and serves the bundle directly via StaticFiles. Faster HMR in dev than Next.js; zero runtime overhead in production. |
| **Backend API** | FastAPI (Python 3.12+) | Async-first; automatic OpenAPI docs; native Python for data processing and LLM libraries. Also serves the compiled frontend static bundle, eliminating the need for a separate web container. |
| **Database** | SQLite (via SQLAlchemy) | Zero-dependency, file-based, trivially backup-able. Sufficient for household transaction volumes (\<500k rows). |
| **Local AI Runtime** | Ollama (serves Qwen2-1.5B or Phi-3 Mini) | Standard local inference daemon; model-agnostic; exposes OpenAI-compatible API endpoint. |
| **Cloud AI (opt-in)** | OpenAI / Anthropic API (user-supplied key) | Fallback for users whose hardware cannot run local inference. Opt-in per-session, never persisted. |
| **Containerisation** | Docker Compose v2 | Two-service stack (api, ai-runtime). Volume-backed persistence. Isolated networking. No Node.js container. |
| **Auth** | JWT (access) \+ refresh tokens, Argon2id hashing | Stateless API auth; cryptographically sound password storage. |
| **API Type Contract** | openapi-typescript (codegen) | FastAPI auto-generates OpenAPI spec; openapi-typescript generates TypeScript types for the frontend at build time. Type-safe API calls without a separate BFF layer. |

## **4.2  Service Topology**

The Docker Compose stack defines a single application service (api) and one named volume (privateLedger\_data). The Vite SPA is compiled into a dist/ directory and served by FastAPI via a StaticFiles mount. No Node.js process runs at any point in production. No AI runtime service is included in v1 — the architecture is intentionally designed so that an ai-runtime (Ollama) service can be added as a second service in v2 without any changes to the api service or database schema.

* api (FastAPI/Uvicorn) — port 8000:8000. Serves REST API on /api/\* and compiled Vite SPA on all other paths. The sole application service in v1.

The api service shares the privateLedger\_data volume, which persists the SQLite database file and uploaded CSV staging area. The compiled frontend bundle is baked into the api container image at build time — a container rebuild is required to deploy frontend changes.

## **4.3  Frontend Architecture**

The frontend is a Vite \+ React 18 SPA written in TypeScript. It communicates with FastAPI exclusively via the REST API — there is no server-side rendering, no API routes, and no Node.js runtime in production. This means all initial data loading happens client-side after the app shell loads.

To avoid request waterfalls on the dashboard (where a naive SPA would fire 3–4 serial fetches on mount), FastAPI exposes a dedicated GET /api/dashboard/summary endpoint that assembles all panel data server-side in a single response. This provides the same perceived performance benefit as SSR without requiring a Node.js process.

Type safety between the frontend and backend is maintained via openapi-typescript: FastAPI's auto-generated OpenAPI spec is used at build time to generate TypeScript types for all request/response shapes. The generated types are committed to the repository and regenerated as part of the CI pipeline on any API change.

JWT access tokens are stored in memory (React state / context) during the session, not in localStorage or cookies. This avoids XSS exposure from localStorage while sidestepping the HttpOnly cookie complexity that would otherwise require a server-side session layer. Refresh tokens are stored in an HttpOnly cookie set by FastAPI on the /api/auth/refresh endpoint.

# **5\.  Functional Requirements**

Requirements are tagged with a priority (Must Have, Should Have, Nice to Have) and assigned to either the v1 MVP or v2 milestone.

## **5.1  Data Ingestion & CSV Normalisation**

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **ING-01** | Multi-bank CSV parsing | Parse CSV exports from TD Bank, RBC, Tangerine, Scotiabank, and CIBC without manual column mapping. Date formats (DD/MM/YYYY, YYYY-MM-DD, MM-DD-YYYY) must all be handled. | **Must Have** | v1 |
| **ING-02** | Known-profile header detection | Match CSV headers against a library of known bank profiles. If no profile matches, fall back to the manual column-mapping UI (ING-03). LLM-assisted header inference is a v2 enhancement — the fallback must be fully functional without it. | **Must Have** | v1 |
| **ING-03** | Flexible column mapping UI | Allow the user to manually override or assign the column mapping via a dropdown per column in the Import Wizard before committing rows. | **Must Have** | v1 |
| **ING-04** | Hash-based deduplication | Generate a SHA-256 dedupe\_hash from the tuple (user\_id, date\_normalised, amount\_cents, merchant\_normalised). Reject insert and surface a skip-count if hash already exists. | **Must Have** | v1 |
| **ING-05** | Bank ID secondary deduplication | Where a CSV contains a bank-provided transaction ID column, store it as external\_id and use it as a secondary dedup check independently of the hash. | **Should Have** | v1 |
| **ING-06** | Staged import preview | Before committing, display: total rows parsed, rows to be inserted, rows skipped (dedup), rows flagged (parse errors). Require explicit user confirmation. | **Must Have** | v1 |
| **ING-07** | Merchant normalisation | Strip trailing whitespace, collapse repeated spaces, apply the Merchant Manager alias table on import (e.g., 'NETFLIX.COM' \-\> 'Netflix'). Normalised merchant stored separately from raw merchant. | **Must Have** | v1 |
| **ING-08** | CAD/USD multi-currency handling | Where a CSV contains a currency column, store the original currency and amount. All budget calculations default to CAD; USD amounts are displayed with a flag but not auto-converted. | **Should Have** | v1 |
| **ING-09** | Bulk re-categorise on rule changes | When a merchant alias or category rule changes in the Merchant Manager, provide a 'Re-categorise historical' action that replays the new rules across existing transactions without re-importing CSVs. | **Should Have** | v1 |
| **ING-10** | LLM-assisted header inference | When no known profile matches, pass the first 5 rows to a local LLM for a JSON column-mapping suggestion. Requires Ollama service (v2). Falls back to manual mapping (ING-03) when unavailable. | **Nice to Have** | v2 |

## **5.2  Transaction Categorisation**

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **CAT-01** | Rule-based auto-categorisation | Apply a priority-ordered list of regex/substring rules against normalised\_merchant to assign a system category. Rules are defined in the Merchant Manager and evaluated on every import and re-categorisation run. Default ruleset ships with the app covering \~40 common Canadian merchants. | **Must Have** | v1 |
| **CAT-02** | Manual category override | The user may override any transaction's category at any time from the Transaction Manager. Overrides are stored with category\_source \= 'manual' and are never overwritten by re-categorisation runs. | **Must Have** | v1 |
| **CAT-03** | Custom categories | Users may create, rename, merge, and delete custom categories. Deleting a category prompts the user to re-assign its transactions. | **Must Have** | v1 |
| **CAT-04** | Category spending rules | Each category may have a monthly\_limit attached. Transactions summing beyond 80% of the limit generate a soft warning; beyond 100% generate a hard alert. | **Must Have** | v1 |
| **CAT-05** | Uncategorised review queue | A dedicated view in the Transaction Manager filters to all transactions with category \= NULL. The user can bulk-assign a category or assign per row. This is the manual fallback for all unmatched merchants before LLM assistance exists. | **Must Have** | v1 |
| **CAT-06** | LLM-assisted categorisation (batch) | For transactions that match no rule, batch-send uncategorised merchant names to a local LLM for category suggestions. Results stored as category\_source \= 'llm\_suggested' until the user approves or rejects. Requires Ollama service (v2). | **Nice to Have** | v2 |

## **5.3  Recurring Detection & Budget Engine**

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **REC-01** | Fixed subscription detection | Identify merchants where amount variance \< 2% and interval is 28–35 days across a minimum of 3 occurrences. Tag as recurring\_fixed. | **Must Have** | v1 |
| **REC-02** | Variable recurring detection | Identify category-level spending patterns (e.g. Groceries, Utilities) where the category appears every month but amount varies. Tag as recurring\_variable. Store 3-month and 6-month rolling averages. | **Must Have** | v1 |
| **REC-03** | Baseline budget generation | On user request (or first login post-import), auto-propose a monthly budget per category using: fixed subscriptions at exact amount, variable categories at 6-month average (or 3-month if insufficient data). Present as editable proposal in the Budget Creator wizard. | **Must Have** | v1 |
| **REC-04** | Seasonal adjustment flag | When a utility or grocery category shows \> 20% variance between summer and winter months, flag it in the baseline proposal with a note suggesting the user set a seasonal override. | **Should Have** | v1 |
| **REC-05** | Budget burn-down calculation | For the current calendar month, compute: budgeted total vs. spent to date vs. projected month-end spend (based on transaction rate). Surface as three hero numbers on the dashboard. | **Must Have** | v1 |
| **REC-06** | Annual subscription handling | Detect transactions occurring at approximately 12-month intervals. Display on the Subscriptions page and pro-rate the monthly cost (amount / 12\) into the baseline budget. | **Should Have** | v1 |
| **REC-07** | Budget history & comparison | Retain prior month budgets as read-only snapshots. Allow month-over-month comparison of budgeted vs. actual per category in the Reports page. | **Should Have** | v2 |

## **5.4  Merchant Manager**

The Merchant Manager is the manual categorisation foundation for the entire application. Every unique normalised\_merchant value encountered across all imports is automatically surfaced here as a merchant record. Users clean up the data here — assigning display names, canonical categories, and alias rules — before any LLM assistance is available in v2. A well-curated merchant table is what makes the recurring detection engine, budget baseline, and reports accurate.

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **MCH-01** | Auto-create merchant records on import | Every unique normalised\_merchant value that does not already have a merchant record must be automatically created in the merchants table on import with status \= 'unreviewed'. | **Must Have** | v1 |
| **MCH-02** | Display name assignment | The user may assign a human-readable display\_name to any merchant record (e.g. 'AMZN MKTP CA' \-\> 'Amazon'). The display\_name is used everywhere in the UI in place of merchant\_normalised. | **Must Have** | v1 |
| **MCH-03** | Canonical category assignment | Each merchant record may be assigned a default\_category. Transactions linked to that merchant are automatically assigned this category on import (and on re-categorisation runs), unless the transaction has a manual override. | **Must Have** | v1 |
| **MCH-04** | Alias rules per merchant | The user may define one or more raw string patterns (substring or regex) that should map to this merchant record. Alias rules are evaluated at import time and during re-categorisation runs. | **Must Have** | v1 |
| **MCH-05** | Unreviewed queue | A filterable list of merchant records with status \= 'unreviewed' (i.e., seen on import but not yet manually configured). Surfaces the count on the dashboard as a prompt to action. | **Must Have** | v1 |
| **MCH-06** | Merge merchants | Allow two merchant records to be merged — all transactions linked to the source merchant are reassigned to the target, and the source record is deleted. | **Should Have** | v1 |
| **MCH-07** | Transaction count & last seen | Each merchant record displays the total transaction count and date of most recent transaction, to help the user prioritise which merchants to configure. | **Should Have** | v1 |
| **MCH-08** | Transfer flag | Each merchant may be flagged as is\_transfer \= true. Transactions from these merchants are excluded from all spending totals, reports, and budget calculations. | **Must Have** | v1 |
| **MCH-09** | LLM-suggested display names & categories | When Ollama is available (v2), suggest display\_name and default\_category for unreviewed merchants. Suggestions are shown as a draft pending user confirmation — never auto-applied. | **Nice to Have** | v2 |

## **5.5  Subscriptions**

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **SUB-01** | Subscription list page | Dedicated page listing all auto-detected recurring\_fixed and annual merchant rules. Each row shows: merchant display name, detected amount (or pro-rated monthly amount for annual), billing interval, last charged date, next expected date, and active/inactive toggle. | **Must Have** | v1 |
| **SUB-02** | Manual subscription entry | Allow users to manually add a subscription record for merchants not yet detected (e.g., new service added this month with insufficient history for auto-detection). Requires: merchant, amount, interval (monthly/annual), start date. | **Should Have** | v1 |
| **SUB-03** | Upcoming charges widget | Display on the dashboard a list of fixed subscriptions expected to charge within the next 7 days, with amounts. Sourced from detected recurring rules and manually entered subscriptions. | **Must Have** | v1 |
| **SUB-04** | Annual subscription pro-ration | Annual subscriptions display both the full annual amount and the pro-rated monthly equivalent (amount / 12). The monthly equivalent is included in the baseline budget calculation. | **Must Have** | v1 |
| **SUB-05** | Inactive toggle | Users may mark a subscription as inactive (e.g., cancelled). Inactive subscriptions are excluded from upcoming charges and budget projections but retained in history. | **Must Have** | v1 |
| **SUB-06** | Subscription spend over time | A sparkline or mini chart on each subscription row showing the last 12 months of charges — useful for spotting price creep. | **Nice to Have** | v2 |

## **5.6  Reports**

The Reports page provides visual analytics inspired by Monarch Money's reporting suite. All charts are rendered client-side using a charting library (Recharts or Chart.js). All report data is sourced from a set of dedicated FastAPI aggregation endpoints under /api/reports/\*, which perform SQL aggregations server-side and return pre-computed datasets. Reports are scoped to the authenticated user's transactions only.

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **RPT-01** | Money flow diagram (Sankey) | A Sankey flow chart showing income sources flowing into spending categories for a selected month or date range. Flow width is proportional to amount. Renders using a D3-based Sankey layout. Clicking a flow segment navigates to a filtered transaction list for that category. | **Must Have** | v1 |
| **RPT-02** | Category spend breakdown (donut chart) | A donut/pie chart showing percentage and absolute spend per category for the selected period. Clicking a segment filters the transaction list. Uncategorised transactions are shown as a distinct segment with a prompt to review. | **Must Have** | v1 |
| **RPT-03** | Monthly spending trend (bar chart) | A grouped or stacked bar chart showing total spend per month over the last 12 months, optionally broken down by category. Provides context for the budget baseline averages. | **Must Have** | v1 |
| **RPT-04** | Top merchants table | A ranked table of merchants by total spend for the selected period. Columns: rank, display name, category, transaction count, total amount. Sortable by any column. | **Must Have** | v1 |
| **RPT-05** | Income vs. expenses summary | A single-row summary showing: total income (positive transactions), total expenses (negative transactions), and net for the selected period. Transfers are excluded. | **Must Have** | v1 |
| **RPT-06** | Date range selector | All report panels share a global date range control: presets (This Month, Last Month, Last 3 Months, Last 6 Months, This Year, Custom) and a custom date picker. | **Must Have** | v1 |
| **RPT-07** | Budget vs. actual comparison | A horizontal bar chart per category showing budget limit alongside actual spend for the selected month. Bars are colour-coded: green (under 80%), amber (80–100%), red (over budget). | **Must Have** | v1 |
| **RPT-08** | Subscription cost summary | A dedicated report panel on the Reports page showing total fixed subscription cost per month, broken down by individual subscription. Includes an annual total. | **Should Have** | v1 |
| **RPT-09** | Net worth / cash flow over time | A line chart of cumulative net cash flow (income minus expenses) over time. Helps users understand savings trends. | **Nice to Have** | v2 |
| **RPT-10** | Export report data as CSV | Each report panel includes an export button that downloads the underlying aggregated dataset as a CSV. | **Should Have** | v1 |

## **5.7  AI Features (v2 — Nice to Have)**

All AI features are deferred to v2. The v1 data model (merchants table, category\_source column, ai\_audit table) is designed to support these features without schema migration when they are built. No Ollama service or LLM dependency exists in v1.

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **AI-01** | Local inference via Ollama | Add Ollama as a second Docker Compose service. The api service communicates with it over the internal network. Default model configurable via OLLAMA\_MODEL env var (default: qwen2:1.5b). | **Nice to Have** | v2 |
| **AI-02** | LLM-assisted CSV header inference | When no known bank profile matches a CSV, pass the first 5 rows to the local LLM for a JSON column-mapping suggestion. Falls back to manual mapping (ING-03) if confidence is low. | **Nice to Have** | v2 |
| **AI-03** | LLM-assisted merchant categorisation | Batch-send unreviewed merchant names to the local LLM for display\_name and category suggestions in the Merchant Manager. All suggestions require user confirmation before being applied. | **Nice to Have** | v2 |
| **AI-04** | Cloud AI opt-in | A user-level setting allows entry of a third-party API key (OpenAI or Anthropic). Key stored encrypted-at-rest via Fernet, keyed from SITE\_PEPPER. Never returned in API responses. | **Nice to Have** | v2 |
| **AI-05** | Chat with your data (NL query) | A slide-out chat panel. The backend translates free-text questions to parameterised SQL SELECT statements via a prompt-engineered LLM call. Queries are sandboxed to the authenticated user's data. No write operations via NL. | **Nice to Have** | v2 |
| **AI-06** | Prompt audit log | All LLM calls logged to ai\_audit table: timestamp, provider, model, prompt\_hash (not full prompt), response\_tokens, latency\_ms. No transaction data stored in log. | **Nice to Have** | v2 |

## **5.8  Multi-User & Access Control**

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **USR-01** | User registration (admin-invite only) | New accounts may only be created by an existing admin user. No public self-registration. The first account created during initial setup is automatically an admin. | **Must Have** | v1 |
| **USR-02** | Role model | Two roles: admin and member. Admins may: create/deactivate users, trigger re-categorisation runs, access backup endpoint. Members may: manage their own transactions, budgets, and settings only. | **Must Have** | v1 |
| **USR-03** | Data isolation | All database queries are row-level filtered by user\_id. API endpoints validate that the authenticated user owns the requested resource. Enforced in a middleware layer, not per-endpoint logic. | **Must Have** | v1 |
| **USR-04** | Instance-level merchant registry | The merchants and merchant\_aliases tables are shared across all users of an instance (one curated list benefits all household members). Individual transaction categorisations and budget limits remain strictly per-user. | **Must Have** | v1 |
| **USR-05** | Household shared view (read-only) | An opt-in view lets an admin see an aggregated, anonymised spending breakdown across all users (totals by category only — no individual transaction detail). | **Nice to Have** | v2 |
| **USR-06** | Session management | JWT access tokens expire after 15 minutes. Refresh tokens expire after 7 days and are rotated on each use. Token revocation on logout enforced via a server-side SQLite-backed blocklist. | **Must Have** | v1 |

## **5.9  Security Requirements**

| ID | Requirement | Description | Priority | Milestone |
| :---- | :---- | :---- | :---- | :---- |
| **SEC-01** | Password hashing | Passwords must be hashed with Argon2id (memory: 65536 KB, iterations: 3, parallelism: 4). A unique 32-byte random salt is generated per user. A 32-byte site-wide pepper is injected from SITE\_PEPPER and prepended before hashing. | **Must Have** | v1 |
| **SEC-02** | HTTPS \+ CSP enforcement | FastAPI must emit HSTS and Content-Security-Policy headers. CSP must restrict script-src to self to mitigate XSS token theft for the cookie-authenticated SPA. The Docker Compose file must include documentation on configuring Caddy or Traefik for TLS termination. | **Should Have** | v1 |
| **SEC-03** | No external network calls by default | The api service must have no outbound internet access by default (enforced via Docker network policy). In v2, the user must explicitly set CLOUD\_AI\_ENABLED=true to allow outbound HTTPS to AI provider endpoints. | **Must Have** | v1 |
| **SEC-04** | Rate limiting | Authentication endpoints (login, refresh) are rate-limited to 10 requests per minute per IP. Repeated failures trigger a 5-minute lockout. | **Should Have** | v1 |
| **SEC-05** | CSV path traversal prevention | Uploaded CSV files must be written to a sandboxed upload directory with a UUID filename. Original filenames must never be used as filesystem paths. | **Must Have** | v1 |
| **SEC-06** | Dependency pinning | All Python and npm dependencies must be version-pinned in requirements.txt and package-lock.json. A CI workflow must flag outdated dependencies weekly. | **Should Have** | v1 |

# **6\.  User Interface Requirements**

The v1 application comprises six primary pages accessible from a persistent left-hand navigation sidebar: Dashboard, Transactions, Import, Subscriptions, Merchant Manager, and Reports.

## **6.1  Dashboard**

* Three hero numbers: Total Budgeted (this month), Spent to Date, Projected Month-End.

* Budget burn-down: horizontal bar chart showing spent vs. limit per category, colour-coded by threshold (green / amber / red).

* Upcoming subscriptions widget: fixed charges expected in the next 7 days with amounts.

* Unreviewed merchants badge: count of merchant records with status \= 'unreviewed', with a direct link to the Merchant Manager queue.

* Recent transactions feed: last 10 transactions with display name, category badge, and amount.

* Alert banner: categories exceeding 80% or 100% of their monthly limit.

## **6.2  Transaction Manager**

* Paginated, searchable, filterable table — filters: date range, category, merchant (display name), amount range, import source, categorisation status (categorised / uncategorised).

* Uncategorised tab: one-click filter to transactions with category \= NULL. Shows count in tab badge.

* Inline category override: clicking a category badge opens a dropdown without navigating away.

* Bulk actions: select multiple rows to bulk re-categorise or bulk delete.

* Export filtered view as CSV.

## **6.3  Import Wizard (3-Step)**

* Step 1 — Upload: drag-and-drop zone accepting .csv files up to 25 MB. Multiple files may be uploaded simultaneously.

* Step 2 — Map & Preview: display auto-detected or manually assigned column mapping with per-column override dropdowns. Show first 10 parsed rows. Display dedup summary (new / skipped / errors).

* Step 3 — Confirm: commit button with progress indicator during insert. Success/error summary. Link to Merchant Manager if new unreviewed merchants were created.

## **6.4  Subscriptions Page**

* Full-page list of all detected and manually entered subscriptions. Each row: display name, category, billing interval, amount (and pro-rated monthly for annual), last charged, next expected, active toggle.

* Filter tabs: All, Monthly, Annual, Inactive.

* 'Add subscription' button for manually entering a new recurring item.

* Summary bar at the top: total monthly subscription cost (sum of monthly \+ pro-rated annual).

* Clicking a subscription row expands a detail view showing the last 12 matching transactions.

## **6.5  Merchant Manager**

* Primary view: a table of all merchant records sorted by transaction count descending. Columns: display name (editable inline), raw name, category (editable dropdown), transaction count, last seen, status badge (reviewed / unreviewed), transfer flag toggle.

* Unreviewed queue tab: filtered view of all merchants with status \= 'unreviewed'. Queue count shown in sidebar badge until cleared.

* Merchant detail side-panel: clicking a row opens a panel showing alias rules (add/remove), recent transactions, and a merge-into control.

* Search and filter: search by raw name or display name; filter by category, status, or transfer flag.

* Bulk category assign: select multiple merchant records and assign a category in one action.

* Re-categorise button: triggers a background job that replays all merchant rules across historical transactions.

## **6.6  Reports Page**

* Global date range selector at the top of the page (This Month / Last Month / Last 3 Months / Last 6 Months / This Year / Custom). All panels update on change.

* Money Flow (Sankey diagram): income sources on the left flow into spending categories on the right. Flow width proportional to amount. Rendered using D3-sankey. Clicking a flow segment navigates to a filtered transaction list.

* Category Breakdown (donut chart): percentage and absolute spend per category. Uncategorised shown as a distinct segment with a prompt. Clicking a segment links to filtered transactions.

* Monthly Trend (bar chart): total spend per month over the last 12 months, optionally stacked by category.

* Budget vs. Actual (horizontal bars): one bar per category showing budget limit vs. actual spend for the selected month. Colour-coded green / amber / red.

* Top Merchants table: ranked by total spend for the period. Columns: rank, display name, category, transaction count, total. Sortable.

* Income vs. Expenses summary row: total income, total expenses, net for the period. Transfers excluded.

* Subscription Cost panel: total fixed subscription spend for the period, broken down per subscription.

* Each panel has an export-to-CSV button for the underlying dataset.

## **6.7  Budget Creator (Wizard)**

* Step 1 — Review Subscriptions: list of auto-detected fixed subscriptions with amounts. Toggle to include/exclude each.

* Step 2 — Set Variable Limits: editable fields per category pre-filled with the 6-month average (3-month if insufficient data). Averages shown as hint text. Seasonal flag shown where detected.

* Step 3 — Confirm & Activate: summary table of all limits. 'Activate Budget' sets is\_active \= true for the current month.

# **7\.  Data Schema**

## **7.1  users**

| Column | Type | Nullable | Notes |
| :---- | :---- | :---- | :---- |
| **id** | INTEGER | NO | Primary key, auto-increment |
| **username** | TEXT | NO | Unique. Lowercase, 3–32 chars. |
| **email** | TEXT | NO | Unique. Used for future notification features. |
| **password\_hash** | TEXT | NO | Argon2id output. Never returned by API. |
| **salt** | TEXT | NO | 32-byte random hex salt, unique per user. |
| **role** | TEXT | NO | Enum: 'admin' | 'member'. Default: 'member'. |
| **cloud\_ai\_key\_enc** | TEXT | YES | Reserved for v2 AI opt-in. NULL in v1. Fernet-encrypted when set. |
| **created\_at** | DATETIME | NO | UTC timestamp of account creation. |
| **last\_login\_at** | DATETIME | YES | Updated on successful authentication. |
| **is\_active** | INTEGER | NO | Boolean (0/1). Inactive users cannot log in. |

## **7.2  merchants**

Central merchant registry. Auto-populated on import; manually curated via the Merchant Manager. This table is the primary categorisation mechanism in v1 and the hook point for LLM suggestions in v2.

| Column | Type | Nullable | Notes |
| :---- | :---- | :---- | :---- |
| **id** | INTEGER | NO | Primary key, auto-increment. |
| **user\_id** | INTEGER | NO | FK \-\> users.id. Merchant records are per-user. |
| **merchant\_normalised** | TEXT | NO | The canonical normalised key. Unique per user. Matched against transactions.merchant\_normalised. |
| **display\_name** | TEXT | YES | Human-readable name shown in UI. NULL until set by user (or LLM in v2). |
| **default\_category** | TEXT | YES | FK \-\> categories.name. Applied to transactions from this merchant on import and re-categorisation. |
| **is\_transfer** | INTEGER | NO | Boolean. Transactions from this merchant excluded from all spend totals and reports. |
| **status** | TEXT | NO | Enum: 'unreviewed' | 'reviewed'. Set to 'reviewed' once user has configured the record. |
| **transaction\_count** | INTEGER | NO | Cached count. Updated on import and re-categorisation. Used for sorting in Merchant Manager. |
| **last\_seen\_date** | DATE | YES | Date of most recent transaction from this merchant. |
| **created\_at** | DATETIME | NO | UTC timestamp of first import that created this record. |

## **7.3  merchant\_aliases**

| Column | Type | Nullable | Notes |
| :---- | :---- | :---- | :---- |
| **id** | INTEGER | NO | Primary key, auto-increment. |
| **merchant\_id** | INTEGER | NO | FK \-\> merchants.id. |
| **pattern** | TEXT | NO | Substring or regex string matched against merchant\_raw during import. |
| **match\_type** | TEXT | NO | Enum: 'substring' | 'regex'. Determines matching strategy. |
| **created\_at** | DATETIME | NO | UTC timestamp. |

## **7.4  transactions**

| Column | Type | Nullable | Notes |
| :---- | :---- | :---- | :---- |
| **id** | INTEGER | NO | Primary key, auto-increment. |
| **user\_id** | INTEGER | NO | FK \-\> users.id. Row-level security anchor. |
| **merchant\_id** | INTEGER | YES | FK \-\> merchants.id. Linked after merchant lookup on import. NULL if no match yet. |
| **date** | DATE | NO | Transaction date, normalised to YYYY-MM-DD. |
| **merchant\_raw** | TEXT | NO | Original merchant string from CSV. |
| **merchant\_normalised** | TEXT | NO | After alias substitution and whitespace collapse. |
| **amount\_cents** | INTEGER | NO | Amount in minor currency unit (cents). Negative \= debit. |
| **currency** | TEXT | NO | ISO 4217 code. Default: 'CAD'. |
| **category** | TEXT | YES | FK \-\> categories.name. NULL until categorised. |
| **category\_source** | TEXT | YES | Enum: 'merchant\_rule' | 'llm\_suggested' | 'manual'. Tracks provenance. NULL until categorised. |
| **external\_id** | TEXT | YES | Bank-provided transaction ID, if available. |
| **dedupe\_hash** | TEXT | NO | SHA-256 of (user\_id, date, amount\_cents, merchant\_normalised). Unique index. |
| **source\_file** | TEXT | NO | UUID filename of originating CSV upload. |
| **import\_batch\_id** | TEXT | NO | UUID linking transactions from the same import run. |
| **created\_at** | DATETIME | NO | UTC timestamp of database insert. |

## **7.5  recurring\_rules**

| Column | Type | Nullable | Notes |
| :---- | :---- | :---- | :---- |
| **id** | INTEGER | NO | Primary key, auto-increment. |
| **user\_id** | INTEGER | NO | FK \-\> users.id. |
| **merchant\_id** | INTEGER | YES | FK \-\> merchants.id. Links detected rule to a merchant record. |
| **detection\_type** | TEXT | NO | Enum: 'fixed\_subscription' | 'variable\_recurring' | 'annual'. |
| **expected\_amount\_cents** | INTEGER | YES | For fixed subscriptions only. NULL for variable. |
| **avg\_3m\_cents** | INTEGER | YES | 3-month rolling average in cents. Updated on import. |
| **avg\_6m\_cents** | INTEGER | YES | 6-month rolling average in cents. Updated on import. |
| **interval\_days** | INTEGER | YES | Detected recurrence interval in days. NULL for variable. |
| **is\_manual** | INTEGER | NO | Boolean. True if user-created rather than auto-detected. |
| **is\_active** | INTEGER | NO | User may deactivate a rule without deleting it. |

## **7.6  budgets**

| Column | Type | Nullable | Notes |
| :---- | :---- | :---- | :---- |
| **id** | INTEGER | NO | Primary key, auto-increment. |
| **user\_id** | INTEGER | NO | FK \-\> users.id. |
| **month** | TEXT | NO | Format YYYY-MM. The budget period. |
| **category** | TEXT | NO | FK \-\> categories.name. |
| **monthly\_limit\_cents** | INTEGER | NO | Hard limit in cents for this category and month. |
| **baseline\_source** | TEXT | NO | Enum: 'rule\_generated' | 'user\_defined' | 'copied\_prior'. Note: 'ai\_generated' reserved for v2. |
| **is\_active** | INTEGER | NO | Only one active budget per (user, month, category) enforced by unique index. |

## **7.7  ai\_audit (v2 — schema reserved in v1)**

This table is created by the v1 Alembic migration but remains empty until Ollama integration is added in v2. Reserving it now avoids a schema migration on a live dataset.

| Column | Type | Nullable | Notes |
| :---- | :---- | :---- | :---- |
| **id** | INTEGER | NO | Primary key, auto-increment. |
| **user\_id** | INTEGER | NO | FK \-\> users.id. |
| **provider** | TEXT | NO | Enum: 'local\_ollama' | 'openai' | 'anthropic'. Populated in v2. |
| **model** | TEXT | NO | Model identifier string (e.g. 'qwen2:1.5b'). Populated in v2. |
| **feature** | TEXT | NO | Enum: 'header\_inference' | 'categorisation' | 'nl\_query'. Populated in v2. |
| **prompt\_hash** | TEXT | NO | SHA-256 of the prompt. Full prompt never stored. |
| **response\_tokens** | INTEGER | YES | Token count of model response, if available. |
| **latency\_ms** | INTEGER | YES | Wall-clock latency of the inference call in milliseconds. |
| **created\_at** | DATETIME | NO | UTC timestamp. |

# **8\.  Deployment & Operations**

## **8.1  Docker Compose Services**

The v1 compose file defines a single application service (api) and one named volume (privateLedger\_data). The Vite SPA is compiled into a dist/ directory and copied into the api container image at build time — it is not a separate runtime service. The volume mounts to two paths inside the api container:

* /data/db.sqlite — SQLite database

* /data/uploads — staged CSV files pending import

The api container's Dockerfile runs vite build as part of the image build step, then copies the dist/ output to /app/dist. FastAPI mounts this directory on startup:

app.mount("/", StaticFiles(directory="dist", html=True), name="static")

All API routes are prefixed with /api/ and registered before the StaticFiles mount. React Router handles client-side routing; the html=True flag ensures that any path not matching /api/\* serves index.html, enabling deep-link navigation.

When the Ollama ai-runtime service is added in v2, it will be defined as a second service in the same compose file. The api service will gain a depends\_on: ai-runtime entry and a /data/models volume path for LLM weights. No changes to the api service definition or database schema are required.

## **8.2  Environment Variables**

| Variable | Required | Description |
| :---- | :---- | :---- |
| **SITE\_PEPPER** | **YES** | 32-byte random hex string. Seed with: openssl rand \-hex 32\. Never commit to source control. Also used in v2 to key Fernet encryption for cloud AI keys. |
| **JWT\_SECRET** | **YES** | Secret key for signing JWT tokens. Minimum 64 characters. |
| **FIRST\_ADMIN\_EMAIL** | **YES (first run)** | Email for the bootstrap admin account created on first startup. |
| **FIRST\_ADMIN\_PASSWORD** | **YES (first run)** | Temporary password for bootstrap admin. Must be changed on first login. |
| **API\_BASE\_URL** | **YES (build time)** | URL the compiled SPA uses to reach the API. Baked in via VITE\_API\_BASE\_URL at docker build time. Example: http://localhost:8000 |
| **LOG\_LEVEL** | **NO** | Python logging level. Default: INFO. |
| **OLLAMA\_BASE\_URL** | **v2 only** | URL of the Ollama service. Example: http://ai-runtime:11434. Not used in v1. |
| **OLLAMA\_MODEL** | **v2 only** | Ollama model tag. Default: qwen2:1.5b. Not used in v1. |
| **CLOUD\_AI\_ENABLED** | **v2 only** | Set to 'true' to allow outbound HTTPS to cloud AI providers. Default: false. Not used in v1. |

## **8.3  Backup & Recovery**

* The app exposes an admin-only POST /admin/backup endpoint that streams the SQLite file to the client as a timestamped .sqlite download.

* The UI surfaces an 'Export Database' button in the admin panel that calls this endpoint.

* The operator is responsible for scheduling external backups (e.g., nightly rsync of the Docker volume). Documentation must include an example cron job.

* Database migrations are managed with Alembic. The api container runs alembic upgrade head on startup before accepting traffic.

# **9\.  Open Questions & Discovery Items**

The following questions must be resolved before finalising the v1 feature set.

| \# | Question | Impact | Owner / Status |
| :---- | :---- | :---- | :---- |
| **Q-01** | Should transfers between accounts (e.g. chequing-to-savings) be auto-detected and excluded from spending totals, or surfaced to the user for manual classification via the Merchant Manager? | Incorrect inclusion would inflate spending figures and break budget baseline accuracy. | **Unresolved — Author** |
| **Q-02** | Which charting library should be used for the Reports page — Recharts (React-native, lighter) or Chart.js (more chart types, D3 for Sankey)? These may need to be combined: D3-sankey for the flow diagram, Recharts for bar/donut charts. | Affects bundle size and dev complexity for the Reports page. | **Unresolved — lean toward Recharts \+ d3-sankey** |
| **Q-03** | Should the Merchant Manager be a shared instance-level resource (one merchant table for all users) or per-user? Per-user is more private but means each household member re-curates the same merchants independently. | Significant data model and UX implication. Instance-level is more practical for households. | **Unresolved — lean toward instance-level with per-user category overrides** |
| **Q-04** | Is a mobile-responsive UI a v1 requirement? The PRD currently defers it to v2, but household members may primarily use phones to check the dashboard. | Significant frontend effort if required for v1. | **Deferred to v2 — confirm with stakeholder** |
| **Q-05** | How should joint/shared transactions be handled? (e.g., one bank card covers a shared grocery trip that both users want reflected in their budgets.) | Requires a transaction-splitting model not currently in scope. | **Out of scope v1 — revisit v2** |
| **Q-06** | Should password reset be supported in v1? Without email infrastructure, this requires admin-driven reset only. | Determines whether an SMTP dependency is needed in v1. | **Lean toward admin-reset only for v1** |
| **Q-07** | Is there a requirement to support Desjardins, National Bank, or credit union CSV formats in v1? | Affects default CSV parser fixture coverage and testing scope. | **Unresolved — confirm banks used in household** |
| **Q-08** | Should the Reports page Sankey diagram show income sources as distinct nodes, or treat all income as a single 'Income' node flowing into spending categories? | Affects the data model for income detection and how the /api/reports/flow endpoint aggregates data. | **Unresolved — single Income node is simpler for v1** |

# **10\.  Out of Scope (v1)**

* LLM / AI features of any kind — Ollama, cloud AI, NL queries, AI-assisted categorisation. All deferred to v2.

* Bank API / Open Banking connectivity (Plaid, Flinks, MX) — CSV-only in v1.

* Mobile native apps (iOS / Android). Mobile-responsive web UI also deferred to v2.

* Investment account tracking (RRSP, TFSA, brokerage).

* Foreign currency auto-conversion with live exchange rates.

* Email or push notifications.

* OCR receipt scanning.

* Shared / split transactions between household users.

* Export to accounting software (QuickBooks, Wave, FreshBooks).

* Public self-registration — invite-only in v1.

* Budget history month-over-month comparison charts — deferred to v2 Reports.

# **11\.  Phased Roadmap**

| Phase | Milestone | Key Deliverables | Est. Duration | Status |
| :---- | :---- | :---- | :---- | :---- |
| **Phase 0** | **Foundation** | Docker Compose (single api service), FastAPI skeleton, Vite \+ React SPA shell, SQLAlchemy models & Alembic migrations (all 7 tables including ai\_audit stub), Auth (JWT \+ Argon2id \+ HttpOnly refresh cookie), openapi-typescript codegen pipeline, unit test harness. | 2–3 weeks | **Planned** |
| **Phase 1** | **Core Ingestion** | CSV parser library, known bank profile fixtures (TD, RBC, Tangerine, CIBC, Scotiabank), deduplication engine, merchant normalisation, auto-create merchant records on import, Import Wizard UI (3-step). | 3–4 weeks | **Planned** |
| **Phase 2** | **Merchant Manager** | Merchants table CRUD, alias rules engine, Merchant Manager page (unreviewed queue, inline edit, detail panel, merge, bulk assign), re-categorise historical action, transfer flag, uncategorised tab in Transaction Manager. | 2–3 weeks | **Planned** |
| **Phase 3** | **Budget Engine** | Rule-based auto-categorisation, recurring detection (fixed \+ variable \+ annual), baseline budget generation, Subscriptions page, Budget Creator wizard, Dashboard burn-down and hero numbers. | 3–4 weeks | **Planned** |
| **Phase 4** | **Reports** | FastAPI /api/reports/\* aggregation endpoints, Reports page: Sankey flow diagram (d3-sankey), category donut chart, monthly trend bar chart, budget vs. actual bars, top merchants table, income vs. expenses summary, subscription cost panel, date range selector, CSV export per panel. | 3–4 weeks | **Planned** |
| **Phase 5** | **Multi-User & Security** | Admin invite flow, role enforcement, data isolation middleware, rate limiting on auth endpoints, SEC test suite, backup endpoint and Export Database UI, CSP headers. | 2 weeks | **Planned** |
| **Phase 6** | **v1 Polish & Docs** | End-to-end tests, Docker clean-VM smoke test, operator documentation, .env.example, README setup guide, openapi-typescript regeneration script. | 1–2 weeks | **Planned** |
| **v2** | **AI & Enhancements** | Ollama service \+ LLM categorisation \+ LLM header inference \+ NL query chat panel \+ cloud AI opt-in. Mobile-responsive UI. Bank API exploration. Household shared view. Transaction splitting. Budget history comparison. Next.js migration if product moves to public SaaS. | TBD | **Future** |

# **Appendix A — Supported Bank CSV Formats (v1 Target)**

| Institution | Date Format | Amount Convention | Notes |
| :---- | :---- | :---- | :---- |
| **TD Bank** | MM/DD/YYYY | Debit as positive in debit col | Separate Debit/Credit columns |
| **RBC** | MM/DD/YYYY | Single amount col, debit negative | May include CAD/USD flag |
| **Tangerine** | YYYY-MM-DD | Single amount col, debit negative | No external\_id column |
| **CIBC** | YYYY-MM-DD | Debit positive in Withdrawals col | Separate Deposits/Withdrawals cols |
| **Scotiabank** | DD MMM YYYY | Single amount col, debit negative | Date parsing requires locale handling |

# **Appendix B — Default Category Taxonomy**

The following top-level categories ship with the v1 default ruleset. Sub-categories are user-definable.

* Housing — Rent, Mortgage, Property Tax, Strata/Condo Fees

* Utilities — Hydro/Electricity, Water, Natural Gas, Internet, Phone

* Groceries — Supermarkets, Wholesale Clubs (Costco, No Frills, Loblaws, Metro)

* Dining & Takeout — Restaurants, Fast Food, Coffee Shops, Delivery Apps

* Transportation — Gas, Parking, Transit (Presto), Ride-share, Vehicle Insurance

* Subscriptions & Streaming — Fixed-cost digital services (Netflix, Spotify, iCloud, etc.)

* Insurance — Life, Home, Auto, Dental (if billed directly)

* Health & Pharmacy — Pharmacies, Dental, Optometrist, Gym

* Shopping & Retail — Clothing, Electronics, Home Goods

* Entertainment & Hobbies — Movies, Books, Sports, Concerts

* Travel — Hotels, Flights, Vacation

* Education — Tuition, Textbooks, Online Courses

* Financial — Bank Fees, Interest Charges, Investment Contributions

* Transfers — Internal transfers between accounts (excluded from spending totals)

* Uncategorised — Default bucket for unmatched transactions

*End of Document.*