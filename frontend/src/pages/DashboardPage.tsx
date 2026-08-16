import { useAuth } from "../hooks/useAuth";

/**
 * Placeholder shell. Phase 3 fills this with statement upload and the
 * transaction list; Phase 4 adds the budget and category charts.
 */
export function DashboardPage() {
  const { user, logout } = useAuth();

  return (
    <div className="app">
      <header className="app__header">
        <strong>Expense Analyser</strong>
        <div className="app__user">
          <span>{user?.display_name || user?.email}</span>
          <button type="button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>

      <main className="app__main">
        <h1>Welcome, {user?.display_name || "there"}</h1>
        <p>
          Household <strong>{user?.household.name}</strong> · {user?.household.currency}
        </p>

        <section className="card">
          <h2>Next steps</h2>
          <p>
            The foundation is in place. Statement upload, parsing and categorisation arrive in the
            next phase — see <code>docs/architecture.md</code> for the roadmap.
          </p>
        </section>
      </main>
    </div>
  );
}
