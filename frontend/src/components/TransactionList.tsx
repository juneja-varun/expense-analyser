import { useEffect, useMemo, useState } from "react";

import { listTransactions, setTransactionCategory } from "../api/finance";
import type { Category, Transaction, TransactionFilters } from "../api/finance";
import { formatDate, formatMagnitude, isDebit } from "../lib/format";

interface Props {
  categories: Category[];
  filters: TransactionFilters;
  /** Bumped by the parent after an upload, to force a refetch. */
  reloadKey: number;
  onCategorised: () => void;
}

export function TransactionList({ categories, filters, reloadKey, onCategorised }: Props) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);

  // Only leaf-ish categories are worth offering: filing under a top-level
  // "Food & Dining" is almost always less useful than its children.
  const options = useMemo(
    () => [...categories].sort((a, b) => a.full_name.localeCompare(b.full_name)),
    [categories],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listTransactions({ ...filters, limit: 100 })
      .then((page) => {
        if (!cancelled) setTransactions(page.results);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters, reloadKey]);

  async function recategorise(transaction: Transaction, value: string) {
    const categoryId = value === "" ? null : Number(value);
    setSaving(transaction.id);
    try {
      const updated = await setTransactionCategory(transaction.id, categoryId);
      setTransactions((current) =>
        current.map((t) => (t.id === updated.id ? updated : t)),
      );
      onCategorised();
    } finally {
      setSaving(null);
    }
  }

  if (loading) return <p className="muted">Loading transactions…</p>;

  if (transactions.length === 0) {
    return (
      <p className="muted">
        No transactions match. Upload a statement to get started.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="transactions">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Description</th>
            <th scope="col">Category</th>
            <th scope="col" className="numeric">
              Amount
            </th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((transaction) => (
            <tr key={transaction.id}>
              <td className="nowrap">{formatDate(transaction.txn_date)}</td>
              <td>
                <span className="description">{transaction.description}</span>
                <span className="muted small">{transaction.source_name}</span>
              </td>
              <td>
                <select
                  aria-label={`Category for ${transaction.description}`}
                  value={transaction.category ?? ""}
                  disabled={saving === transaction.id}
                  onChange={(e) => void recategorise(transaction, e.target.value)}
                >
                  <option value="">Uncategorised</option>
                  {options.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.full_name}
                    </option>
                  ))}
                </select>
                {transaction.is_categorised_by_user && (
                  <span className="badge" title="You set this — imports won't change it">
                    yours
                  </span>
                )}
              </td>
              <td className={`numeric ${isDebit(transaction.amount) ? "debit" : "credit"}`}>
                {isDebit(transaction.amount) ? "−" : "+"}
                {formatMagnitude(transaction.amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
