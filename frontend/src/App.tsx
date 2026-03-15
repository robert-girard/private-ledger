import { FormEvent, useEffect, useState } from "react";

type AppView = "import";

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

type ApiError = {
  detail?: string | { message?: string; errors?: string[] };
};

const views: Array<{ id: AppView; title: string; summary: string }> = [
  {
    id: "import",
    title: "Import Wizard",
    summary: "Upload CSVs, inspect detected bank profiles, fix unsupported columns, and preview before commit.",
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

export function App() {
  const [token, setToken] = useState<string>(() => window.localStorage.getItem("private-ledger-token") ?? "");
  const [user, setUser] = useState<UserSummary | null>(null);
  const [view] = useState<AppView>("import");
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
                <button key={item.id} type="button" className={item.id === view ? "nav-item active" : "nav-item"}>
                  <strong>{item.title}</strong>
                  <span>{item.summary}</span>
                </button>
              ))}
            </nav>
          </aside>

          <div className="workspace-content">
            <ImportWizard token={token} />
          </div>
        </div>
      )}
    </main>
  );
}
