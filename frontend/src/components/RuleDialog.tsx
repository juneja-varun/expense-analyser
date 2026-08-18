import { useEffect, useState } from "react";

import type { Category } from "../api/finance";
import { createRule, previewRule, suggestRule } from "../api/rules";
import type { MatchType, RuleSuggestion } from "../api/rules";
import { ApiError } from "../api/client";
import { formatDate } from "../lib/format";

interface Props {
  /** The narration the rule is being written for. */
  description: string;
  categories: Category[];
  /** Pre-selected when the user already chose a category for the transaction. */
  initialCategory: number | null;
  onClose: () => void;
  /** Called after a rule is saved, with how many transactions it categorised. */
  onSaved: (applied: number) => void;
}

const MATCH_TYPES: { value: MatchType; label: string }[] = [
  { value: "contains", label: "Description contains" },
  { value: "starts_with", label: "Description starts with" },
  { value: "exact", label: "Description is exactly" },
  { value: "upi_vpa", label: "UPI VPA is" },
  { value: "regex", label: "Description matches regex" },
];

export function RuleDialog({
  description,
  categories,
  initialCategory,
  onClose,
  onSaved,
}: Props) {
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [pattern, setPattern] = useState("");
  const [category, setCategory] = useState<number | null>(initialCategory);
  const [preview, setPreview] = useState<RuleSuggestion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Until the suggestion lands there is no pattern to preview, and firing the
  // preview against an empty one would flash "0 matches" at the user.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    suggestRule(description)
      .then((suggestion) => {
        if (cancelled) return;
        setMatchType(suggestion.match_type);
        setPattern(suggestion.pattern);
        setPreview(suggestion);
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [description]);

  // Re-preview as the pattern is edited. Debounced because this counts against
  // every transaction in the household on each keystroke otherwise.
  useEffect(() => {
    if (!ready || !pattern.trim()) return;
    let cancelled = false;

    const timer = window.setTimeout(() => {
      previewRule(pattern, matchType)
        .then((data) => {
          if (cancelled) return;
          setPreview(data);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          // A bad regex is the expected failure here, and the API says which.
          setPreview(null);
          setError(
            err instanceof ApiError
              ? (Object.values(err.fieldErrors).flat()[0] ?? "That pattern is not valid.")
              : "Could not check that pattern.",
          );
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [pattern, matchType, ready]);

  async function save() {
    if (category === null) {
      setError("Pick a category for this rule.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await createRule({ category, match_type: matchType, pattern });
      onSaved(created.applied);
    } catch (err) {
      const detail =
        err instanceof ApiError
          ? Object.values(err.fieldErrors).flat().join(" ")
          : "Could not save that rule.";
      setError(detail || "Could not save that rule.");
    } finally {
      setSaving(false);
    }
  }

  const options = [...categories].sort((a, b) => a.full_name.localeCompare(b.full_name));

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Add a categorisation rule"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Always categorise this merchant</h2>
        <p className="muted small">{description}</p>

        <label>
          <span>Rule</span>
          <div className="rule-row">
            <select
              aria-label="How to match"
              value={matchType}
              onChange={(e) => setMatchType(e.target.value as MatchType)}
            >
              {MATCH_TYPES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <input
              aria-label="Pattern to match"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder="Loading suggestion…"
            />
          </div>
        </label>

        <label>
          <span>File it under</span>
          <select
            aria-label="Category for this rule"
            value={category ?? ""}
            onChange={(e) => setCategory(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Choose a category…</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.full_name}
              </option>
            ))}
          </select>
        </label>

        {preview && (
          <div className="rule-preview">
            <strong>
              {preview.matches === 0
                ? "Matches nothing yet"
                : `Matches ${preview.matches} transaction${preview.matches === 1 ? "" : "s"}`}
            </strong>
            <ul>
              {preview.examples.map((example) => (
                <li key={example.id}>
                  <span className="muted small">{formatDate(example.txn_date)}</span>{" "}
                  {example.description}
                  {example.category_name && (
                    <span className="muted small"> — now {example.category_name}</span>
                  )}
                  {example.is_categorised_by_user && (
                    <span className="badge" title="You filed this one — the rule won't move it">
                      yours
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {preview.matches > preview.examples.length && (
              <p className="muted small">
                …and {preview.matches - preview.examples.length} more.
              </p>
            )}
            {preview.protected > 0 && (
              <p className="muted small">
                {preview.protected} of these you filed by hand, and will be left as they are.
              </p>
            )}
          </div>
        )}

        {error && <p className="notice notice--error">{error}</p>}

        <div className="modal__actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" onClick={() => void save()} disabled={saving || !pattern.trim()}>
            {saving ? "Saving…" : "Save rule"}
          </button>
        </div>
      </div>
    </div>
  );
}
