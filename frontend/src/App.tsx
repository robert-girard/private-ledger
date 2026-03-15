import { FormEvent, useEffect, useMemo, useState } from "react";

type AppView = "import" | "transactions" | "merchants";

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

type ApiError = {
  detail?: string | { message?: string; errors?: string[] };
};

const views: Array<{ id: AppView; title: string; summary: string }> = [
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
];

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

export function App() {
  const [token, setToken] = useState<string>(() => window.localStorage.getItem("private-ledger-token") ?? "");
  const [user, setUser] = useState<UserSummary | null>(null);
  const [view, setView] = useState<AppView>("import");
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
            The import flow is the first end-user workflow. Sign in, upload a CSV, review detection, and correct unsupported formats inline.
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
            {view === "import" ? <ImportWizard token={token} /> : null}
            {view === "transactions" ? <TransactionManager token={token} /> : null}
            {view === "merchants" ? <MerchantManager token={token} /> : null}
          </div>
        </div>
      )}
    </main>
  );
}
