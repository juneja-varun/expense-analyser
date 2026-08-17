import { useCallback, useEffect, useState } from "react";

import type { Category } from "../api/finance";
import {
  copyBudgetsFromPreviousMonth,
  getBudgetProgress,
  setBudget,
} from "../api/insights";
import type { BudgetProgress } from "../api/insights";
import { formatAmount } from "../lib/format";

interface Props {
  categories: Category[];
  month: string;
}

export function BudgetPanel({ categories, month }: Props) {
  const [progress, setProgress] = useState<BudgetProgress | null>(null);
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getBudgetProgress(month)
      .then(setProgress)
      .catch(() => setProgress(null));
  }, [month]);

  useEffect(load, [load]);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!categoryId || !amount) return;
    setBusy(true);
    setError(null);
    try {
      await setBudget(Number(categoryId), month, amount);
      setCategoryId("");
      setAmount("");
      load();
    } catch {
      setError("Couldn't save that budget. It may already exist for this month.");
    } finally {
      setBusy(false);
    }
  }

  async function copyPrevious() {
    setBusy(true);
    try {
      await copyBudgetsFromPreviousMonth(month);
      load();
    } finally {
      setBusy(false);
    }
  }

  // Income can't be budgeted — a budget caps spending.
  const budgetable = categories.filter((category) => !category.is_income);
  const rows = progress?.categories ?? [];

  return (
    <section className="card">
      <div className="toolbar">
        <h2>Budgets</h2>
        {rows.length === 0 && (
          <button type="button" onClick={() => void copyPrevious()} disabled={busy}>
            Copy last month’s
          </button>
        )}
      </div>

      {rows.length > 0 && (
        <>
          <p className="muted small">
            {formatAmount(progress!.total_spent)} spent of{" "}
            {formatAmount(progress!.total_budgeted)} budgeted
          </p>
          <ul className="budgets">
            {rows.map((row) => (
              <li key={row.category} className="budget">
                <div className="budget__head">
                  <span className="budget__name">{row.category_name}</span>
                  <span className={`budget__figure${row.is_over ? " debit" : ""}`}>
                    {formatAmount(row.spent)} / {formatAmount(row.budgeted)}
                  </span>
                </div>
                {/* Uncapped bar width would overflow its track, so the fill is
                    clamped while the percentage text still reports the truth. */}
                <div
                  className="budget__track"
                  role="progressbar"
                  aria-valuenow={row.percent_used}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${row.category_name}: ${row.percent_used}% of budget used`}
                >
                  <div
                    className={`budget__fill${row.is_over ? " budget__fill--over" : ""}`}
                    style={{ width: `${Math.min(row.percent_used, 100)}%` }}
                  />
                </div>
                <p className="budget__meta muted small">
                  {row.is_over
                    ? `${formatAmount(row.remaining.replace("-", ""))} over — ${row.percent_used}% used`
                    : `${formatAmount(row.remaining)} left — ${row.percent_used}% used`}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}

      <form className="budget-form" onSubmit={add}>
        <select
          aria-label="Category to budget"
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
        >
          <option value="">Add a budget…</option>
          {budgetable.map((category) => (
            <option key={category.id} value={category.id}>
              {category.full_name}
            </option>
          ))}
        </select>
        <input
          type="number"
          min="0"
          step="1"
          inputMode="numeric"
          placeholder="Amount"
          aria-label="Budget amount"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <button type="submit" disabled={busy || !categoryId || !amount}>
          Set
        </button>
      </form>

      {error && <p className="notice notice--error">{error}</p>}
    </section>
  );
}
