import { useCallback, useEffect, useMemo, useState } from "react";

import { getTransactionSummary, listCategories } from "../api/finance";
import type { Category, TransactionFilters, TransactionSummary } from "../api/finance";
import { getMonthlyTrend, getSpendByCategory, monthKey } from "../api/insights";
import type { MonthTotals, SpendByCategory } from "../api/insights";
import { BudgetPanel } from "../components/BudgetPanel";
import { MonthlyTrendChart } from "../components/MonthlyTrendChart";
import { SpendByCategoryChart } from "../components/SpendByCategoryChart";
import { TransactionList } from "../components/TransactionList";
import { UploadStatement } from "../components/UploadStatement";
import { useAuth } from "../hooks/useAuth";
import { formatAmount } from "../lib/format";

/** The last 12 months, newest first, for the month picker. */
function recentMonths(count = 12): string[] {
  const now = new Date();
  return Array.from({ length: count }, (_, index) =>
    monthKey(new Date(now.getFullYear(), now.getMonth() - index, 1)),
  );
}

function monthName(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-IN", {
    month: "long",
    year: "numeric",
  });
}

export function DashboardPage() {
  const { user, logout } = useAuth();
  const [categories, setCategories] = useState<Category[]>([]);
  const [summary, setSummary] = useState<TransactionSummary | null>(null);
  const [spend, setSpend] = useState<SpendByCategory | null>(null);
  const [trend, setTrend] = useState<MonthTotals[]>([]);
  const [month, setMonth] = useState(monthKey());
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

  useEffect(() => {
    getSpendByCategory(month)
      .then(setSpend)
      .catch(() => setSpend(null));
    getMonthlyTrend(12)
      .then((data) => setTrend(data.months))
      .catch(() => setTrend([]));
  }, [month, reloadKey]);

  const topLevel = categories.filter((category) => category.depth === 0);
  const months = recentMonths();

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

        <div className="toolbar" style={{ marginTop: "1.5rem" }}>
          <h2>{monthName(month)}</h2>
          <select
            className="month-picker"
            aria-label="Month to analyse"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          >
            {months.map((key) => (
              <option key={key} value={key}>
                {monthName(key)}
              </option>
            ))}
          </select>
        </div>

        <div className="charts">
          <section className="card">
            <h2>Where it went</h2>
            {spend && (
              <SpendByCategoryChart categories={spend.categories} total={spend.total} />
            )}
          </section>

          <section className="card">
            <h2>Month by month</h2>
            <MonthlyTrendChart months={trend} />
          </section>
        </div>

        <div className="charts">
          <BudgetPanel categories={categories} month={month} />
        </div>

        <section className="card" style={{ marginTop: "1.5rem" }}>
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
