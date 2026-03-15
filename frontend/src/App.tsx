const sections = [
  {
    title: "Dashboard",
    summary: "Monthly cash flow, budget burn, and recent activity will land here.",
  },
  {
    title: "Transactions",
    summary: "Search, filter, export, and repair transaction data from one view.",
  },
  {
    title: "Import",
    summary: "CSV upload, profile detection, and preview-driven commits.",
  },
  {
    title: "Subscriptions",
    summary: "Recurring spend review and manual subscription management.",
  },
  {
    title: "Merchant Manager",
    summary: "Shared merchant registry, aliases, recategorization, and merges.",
  },
  {
    title: "Reports",
    summary: "Top merchants, trends, category mix, and budget-versus-actual analysis.",
  },
] as const;

export function App() {
  return (
    <main className="app-shell">
      <section className="hero-panel">
        <p className="eyebrow">Authenticated Workspace</p>
        <h1>Private Ledger</h1>
        <p className="hero-copy">
          A self-hosted, privacy-first finance workspace for household operators.
          This scaffold wires the React shell to the FastAPI app so later stories
          can fill in data flows without revisiting the deployment baseline.
        </p>
      </section>

      <section className="status-panel" aria-label="Session summary">
        <div>
          <span className="label">Signed in as</span>
          <strong>Household Admin</strong>
        </div>
        <div>
          <span className="label">Instance mode</span>
          <strong>Local-only</strong>
        </div>
        <div>
          <span className="label">Backend status</span>
          <strong>FastAPI attached</strong>
        </div>
      </section>

      <section className="grid" aria-label="Planned application areas">
        {sections.map((section) => (
          <article key={section.title} className="card">
            <h2>{section.title}</h2>
            <p>{section.summary}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
