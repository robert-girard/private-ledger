import { FormEvent, useEffect, useMemo, useState } from "react";

type AppView = "dashboard" | "import" | "transactions" | "merchants" | "subscriptions" | "budget";

type UserSummary = {
  email: string;
  display_name: string;
};

type ManualMapping = {
  date: string;
  description: string;
  amount?: string;
  debit?: string;
  credit?: string;
};

type PreviewRow = {
  posted_on: string;
  description: string;
  amount: string;
};

type PreviewResponse = {
  import_id: string;
  source_filename: string;
  stored_path: string;
  status: "parsed" | "manual_mapping_required";
  profile_name: string | null;
  headers: string[];
  row_count: number;
  unresolved_columns: string[];
  preview_rows: PreviewRow[];
};

type TransactionRow = {
  id: string;
  posted_on: string;
  description: string;
  amount: string;
  category: string | null;
  merchant_name: string | null;
  import_source: string | null;
};

type MerchantRow = {
  id: string;
  raw_name: string;
  display_name: string;
  category: string | null;
  status: "reviewed" | "unreviewed";
  is_transfer: boolean;
  transaction_count: number;
  last_seen: string | null;
};

type MerchantAliasRow = {
  id: string;
  merchant_id: string;
  alias: string;
  normalized_alias: string;
};

type SubscriptionRow = {
  id: string;
  user_id: string;
  merchant_id: string | null;
  display_name: string;
  category: string | null;
  interval: "monthly" | "annual" | "variable";
  amount: string;
  is_active: boolean;
  last_charged_on: string | null;
  next_expected_on: string | null;
  recent_match_transaction_id: string | null;
};

type SubscriptionDetail = SubscriptionRow & {
  recent_matches: Array<{
    transaction_id: string;
    posted_on: string;
    description: string;
    amount: string;
    category: string | null;
  }>;
};

type BudgetRecommendation = {
  id: string;
  user_id: string;
  month_start: string;
  category: string;
  planned_amount: string;
  spent_amount: string;
  is_active: boolean;
  source_type: "subscription" | "variable";
  subscription_names: string[];
  months_used: number;
};

type DashboardSummary = {
  month_start: string | null;
  total_budgeted: string;
  spent_to_date: string;
  projected_month_end: string;
};

type DashboardBurnDownItem = {
  category: string;
  planned_amount: string;
  spent_amount: string;
  remaining_amount: string;
  status: "safe" | "warning" | "over";
};

type DashboardAttention = {
  upcoming_subscriptions: Array<{
    id: string;
    display_name: string;
    category: string | null;
    amount: string;
    interval: string;
    next_expected_on: string | null;
  }>;
  recent_transactions: Array<{
    id: string;
    posted_on: string;
    description: string;
    amount: string;
    category: string | null;
    merchant_name: string | null;
  }>;
  unreviewed_merchant_count: number;
};

type ApiError = {
  detail?: string | { message?: string; errors?: string[] };
};

const views: Array<{ id: AppView; title: string; summary: string }> = [
  {
    id: "dashboard",
    title: "Dashboard",
    summary: "Track budget health, alerts, upcoming charges, and recent cleanup work at a glance.",
  },
  {
    id: "import",
    title: "Import Wizard",
    summary: "Upload CSVs, inspect detected bank profiles, fix unsupported columns, and preview before commit.",
  },
  {
    id: "transactions",
    title: "Transaction Manager",
    summary: "Filter, repair, bulk-edit, and export the current ledger view.",
  },
  {
    id: "merchants",
    title: "Merchant Manager",
    summary: "Review merchant records, repair aliases, and merge duplicate registry entries.",
  },
  {
    id: "subscriptions",
    title: "Subscriptions",
    summary: "Detect recurring charges, edit recurring entries, and inspect matched transactions.",
  },
  {
    id: "budget",
    title: "Budget Creator",
    summary: "Generate a monthly budget, refine category limits, and activate the reviewed month.",
  },
];

function formatCurrency(value: string | number): string {
  const amount = typeof value === "number" ? value : Number(value);
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatInterval(interval: string): string {
  return interval.charAt(0).toUpperCase() + interval.slice(1);
}

function DashboardPage({ token, onNavigate }: { token: string; onNavigate: (view: AppView) => void }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [burnDown, setBurnDown] = useState<DashboardBurnDownItem[]>([]);
  const [attention, setAttention] = useState<DashboardAttention | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const [summaryPayload, burnDownPayload, attentionPayload] = await Promise.all([
        apiRequest<DashboardSummary>("/api/dashboard/summary", {}, token),
        apiRequest<DashboardBurnDownItem[]>("/api/dashboard/burn-down", {}, token),
        apiRequest<DashboardAttention>("/api/dashboard/attention", {}, token),
      ]);
      setSummary(summaryPayload);
      setBurnDown(burnDownPayload);
      setAttention(attentionPayload);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const alertItems = burnDown.filter((item) => item.status !== "safe");
  const highestSpend = Math.max(...burnDown.map((item) => Number(item.spent_amount)), 0);
  const monthLabel = summary?.month_start
    ? new Date(`${summary.month_start}T00:00:00`).toLocaleDateString("en-CA", {
        month: "long",
        year: "numeric",
      })
    : "No active budget month";

  return (
    <section className="workspace-card">
      <div className="section-heading">
        <p className="eyebrow">Dashboard</p>
        <h2>Budget Health Overview</h2>
        <p>Review current-month budget posture, spot categories near their limits, and jump to the workflows that need attention next.</p>
      </div>

      <div className="actions-row dashboard-header-actions">
        <button className="primary-button" type="button" onClick={() => void loadDashboard()} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh dashboard"}
        </button>
        <button className="ghost-button" type="button" onClick={() => onNavigate("budget")}>
          Open Budget Creator
        </button>
      </div>

      {error ? <p className="notice error">{error}</p> : null}

      {alertItems.length ? (
        <div className="dashboard-alert-banner">
          <strong>Threshold alerts</strong>
          <p>
            {alertItems.map((item) => `${item.category} is ${item.status === "over" ? "over budget" : "near its limit"}`).join(" • ")}
          </p>
        </div>
      ) : null}

      <div className="dashboard-metric-grid">
        <article className="metric-card">
          <span className="label">Budget month</span>
          <strong>{monthLabel}</strong>
          <p>{summary?.month_start ? "Active budget rows are already reflected in this month." : "Generate and activate a monthly budget to unlock the dashboard."}</p>
        </article>
        <article className="metric-card">
          <span className="label">Total budgeted</span>
          <strong>{formatCurrency(summary?.total_budgeted ?? 0)}</strong>
          <p>Combined planned spend across the active monthly budget.</p>
        </article>
        <article className="metric-card">
          <span className="label">Spent to date</span>
          <strong>{formatCurrency(summary?.spent_to_date ?? 0)}</strong>
          <p>Transfer merchants stay out of this figure.</p>
        </article>
        <article className="metric-card">
          <span className="label">Projected month-end</span>
          <strong>{formatCurrency(summary?.projected_month_end ?? 0)}</strong>
          <p>Projection is based on current-month spend pace through the latest charge date.</p>
        </article>
      </div>

      <div className="split-layout dashboard-layout">
        <article className="preview-table-card">
          <div className="table-header">
            <div>
              <h3>Category burn-down</h3>
              <p className="muted-copy">Threshold coloring highlights categories that need intervention before month end.</p>
            </div>
            <span>{burnDown.length} categories</span>
          </div>

          {burnDown.length ? (
            <div className="burn-down-list">
              {burnDown.map((item) => {
                const spent = Number(item.spent_amount);
                const planned = Number(item.planned_amount);
                const ratio = planned > 0 ? Math.min(spent / planned, 1.25) : 0;
                const width = `${Math.max(8, ratio * 100)}%`;
                const compareWidth = `${Math.max(10, highestSpend > 0 ? (spent / highestSpend) * 100 : 10)}%`;

                return (
                  <div key={item.category} className={`burn-down-row burn-${item.status}`}>
                    <div className="table-header burn-row-heading">
                      <div>
                        <strong>{item.category}</strong>
                        <p className="muted-copy">
                          {formatCurrency(item.spent_amount)} spent of {formatCurrency(item.planned_amount)}
                        </p>
                      </div>
                      <span className={`status-pill ${item.status === "safe" ? "reviewed" : ""}`}>{item.status}</span>
                    </div>
                    <div className="burn-bar-track">
                      <div className="burn-bar-compare" style={{ width: compareWidth }} />
                      <div className="burn-bar-fill" style={{ width }} />
                    </div>
                    <div className="burn-stats">
                      <span>Remaining {formatCurrency(item.remaining_amount)}</span>
                      <span>{Math.round(ratio * 100)}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">
              <p>No active budget data is available yet. Generate a monthly budget first, then return here for burn-down tracking.</p>
            </div>
          )}
        </article>

        <aside className="preview-metadata detail-panel dashboard-side-panel">
          <div className="detail-section dashboard-widget">
            <div className="table-header">
              <h4>Upcoming subscriptions</h4>
              <button className="ghost-button" type="button" onClick={() => onNavigate("subscriptions")}>
                Open
              </button>
            </div>
            {attention?.upcoming_subscriptions.length ? (
              <div className="dashboard-list">
                {attention.upcoming_subscriptions.map((item) => (
                  <div key={item.id} className="dashboard-list-row">
                    <div>
                      <strong>{item.display_name}</strong>
                      <p className="muted-copy">{item.category ?? "Unassigned"} • {formatInterval(item.interval)}</p>
                    </div>
                    <div className="dashboard-list-meta">
                      <span>{formatCurrency(item.amount)}</span>
                      <span>{item.next_expected_on ?? "TBD"}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted-copy">No active upcoming subscriptions are scheduled.</p>
            )}
          </div>

          <div className="detail-section dashboard-widget">
            <div className="table-header">
              <h4>Recent transactions</h4>
              <button className="ghost-button" type="button" onClick={() => onNavigate("transactions")}>
                Review
              </button>
            </div>
            {attention?.recent_transactions.length ? (
              <div className="dashboard-list">
                {attention.recent_transactions.map((item) => (
                  <div key={item.id} className="dashboard-list-row">
                    <div>
                      <strong>{item.description}</strong>
                      <p className="muted-copy">{item.merchant_name ?? "Unknown merchant"} • {item.category ?? "Uncategorized"}</p>
                    </div>
                    <div className="dashboard-list-meta">
                      <span>{formatCurrency(item.amount)}</span>
                      <span>{item.posted_on}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted-copy">No recent transactions are available yet.</p>
            )}
          </div>

          <div className="detail-section dashboard-widget">
            <div className="table-header">
              <h4>Unreviewed merchants</h4>
              <button className="ghost-button" type="button" onClick={() => onNavigate("merchants")}>
                Triage
              </button>
            </div>
            <div className="dashboard-count-card">
              <strong>{attention?.unreviewed_merchant_count ?? 0}</strong>
              <p className="muted-copy">Shared merchant records still marked unreviewed across the instance.</p>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

function errorMessage(error: unknown): string {
  if (typeof error === "string") {
    return error;
  }

  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as ApiError).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (detail?.errors?.length) {
      return `${detail.message ?? "Request failed."} ${detail.errors.join(" ")}`;
    }
    if (detail?.message) {
      return detail.message;
    }
  }

  return "Request failed.";
}

async function apiRequest<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(errorMessage(payload));
  }
  return (await response.json()) as T;
}

function ImportWizard({
  token,
}: {
  token: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [mapping, setMapping] = useState<ManualMapping>({
    date: "",
    description: "",
  });
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");

  async function submitPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a CSV file first.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");
    setPreview(null);

    try {
      const body = new FormData();
      body.append("file", file);

      if (mapping.date && mapping.description && (mapping.amount || mapping.debit || mapping.credit)) {
        body.append("column_mapping", JSON.stringify(mapping));
      }

      const response = await apiRequest<PreviewResponse>(
        "/api/imports/preview",
        {
          method: "POST",
          body,
        },
        token,
      );

      setPreview(response);
      setMessage(
        response.status === "parsed"
          ? `Detected ${response.profile_name ?? "manual"} format with ${response.row_count} preview row${response.row_count === 1 ? "" : "s"}.`
          : "Unsupported headers detected. Map the required columns and preview again.",
      );

      if (response.status === "manual_mapping_required") {
        setMapping((current) => ({
          ...current,
          date: current.date || response.headers[0] || "",
          description: current.description || response.headers[1] || "",
          debit: current.debit || response.headers[2] || "",
          credit: current.credit || response.headers[3] || "",
        }));
      }
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setLoading(false);
    }
  }

  async function commitImport() {
    if (!preview) {
      return;
    }

    setCommitting(true);
    setError("");
    setMessage("");

    try {
      const payload =
        preview.status === "manual_mapping_required"
          ? { column_mapping: mapping }
          : {};
      const response = await apiRequest<{
        inserted_count: number;
        skipped_count: number;
      }>(
        `/api/imports/${preview.import_id}/commit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        token,
      );
      setMessage(
        `Commit complete. Inserted ${response.inserted_count} row${response.inserted_count === 1 ? "" : "s"} and skipped ${response.skipped_count}.`,
      );
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setCommitting(false);
    }
  }

  const headerOptions = preview?.headers ?? [];

  return (
    <section className="workspace-card">
      <div className="section-heading">
        <p className="eyebrow">Import</p>
        <h2>Import Wizard</h2>
        <p>
          Upload a bank CSV, inspect the detected parser profile, and correct unsupported columns before anything is committed.
        </p>
      </div>

      <form className="import-form" onSubmit={submitPreview}>
        <label className="field">
          <span>CSV file</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>

        <div className="actions-row">
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "Previewing..." : "Preview Import"}
          </button>
        </div>

        {preview?.status === "manual_mapping_required" ? (
          <div className="mapping-panel">
            <h3>Manual column mapping</h3>
            <p>Choose which headers should supply the required fields.</p>
            <div className="mapping-grid">
              <label className="field">
                <span>Date column</span>
                <select
                  value={mapping.date}
                  onChange={(event) => setMapping((current) => ({ ...current, date: event.target.value }))}
                >
                  <option value="">Select header</option>
                  {headerOptions.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Description column</span>
                <select
                  value={mapping.description}
                  onChange={(event) =>
                    setMapping((current) => ({ ...current, description: event.target.value }))
                  }
                >
                  <option value="">Select header</option>
                  {headerOptions.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Amount column</span>
                <select
                  value={mapping.amount ?? ""}
                  onChange={(event) =>
                    setMapping((current) => ({
                      ...current,
                      amount: event.target.value || undefined,
                    }))
                  }
                >
                  <option value="">Use debit and credit instead</option>
                  {headerOptions.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Debit column</span>
                <select
                  value={mapping.debit ?? ""}
                  onChange={(event) =>
                    setMapping((current) => ({
                      ...current,
                      debit: event.target.value || undefined,
                    }))
                  }
                >
                  <option value="">Optional</option>
                  {headerOptions.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Credit column</span>
                <select
                  value={mapping.credit ?? ""}
                  onChange={(event) =>
                    setMapping((current) => ({
                      ...current,
                      credit: event.target.value || undefined,
                    }))
                  }
                >
                  <option value="">Optional</option>
                  {headerOptions.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        ) : null}
      </form>

      {message ? <p className="notice success">{message}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      {preview ? (
        <div className="preview-layout">
          <article className="preview-metadata">
            <h3>Detected format</h3>
            <dl>
              <div>
                <dt>Filename</dt>
                <dd>{preview.source_filename}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{preview.status}</dd>
              </div>
              <div>
                <dt>Profile</dt>
                <dd>{preview.profile_name ?? "Manual mapping required"}</dd>
              </div>
              <div>
                <dt>Headers</dt>
                <dd>{preview.headers.join(", ")}</dd>
              </div>
            </dl>

            {preview.status === "parsed" ? (
              <button className="secondary-button" type="button" onClick={commitImport} disabled={committing}>
                {committing ? "Committing..." : "Commit Import"}
              </button>
            ) : null}
          </article>

          <article className="preview-table-card">
            <div className="table-header">
              <h3>Preview rows</h3>
              <span>{preview.row_count} rows</span>
            </div>

            {preview.preview_rows.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Description</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.preview_rows.map((row) => (
                    <tr key={`${row.posted_on}-${row.description}-${row.amount}`}>
                      <td>{row.posted_on}</td>
                      <td>{row.description}</td>
                      <td>{row.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">
                <p>Preview rows will appear here after the backend can parse the file.</p>
              </div>
            )}
          </article>
        </div>
      ) : null}
    </section>
  );
}

function TransactionManager({ token }: { token: string }) {
  const [transactions, setTransactions] = useState<TransactionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [inlineCategory, setInlineCategory] = useState<Record<string, string>>({});
  const [bulkCategory, setBulkCategory] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 10;

  async function loadTransactions() {
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (categoryFilter) {
      params.set("category", categoryFilter);
    }
    if (uncategorizedOnly) {
      params.set("uncategorized_only", "true");
    }

    try {
      const response = await apiRequest<TransactionRow[]>(
        `/api/transactions${params.toString() ? `?${params.toString()}` : ""}`,
        {},
        token,
      );
      setTransactions(response);
      setPage(1);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTransactions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, uncategorizedOnly]);

  async function updateCategory(transactionId: string) {
    try {
      await apiRequest(
        `/api/transactions/${transactionId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: inlineCategory[transactionId] ?? "" }),
        },
        token,
      );
      setMessage("Transaction category updated.");
      await loadTransactions();
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  async function applyBulkCategory() {
    if (!selectedIds.length) {
      setError("Select at least one transaction.");
      return;
    }
    try {
      await apiRequest(
        "/api/transactions/bulk-category",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transaction_ids: selectedIds, category: bulkCategory }),
        },
        token,
      );
      setMessage(`Updated ${selectedIds.length} transaction categories.`);
      setSelectedIds([]);
      await loadTransactions();
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  async function bulkDelete() {
    if (!selectedIds.length) {
      setError("Select at least one transaction.");
      return;
    }
    try {
      await apiRequest(
        "/api/transactions/bulk-delete",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transaction_ids: selectedIds }),
        },
        token,
      );
      setMessage(`Deleted ${selectedIds.length} transaction rows.`);
      setSelectedIds([]);
      await loadTransactions();
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  async function exportTransactions() {
    setError("");
    try {
      const params = new URLSearchParams();
      if (categoryFilter) {
        params.set("category", categoryFilter);
      }
      if (uncategorizedOnly) {
        params.set("uncategorized_only", "true");
      }

      const response = await fetch(
        `/api/transactions/export${params.toString() ? `?${params.toString()}` : ""}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(errorMessage(payload));
      }

      const content = await response.text();
      const blob = new Blob([content], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "transactions.csv";
      link.click();
      window.URL.revokeObjectURL(url);
      setMessage("Exported the current filtered transaction view.");
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  const uncategorizedCount = transactions.filter((transaction) => !transaction.category).length;
  const totalPages = Math.max(1, Math.ceil(transactions.length / pageSize));
  const pagedTransactions = transactions.slice((page - 1) * pageSize, page * pageSize);
  return (
    <section className="workspace-card">
      <div className="section-heading">
        <p className="eyebrow">Transactions</p>
        <h2>Transaction Manager</h2>
        <p>Filter and repair transactions, apply bulk actions, and export the exact ledger slice you are reviewing.</p>
      </div>

      <div className="filter-grid">
        <label className="field">
          <span>Category filter</span>
          <input value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} placeholder="Dining" />
        </label>
        <label className="toggle">
          <input
            checked={uncategorizedOnly}
            onChange={(event) => setUncategorizedOnly(event.target.checked)}
            type="checkbox"
          />
          <span>Uncategorized only ({uncategorizedCount})</span>
        </label>
        <div className="actions-row">
          <button className="primary-button" type="button" onClick={() => void loadTransactions()} disabled={loading}>
            {loading ? "Refreshing..." : "Apply Filters"}
          </button>
          <button className="secondary-link" type="button" onClick={() => void exportTransactions()}>
            Export CSV
          </button>
        </div>
      </div>

      <div className="bulk-toolbar">
        <label className="field">
          <span>Bulk category</span>
          <input value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)} placeholder="Reviewed" />
        </label>
        <button className="secondary-button" type="button" onClick={applyBulkCategory}>
          Apply to selected
        </button>
        <button className="ghost-button" type="button" onClick={bulkDelete}>
          Delete selected
        </button>
      </div>

      {message ? <p className="notice success">{message}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      <div className="preview-table-card transaction-table-card">
        <div className="table-header">
          <h3>Ledger rows</h3>
          <span>
            Page {page} of {totalPages}
          </span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Select</th>
              <th>Date</th>
              <th>Description</th>
              <th>Merchant</th>
              <th>Amount</th>
              <th>Category</th>
              <th>Import</th>
            </tr>
          </thead>
          <tbody>
            {pagedTransactions.map((transaction) => (
              <tr key={transaction.id}>
                <td>
                  <input
                    checked={selectedIds.includes(transaction.id)}
                    onChange={(event) =>
                      setSelectedIds((current) =>
                        event.target.checked
                          ? [...current, transaction.id]
                          : current.filter((id) => id !== transaction.id),
                      )
                    }
                    type="checkbox"
                  />
                </td>
                <td>{transaction.posted_on}</td>
                <td>{transaction.description}</td>
                <td>{transaction.merchant_name ?? "Unknown"}</td>
                <td>{transaction.amount}</td>
                <td>
                  <div className="inline-edit">
                    <input
                      value={inlineCategory[transaction.id] ?? transaction.category ?? ""}
                      onChange={(event) =>
                        setInlineCategory((current) => ({ ...current, [transaction.id]: event.target.value }))
                      }
                    />
                    <button className="ghost-button" type="button" onClick={() => void updateCategory(transaction.id)}>
                      Save
                    </button>
                  </div>
                </td>
                <td>{transaction.import_source ?? "Manual"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="pagination-row">
          <button className="ghost-button" type="button" onClick={() => setPage((current) => Math.max(1, current - 1))}>
            Previous
          </button>
          <button
            className="ghost-button"
            type="button"
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}

function MerchantManager({ token }: { token: string }) {
  const [merchants, setMerchants] = useState<MerchantRow[]>([]);
  const [aliases, setAliases] = useState<MerchantAliasRow[]>([]);
  const [recentTransactions, setRecentTransactions] = useState<TransactionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "reviewed" | "unreviewed">("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [transferFilter, setTransferFilter] = useState<"all" | "transfer" | "non-transfer">("all");
  const [selectedMerchantId, setSelectedMerchantId] = useState<string>("");
  const [draftDisplayNames, setDraftDisplayNames] = useState<Record<string, string>>({});
  const [draftCategories, setDraftCategories] = useState<Record<string, string>>({});
  const [newAlias, setNewAlias] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");

  async function loadMerchants() {
    setLoading(true);
    setError("");
    try {
      const [merchantRows, aliasRows] = await Promise.all([
        apiRequest<MerchantRow[]>("/api/merchants", {}, token),
        apiRequest<MerchantAliasRow[]>("/api/merchant-aliases", {}, token),
      ]);
      setMerchants(merchantRows);
      setAliases(aliasRows);
      setSelectedMerchantId((current) => current || merchantRows[0]?.id || "");
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setLoading(false);
    }
  }

  async function loadMerchantDetail(merchantId: string) {
    if (!merchantId) {
      setRecentTransactions([]);
      return;
    }

    setDetailLoading(true);
    setError("");
    try {
      const transactions = await apiRequest<TransactionRow[]>(
        `/api/transactions?merchant_id=${encodeURIComponent(merchantId)}`,
        {},
        token,
      );
      setRecentTransactions(transactions.slice(0, 5));
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    void loadMerchants();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    void loadMerchantDetail(selectedMerchantId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMerchantId, token]);

  const filteredMerchants = useMemo(() => {
    return merchants.filter((merchant) => {
      const matchesSearch =
        !search ||
        [merchant.display_name, merchant.raw_name, merchant.category ?? ""]
          .join(" ")
          .toLowerCase()
          .includes(search.toLowerCase());
      const matchesStatus = statusFilter === "all" || merchant.status === statusFilter;
      const matchesCategory =
        !categoryFilter || (merchant.category ?? "").toLowerCase().includes(categoryFilter.toLowerCase());
      const matchesTransfer =
        transferFilter === "all" ||
        (transferFilter === "transfer" ? merchant.is_transfer : !merchant.is_transfer);
      return matchesSearch && matchesStatus && matchesCategory && matchesTransfer;
    });
  }, [categoryFilter, merchants, search, statusFilter, transferFilter]);

  const selectedMerchant = merchants.find((merchant) => merchant.id === selectedMerchantId) ?? null;
  const selectedAliases = aliases.filter((alias) => alias.merchant_id === selectedMerchantId);

  async function saveMerchant(merchant: MerchantRow) {
    try {
      await apiRequest<MerchantRow>(
        `/api/merchants/${merchant.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: draftDisplayNames[merchant.id] ?? merchant.display_name,
            category: draftCategories[merchant.id] ?? merchant.category ?? "",
          }),
        },
        token,
      );
      setMessage(`Saved merchant changes for ${merchant.display_name}.`);
      await loadMerchants();
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  async function createAlias() {
    if (!selectedMerchantId || !newAlias.trim()) {
      setError("Choose a merchant and enter an alias.");
      return;
    }
    try {
      await apiRequest(
        `/api/merchants/${selectedMerchantId}/aliases`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ alias: newAlias }),
        },
        token,
      );
      setNewAlias("");
      setMessage("Alias added.");
      await loadMerchants();
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  async function deleteAlias(aliasId: string) {
    try {
      await fetch(`/api/merchant-aliases/${aliasId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }).then(async (response) => {
        if (!response.ok) {
          const payload = (await response.json().catch(() => ({}))) as ApiError;
          throw new Error(errorMessage(payload));
        }
      });
      setMessage("Alias removed.");
      await loadMerchants();
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  async function mergeMerchant() {
    if (!selectedMerchantId || !mergeTargetId) {
      setError("Choose a merge target.");
      return;
    }
    try {
      await apiRequest(
        `/api/merchants/${selectedMerchantId}/merge`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_merchant_id: mergeTargetId }),
        },
        token,
      );
      setMessage("Merchants merged.");
      setMergeTargetId("");
      await loadMerchants();
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  return (
    <section className="workspace-card">
      <div className="section-heading">
        <p className="eyebrow">Merchants</p>
        <h2>Merchant Manager</h2>
        <p>Search the shared merchant registry, repair display names and categories inline, and resolve alias or merge cleanup from one panel.</p>
      </div>

      <div className="filter-grid merchant-filter-grid">
        <label className="field">
          <span>Search</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Coffee, payroll, transfer" />
        </label>
        <label className="field">
          <span>Status</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
            <option value="all">All statuses</option>
            <option value="reviewed">Reviewed</option>
            <option value="unreviewed">Unreviewed</option>
          </select>
        </label>
        <label className="field">
          <span>Category</span>
          <input value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} placeholder="Dining" />
        </label>
        <label className="field">
          <span>Transfer flag</span>
          <select value={transferFilter} onChange={(event) => setTransferFilter(event.target.value as typeof transferFilter)}>
            <option value="all">All merchants</option>
            <option value="transfer">Transfers only</option>
            <option value="non-transfer">Non-transfers</option>
          </select>
        </label>
        <div className="actions-row">
          <button className="primary-button" type="button" onClick={() => void loadMerchants()} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh Registry"}
          </button>
        </div>
      </div>

      {message ? <p className="notice success">{message}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      <div className="split-layout">
        <article className="preview-table-card">
          <div className="table-header">
            <h3>Merchant registry</h3>
            <span>{filteredMerchants.length} merchants</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Merchant</th>
                <th>Raw name</th>
                <th>Category</th>
                <th>Transactions</th>
                <th>Last seen</th>
                <th>Status</th>
                <th>Transfer</th>
              </tr>
            </thead>
            <tbody>
              {filteredMerchants.map((merchant) => (
                <tr
                  key={merchant.id}
                  className={merchant.id === selectedMerchantId ? "table-row-active" : ""}
                  onClick={() => setSelectedMerchantId(merchant.id)}
                >
                  <td>
                    <div className="inline-edit stacked-inline">
                      <input
                        value={draftDisplayNames[merchant.id] ?? merchant.display_name}
                        onChange={(event) =>
                          setDraftDisplayNames((current) => ({ ...current, [merchant.id]: event.target.value }))
                        }
                      />
                      <button className="ghost-button" type="button" onClick={() => void saveMerchant(merchant)}>
                        Save
                      </button>
                    </div>
                  </td>
                  <td>{merchant.raw_name}</td>
                  <td>
                    <input
                      value={draftCategories[merchant.id] ?? merchant.category ?? ""}
                      onChange={(event) =>
                        setDraftCategories((current) => ({ ...current, [merchant.id]: event.target.value }))
                      }
                    />
                  </td>
                  <td>{merchant.transaction_count}</td>
                  <td>{merchant.last_seen ?? "Never"}</td>
                  <td>
                    <span className={merchant.status === "reviewed" ? "status-pill reviewed" : "status-pill"}>
                      {merchant.status}
                    </span>
                  </td>
                  <td>{merchant.is_transfer ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>

        <aside className="preview-metadata detail-panel">
          <h3>Detail panel</h3>
          {selectedMerchant ? (
            <>
              <dl>
                <div>
                  <dt>Display name</dt>
                  <dd>{selectedMerchant.display_name}</dd>
                </div>
                <div>
                  <dt>Raw name</dt>
                  <dd>{selectedMerchant.raw_name}</dd>
                </div>
                <div>
                  <dt>Category</dt>
                  <dd>{selectedMerchant.category ?? "Unassigned"}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{selectedMerchant.status}</dd>
                </div>
              </dl>

              <div className="detail-section">
                <div className="table-header">
                  <h4>Alias rules</h4>
                  <span>{selectedAliases.length}</span>
                </div>
                <div className="actions-row compact-row">
                  <input value={newAlias} onChange={(event) => setNewAlias(event.target.value)} placeholder="COFFEE SHOP TORONTO" />
                  <button className="secondary-button" type="button" onClick={createAlias}>
                    Add alias
                  </button>
                </div>
                {selectedAliases.length ? (
                  <div className="alias-list">
                    {selectedAliases.map((alias) => (
                      <div key={alias.id} className="alias-row">
                        <span>{alias.alias}</span>
                        <button className="ghost-button" type="button" onClick={() => void deleteAlias(alias.id)}>
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted-copy">No aliases yet.</p>
                )}
              </div>

              <div className="detail-section">
                <div className="table-header">
                  <h4>Merge action</h4>
                </div>
                <label className="field">
                  <span>Merge into</span>
                  <select value={mergeTargetId} onChange={(event) => setMergeTargetId(event.target.value)}>
                    <option value="">Choose target merchant</option>
                    {merchants
                      .filter((merchant) => merchant.id !== selectedMerchant.id)
                      .map((merchant) => (
                        <option key={merchant.id} value={merchant.id}>
                          {merchant.display_name}
                        </option>
                      ))}
                  </select>
                </label>
                <button className="ghost-button" type="button" onClick={mergeMerchant}>
                  Merge selected merchant
                </button>
              </div>

              <div className="detail-section">
                <div className="table-header">
                  <h4>Recent transactions</h4>
                  <span>{detailLoading ? "Loading..." : recentTransactions.length}</span>
                </div>
                {recentTransactions.length ? (
                  <div className="detail-transaction-list">
                    {recentTransactions.map((transaction) => (
                      <div key={transaction.id} className="detail-transaction-row">
                        <strong>{transaction.description}</strong>
                        <span>{transaction.posted_on}</span>
                        <span>{transaction.amount}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted-copy">No recent transactions for this merchant yet.</p>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p>Select a merchant to manage aliases, merge actions, and recent transaction history.</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

function SubscriptionsPage({ token }: { token: string }) {
  const [subscriptions, setSubscriptions] = useState<SubscriptionRow[]>([]);
  const [detail, setDetail] = useState<SubscriptionDetail | null>(null);
  const [selectedSubscriptionId, setSelectedSubscriptionId] = useState("");
  const [filter, setFilter] = useState<"all" | "monthly" | "annual" | "inactive">("all");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [editingSubscriptionId, setEditingSubscriptionId] = useState("");
  const [form, setForm] = useState({
    display_name: "",
    category: "",
    interval: "monthly" as SubscriptionRow["interval"],
    amount: "",
    is_active: true,
    merchant_id: "",
    last_charged_on: "",
    next_expected_on: "",
  });
  const [merchants, setMerchants] = useState<MerchantRow[]>([]);

  async function loadSubscriptions(preferredId?: string) {
    setLoading(true);
    setError("");
    try {
      const [subscriptionRows, merchantRows] = await Promise.all([
        apiRequest<SubscriptionRow[]>("/api/subscriptions", {}, token),
        apiRequest<MerchantRow[]>("/api/merchants", {}, token),
      ]);
      setSubscriptions(subscriptionRows);
      setMerchants(merchantRows);
      const nextId = preferredId ?? selectedSubscriptionId ?? subscriptionRows[0]?.id ?? "";
      setSelectedSubscriptionId(nextId);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(subscriptionId: string) {
    if (!subscriptionId) {
      setDetail(null);
      return;
    }

    setDetailLoading(true);
    setError("");
    try {
      const payload = await apiRequest<SubscriptionDetail>(`/api/subscriptions/${subscriptionId}`, {}, token);
      setDetail(payload);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    void loadSubscriptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    void loadDetail(selectedSubscriptionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSubscriptionId, token]);

  const filteredSubscriptions = useMemo(() => {
    return subscriptions.filter((subscription) => {
      if (filter === "all") {
        return true;
      }
      if (filter === "inactive") {
        return !subscription.is_active;
      }
      return subscription.interval === filter && subscription.is_active;
    });
  }, [filter, subscriptions]);

  function resetForm() {
    setForm({
      display_name: "",
      category: "",
      interval: "monthly",
      amount: "",
      is_active: true,
      merchant_id: "",
      last_charged_on: "",
      next_expected_on: "",
    });
    setEditingSubscriptionId("");
    setManualOpen(false);
  }

  async function runDetection() {
    try {
      const payload = await apiRequest<{ detected_count: number; subscriptions: SubscriptionRow[] }>(
        "/api/subscriptions/detect",
        { method: "POST" },
        token,
      );
      setMessage(`Detected or refreshed ${payload.detected_count} recurring subscription${payload.detected_count === 1 ? "" : "s"}.`);
      setSubscriptions(payload.subscriptions);
      setSelectedSubscriptionId(payload.subscriptions[0]?.id ?? "");
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  function startManualCreate() {
    resetForm();
    setManualOpen(true);
  }

  function startEdit(subscription: SubscriptionRow) {
    setEditingSubscriptionId(subscription.id);
    setManualOpen(true);
    setForm({
      display_name: subscription.display_name,
      category: subscription.category ?? "",
      interval: subscription.interval,
      amount: subscription.amount,
      is_active: subscription.is_active,
      merchant_id: subscription.merchant_id ?? "",
      last_charged_on: subscription.last_charged_on ?? "",
      next_expected_on: subscription.next_expected_on ?? "",
    });
  }

  async function saveSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const payload = {
        display_name: form.display_name,
        category: form.category || null,
        interval: form.interval,
        amount: form.amount,
        is_active: form.is_active,
        merchant_id: form.merchant_id || null,
        last_charged_on: form.last_charged_on || null,
        next_expected_on: form.next_expected_on || null,
      };

      const path = editingSubscriptionId ? `/api/subscriptions/${editingSubscriptionId}` : "/api/subscriptions";
      const method = editingSubscriptionId ? "PATCH" : "POST";
      const response = await apiRequest<SubscriptionRow>(
        path,
        {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        token,
      );
      setMessage(editingSubscriptionId ? "Subscription updated." : "Subscription created.");
      resetForm();
      await loadSubscriptions(response.id);
      await loadDetail(response.id);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  return (
    <section className="workspace-card">
      <div className="section-heading">
        <p className="eyebrow">Subscriptions</p>
        <h2>Subscriptions</h2>
        <p>Detect recurring spending, keep recurring entries editable, and review the transaction history supporting each subscription.</p>
      </div>

      <div className="filter-grid subscription-toolbar">
        <label className="field">
          <span>Filter</span>
          <select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}>
            <option value="all">All subscriptions</option>
            <option value="monthly">Monthly</option>
            <option value="annual">Annual</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
        <button className="primary-button" type="button" onClick={() => void runDetection()}>
          Detect recurring charges
        </button>
        <button className="secondary-button" type="button" onClick={startManualCreate}>
          Add manual subscription
        </button>
      </div>

      {message ? <p className="notice success">{message}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      <div className="split-layout">
        <article className="preview-table-card">
          <div className="table-header">
            <h3>Recurring entries</h3>
            <span>{loading ? "Refreshing..." : `${filteredSubscriptions.length} subscriptions`}</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Category</th>
                <th>Interval</th>
                <th>Amount</th>
                <th>Last charged</th>
                <th>Next expected</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {filteredSubscriptions.map((subscription) => (
                <tr
                  key={subscription.id}
                  className={subscription.id === selectedSubscriptionId ? "table-row-active" : ""}
                  onClick={() => setSelectedSubscriptionId(subscription.id)}
                >
                  <td>{subscription.display_name}</td>
                  <td>{subscription.category ?? "Unassigned"}</td>
                  <td>{subscription.interval}</td>
                  <td>{subscription.amount}</td>
                  <td>{subscription.last_charged_on ?? "Unknown"}</td>
                  <td>{subscription.next_expected_on ?? "Unknown"}</td>
                  <td>{subscription.is_active ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>

        <aside className="preview-metadata detail-panel">
          <div className="table-header">
            <h3>Subscription detail</h3>
            {detail ? (
              <button className="ghost-button" type="button" onClick={() => startEdit(detail)}>
                Edit
              </button>
            ) : null}
          </div>

          {manualOpen ? (
            <form className="auth-form compact-form" onSubmit={saveSubscription}>
              <label className="field">
                <span>Display name</span>
                <input value={form.display_name} onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))} />
              </label>
              <label className="field">
                <span>Category</span>
                <input value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))} />
              </label>
              <label className="field">
                <span>Interval</span>
                <select value={form.interval} onChange={(event) => setForm((current) => ({ ...current, interval: event.target.value as SubscriptionRow["interval"] }))}>
                  <option value="monthly">Monthly</option>
                  <option value="annual">Annual</option>
                  <option value="variable">Variable</option>
                </select>
              </label>
              <label className="field">
                <span>Amount</span>
                <input value={form.amount} onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))} placeholder="15.99" />
              </label>
              <label className="field">
                <span>Merchant</span>
                <select value={form.merchant_id} onChange={(event) => setForm((current) => ({ ...current, merchant_id: event.target.value }))}>
                  <option value="">No merchant link</option>
                  {merchants.map((merchant) => (
                    <option key={merchant.id} value={merchant.id}>
                      {merchant.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Last charged</span>
                <input type="date" value={form.last_charged_on} onChange={(event) => setForm((current) => ({ ...current, last_charged_on: event.target.value }))} />
              </label>
              <label className="field">
                <span>Next expected</span>
                <input type="date" value={form.next_expected_on} onChange={(event) => setForm((current) => ({ ...current, next_expected_on: event.target.value }))} />
              </label>
              <label className="toggle">
                <input checked={form.is_active} onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))} type="checkbox" />
                <span>Active subscription</span>
              </label>
              <div className="actions-row">
                <button className="primary-button" type="submit">
                  {editingSubscriptionId ? "Save subscription" : "Create subscription"}
                </button>
                <button className="ghost-button" type="button" onClick={resetForm}>
                  Cancel
                </button>
              </div>
            </form>
          ) : detail ? (
            <>
              <dl>
                <div>
                  <dt>Display name</dt>
                  <dd>{detail.display_name}</dd>
                </div>
                <div>
                  <dt>Category</dt>
                  <dd>{detail.category ?? "Unassigned"}</dd>
                </div>
                <div>
                  <dt>Interval</dt>
                  <dd>{detail.interval}</dd>
                </div>
                <div>
                  <dt>Amount</dt>
                  <dd>{detail.amount}</dd>
                </div>
                <div>
                  <dt>Active</dt>
                  <dd>{detail.is_active ? "Yes" : "No"}</dd>
                </div>
              </dl>

              <div className="detail-section">
                <div className="table-header">
                  <h4>Recent matching transactions</h4>
                  <span>{detailLoading ? "Loading..." : detail.recent_matches.length}</span>
                </div>
                {detail.recent_matches.length ? (
                  <div className="detail-transaction-list">
                    {detail.recent_matches.map((match) => (
                      <div key={match.transaction_id} className="detail-transaction-row">
                        <strong>{match.description}</strong>
                        <span>{match.posted_on}</span>
                        <span>{match.amount}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted-copy">No matching transactions are attached yet.</p>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p>Run detection or create a manual subscription to start reviewing recurring spending.</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

function BudgetCreator({ token }: { token: string }) {
  const [monthStart, setMonthStart] = useState("2026-04-01");
  const [step, setStep] = useState(1);
  const [recommendations, setRecommendations] = useState<BudgetRecommendation[]>([]);
  const [draftAmounts, setDraftAmounts] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activating, setActivating] = useState(false);

  const fixedRecommendations = recommendations.filter((item) => item.source_type === "subscription");
  const variableRecommendations = recommendations.filter((item) => item.source_type === "variable");
  const totalPlanned = recommendations.reduce((sum, item) => sum + Number(draftAmounts[item.id] ?? item.planned_amount), 0);

  async function generateBudget() {
    setLoading(true);
    setError("");
    try {
      const response = await apiRequest<{ month_start: string; recommendations: BudgetRecommendation[] }>(
        "/api/budgets/generate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ month_start: monthStart }),
        },
        token,
      );
      setRecommendations(response.recommendations);
      setDraftAmounts(
        Object.fromEntries(response.recommendations.map((item) => [item.id, item.planned_amount])),
      );
      setStep(1);
      setMessage(`Generated ${response.recommendations.length} budget recommendations for ${response.month_start}.`);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setLoading(false);
    }
  }

  async function saveBudgetAmount(budgetId: string) {
    try {
      const updated = await apiRequest<BudgetRecommendation>(
        `/api/budgets/${budgetId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ planned_amount: draftAmounts[budgetId] }),
        },
        token,
      );
      setRecommendations((current) =>
        current.map((item) =>
          item.id === budgetId ? { ...item, planned_amount: updated.planned_amount } : item,
        ),
      );
      setMessage(`Updated ${updated.category}.`);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    }
  }

  async function activateBudget() {
    setActivating(true);
    setError("");
    try {
      const response = await apiRequest<{ activated_count: number }>(
        "/api/budgets/activate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ month_start: monthStart }),
        },
        token,
      );
      setRecommendations((current) => current.map((item) => ({ ...item, is_active: true })));
      setMessage(`Activated ${response.activated_count} budget row${response.activated_count === 1 ? "" : "s"} for ${monthStart}.`);
    } catch (requestError) {
      setError(errorMessage((requestError as Error).message));
    } finally {
      setActivating(false);
    }
  }

  function stepCopy() {
    if (step === 1) {
      return {
        title: "Step 1: Fixed spending",
        description: "Review the subscription-backed entries first so fixed recurring obligations are locked before variable categories move.",
      };
    }
    if (step === 2) {
      return {
        title: "Step 2: Variable limits",
        description: "Adjust the history-based category averages, especially where limited history produced a rougher fallback.",
      };
    }
    return {
      title: "Step 3: Activation summary",
      description: "Confirm the month, planned total, and reviewed categories before making this budget the active plan.",
    };
  }

  const activeStepCopy = stepCopy();

  return (
    <section className="workspace-card">
      <div className="section-heading">
        <p className="eyebrow">Budget</p>
        <h2>Budget Creator</h2>
        <p>Generate a monthly baseline from subscriptions and historical spending, edit the stored recommendations, and activate the month when the review is complete.</p>
      </div>

      <div className="filter-grid budget-toolbar">
        <label className="field">
          <span>Budget month</span>
          <input type="date" value={monthStart} onChange={(event) => setMonthStart(event.target.value)} />
        </label>
        <button className="primary-button" type="button" onClick={() => void generateBudget()} disabled={loading}>
          {loading ? "Generating..." : "Generate budget"}
        </button>
      </div>

      {message ? <p className="notice success">{message}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      <div className="stepper-row">
        {[1, 2, 3].map((stepNumber) => (
          <button
            key={stepNumber}
            type="button"
            className={step === stepNumber ? "step-pill active" : "step-pill"}
            onClick={() => setStep(stepNumber)}
            disabled={!recommendations.length}
          >
            Step {stepNumber}
          </button>
        ))}
      </div>

      <div className="split-layout">
        <article className="preview-table-card">
          <div className="table-header">
            <div>
              <h3>{activeStepCopy.title}</h3>
              <p className="muted-copy">{activeStepCopy.description}</p>
            </div>
            <span>{recommendations.length} rows</span>
          </div>

          {step === 1 ? (
            <div className="budget-review-list">
              {fixedRecommendations.map((item) => (
                <div key={item.id} className="budget-row-card">
                  <div>
                    <strong>{item.category}</strong>
                    <p className="muted-copy">{item.subscription_names.join(", ") || "No subscriptions linked"}</p>
                  </div>
                  <div className="inline-edit">
                    <input
                      value={draftAmounts[item.id] ?? item.planned_amount}
                      onChange={(event) =>
                        setDraftAmounts((current) => ({ ...current, [item.id]: event.target.value }))
                      }
                    />
                    <button className="ghost-button" type="button" onClick={() => void saveBudgetAmount(item.id)}>
                      Save
                    </button>
                  </div>
                </div>
              ))}
              {!fixedRecommendations.length ? <div className="empty-state"><p>No fixed subscription entries were generated.</p></div> : null}
            </div>
          ) : null}

          {step === 2 ? (
            <div className="budget-review-list">
              {variableRecommendations.map((item) => (
                <div key={item.id} className="budget-row-card">
                  <div>
                    <strong>{item.category}</strong>
                    <p className="muted-copy">Average from {item.months_used} month{item.months_used === 1 ? "" : "s"} of history</p>
                  </div>
                  <div className="inline-edit">
                    <input
                      value={draftAmounts[item.id] ?? item.planned_amount}
                      onChange={(event) =>
                        setDraftAmounts((current) => ({ ...current, [item.id]: event.target.value }))
                      }
                    />
                    <button className="ghost-button" type="button" onClick={() => void saveBudgetAmount(item.id)}>
                      Save
                    </button>
                  </div>
                </div>
              ))}
              {!variableRecommendations.length ? <div className="empty-state"><p>No variable category limits were generated.</p></div> : null}
            </div>
          ) : null}

          {step === 3 ? (
            <div className="budget-review-list">
              {recommendations.map((item) => (
                <div key={item.id} className="budget-row-card">
                  <div>
                    <strong>{item.category}</strong>
                    <p className="muted-copy">{item.source_type === "subscription" ? "Fixed" : "Variable"} entry</p>
                  </div>
                  <span>{draftAmounts[item.id] ?? item.planned_amount}</span>
                </div>
              ))}
            </div>
          ) : null}
        </article>

        <aside className="preview-metadata detail-panel">
          <h3>Activation summary</h3>
          <dl>
            <div>
              <dt>Month</dt>
              <dd>{monthStart}</dd>
            </div>
            <div>
              <dt>Fixed rows</dt>
              <dd>{fixedRecommendations.length}</dd>
            </div>
            <div>
              <dt>Variable rows</dt>
              <dd>{variableRecommendations.length}</dd>
            </div>
            <div>
              <dt>Planned total</dt>
              <dd>{totalPlanned.toFixed(2)}</dd>
            </div>
          </dl>
          <div className="actions-row">
            <button className="ghost-button" type="button" onClick={() => setStep((current) => Math.max(1, current - 1))}>
              Previous
            </button>
            <button className="secondary-button" type="button" onClick={() => setStep((current) => Math.min(3, current + 1))}>
              Next
            </button>
          </div>
          <button className="primary-button" type="button" onClick={() => void activateBudget()} disabled={!recommendations.length || activating}>
            {activating ? "Activating..." : "Activate month budget"}
          </button>
        </aside>
      </div>
    </section>
  );
}

export function App() {
  const [token, setToken] = useState<string>(() => window.localStorage.getItem("private-ledger-token") ?? "");
  const [user, setUser] = useState<UserSummary | null>(null);
  const [view, setView] = useState<AppView>("dashboard");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("secret-pass");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      setUser(null);
      window.localStorage.removeItem("private-ledger-token");
      return;
    }

    window.localStorage.setItem("private-ledger-token", token);
    void apiRequest<UserSummary>("/api/me", {}, token)
      .then((payload) => {
        setUser(payload);
        setLoginError("");
      })
      .catch(() => {
        setToken("");
        setUser(null);
      });
  }, [token]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginLoading(true);
    setLoginError("");

    try {
      const payload = await apiRequest<{ access_token: string }>("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      setToken(payload.access_token);
    } catch (requestError) {
      setLoginError(errorMessage((requestError as Error).message));
    } finally {
      setLoginLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Authenticated Workspace</p>
          <h1>Private Ledger</h1>
          <p className="hero-copy">
            Sign in to move between dashboard review, imports, ledger cleanup, recurring subscriptions, and monthly budget activation from one local-first workspace.
          </p>
        </div>

        {user ? (
          <div className="session-chip">
            <span>{user.display_name}</span>
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                setToken("");
                setUser(null);
              }}
            >
              Sign out
            </button>
          </div>
        ) : null}
      </section>

      {!user ? (
        <section className="workspace-card auth-card">
          <div className="section-heading">
            <p className="eyebrow">Sign in</p>
            <h2>Connect to the local backend</h2>
            <p>Use the bootstrapped admin account or any existing household user to unlock protected API flows.</p>
          </div>

          <form className="auth-form" onSubmit={handleLogin}>
            <label className="field">
              <span>Email</span>
              <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
            </label>
            <label className="field">
              <span>Password</span>
              <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
            </label>
            <button className="primary-button" type="submit" disabled={loginLoading}>
              {loginLoading ? "Signing in..." : "Sign in"}
            </button>
            {loginError ? <p className="notice error">{loginError}</p> : null}
          </form>
        </section>
      ) : (
        <div className="workspace-grid">
          <aside className="nav-card">
            <p className="eyebrow">Workspace</p>
            <nav>
              {views.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={item.id === view ? "nav-item active" : "nav-item"}
                  onClick={() => setView(item.id)}
                >
                  <strong>{item.title}</strong>
                  <span>{item.summary}</span>
                </button>
              ))}
            </nav>
          </aside>

          <div className="workspace-content">
            {view === "dashboard" ? <DashboardPage token={token} onNavigate={setView} /> : null}
            {view === "import" ? <ImportWizard token={token} /> : null}
            {view === "transactions" ? <TransactionManager token={token} /> : null}
            {view === "merchants" ? <MerchantManager token={token} /> : null}
            {view === "subscriptions" ? <SubscriptionsPage token={token} /> : null}
            {view === "budget" ? <BudgetCreator token={token} /> : null}
          </div>
        </div>
      )}
    </main>
  );
}
