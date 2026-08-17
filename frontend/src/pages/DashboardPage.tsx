import { useCallback, useEffect, useMemo, useState } from "react";

import { getTransactionSummary, listCategories } from "../api/finance";
import type { Category, TransactionFilters, TransactionSummary } from "../api/finance";
import { TransactionList } from "../components/TransactionList";
import { UploadStatement } from "../components/UploadStatement";
import { useAuth } from "../hooks/useAuth";
import { formatAmount } from "../lib/format";

export function DashboardPage() {
  const { user, logout } = useAuth();
  const [categories, setCategories] = useState<Category[]>([]);
  const [summary, setSummary] = useState<TransactionSummary | null>(null);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const filters = useMemo<TransactionFilters>(
    () => ({
      search: search || undefined,
      category: categoryFilter || undefined,
    }),
    [search, categoryFilter],
  );

  const refresh = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    listCategories()
      .then((page) => setCategories(page.results))
      .catch(() => setCategories([]));
  }, [reloadKey]);

  useEffect(() => {
    getTransactionSummary(filters)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [filters, reloadKey]);

  const topLevel = categories.filter((c) => c.depth === 0);

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
        <UploadStatement onImported={refresh} />

        {summary && summary.count > 0 && (
          <section className="stats">
            <div className="stat">
              <span className="stat__label">Spent</span>
              <span className="stat__value debit">{formatAmount(summary.spent)}</span>
            </div>
            <div className="stat">
              <span className="stat__label">Received</span>
              <span className="stat__value credit">{formatAmount(summary.received)}</span>
            </div>
            <div className="stat">
              <span className="stat__label">Net</span>
              <span className="stat__value">{formatAmount(summary.net)}</span>
            </div>
            <div className="stat">
              <span className="stat__label">Uncategorised</span>
              <span className="stat__value">
                {summary.uncategorised}
                <span className="muted small"> of {summary.count}</span>
              </span>
            </div>
          </section>
        )}

        <section className="card">
          <div className="toolbar">
            <h2>Transactions</h2>
            <div className="toolbar__filters">
              <input
                type="search"
                placeholder="Search descriptions…"
                aria-label="Search transactions"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <select
                aria-label="Filter by category"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="">All categories</option>
                <option value="none">Uncategorised only</option>
                {topLevel.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <TransactionList
            categories={categories}
            filters={filters}
            reloadKey={reloadKey}
            onCategorised={refresh}
          />
        </section>
      </main>
    </div>
  );
}
