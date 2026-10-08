import { useEffect, useMemo, useState } from "react";

import { listTransactions, setTransactionCategory } from "../api/finance";
import type { Category, Transaction, TransactionFilters } from "../api/finance";
import { formatDate, formatMagnitude, isDebit } from "../lib/format";
import { RuleDialog } from "./RuleDialog";

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
  // The transaction a rule is being written for, if the dialog is open.
  const [ruleFor, setRuleFor] = useState<Transaction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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

  function ruleSaved(applied: number) {
    setRuleFor(null);
    setNotice(
      applied === 0
        ? "Rule saved. It will apply to matching transactions from now on."
        : `Rule saved — ${applied} transaction${applied === 1 ? "" : "s"} categorised.`,
    );
    onCategorised();
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
    <>
      {notice && (
        <p className="notice notice--ok" role="status">
          {notice}
        </p>
      )}
      {ruleFor && (
        <RuleDialog
          description={ruleFor.description}
          categories={categories}
          initialCategory={ruleFor.category}
          onClose={() => setRuleFor(null)}
          onSaved={ruleSaved}
        />
      )}
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
                  {/* The rules could not place this one, so offer to teach them.
                      Also offered for a transaction the user has just categorised
                      by hand, since one correction does not always generalise the
                      way the learned rule assumes. */}
                  <button
                    type="button"
                    className="link"
                    onClick={() => setRuleFor(transaction)}
                    title="Always categorise transactions like this one"
                  >
                    {transaction.category === null ? "Add rule" : "Rule…"}
                  </button>
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
    </>
  );
}
