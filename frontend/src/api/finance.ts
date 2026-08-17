import { api } from "./client";

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Category {
  id: number;
  name: string;
  full_name: string;
  parent: number | null;
  root: number | null;
  depth: number;
  colour: string;
  is_income: boolean;
  is_system: boolean;
  transaction_count: number;
}

export interface Transaction {
  id: number;
  txn_date: string;
  description: string;
  /** Signed decimal string. Negative is money out. Kept as a string so the
   *  value never passes through a float. */
  amount: string;
  balance: string | null;
  reference: string;
  notes: string;
  category: number | null;
  category_name: string | null;
  category_colour: string | null;
  source: number;
  source_name: string;
  is_categorised_by_user: boolean;
}

export interface TransactionSummary {
  count: number;
  spent: string;
  received: string;
  net: string;
  uncategorised: number;
}

export interface Statement {
  id: number;
  original_filename: string;
  status: "pending" | "parsed" | "failed";
  bank_slug: string;
  statement_kind: string;
  source_name: string | null;
  period_start: string | null;
  period_end: string | null;
  transaction_count: number;
  duplicate_count: number;
  error_message: string;
  was_entirely_duplicate: boolean;
  created_at: string;
}

export interface UploadResult extends Statement {
  created: number;
  duplicates: number;
}

export interface SupportedBank {
  bank_slug: string;
  display_name: string;
  statement_kind: string;
  file_formats: string[];
}

export interface TransactionFilters {
  category?: string;
  search?: string;
  direction?: "debit" | "credit";
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

function toQuery(filters: TransactionFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const listCategories = () => api.get<Paginated<Category>>("/categories/?limit=500");

export const listTransactions = (filters: TransactionFilters = {}) =>
  api.get<Paginated<Transaction>>(`/transactions/${toQuery(filters)}`);

export const getTransactionSummary = (filters: TransactionFilters = {}) =>
  api.get<TransactionSummary>(`/transactions/summary/${toQuery(filters)}`);

export const setTransactionCategory = (id: number, category: number | null) =>
  api.patch<Transaction>(`/transactions/${id}/`, { category });

export const listStatements = () => api.get<Paginated<Statement>>("/statements/");

export const listSupportedBanks = () =>
  api.get<SupportedBank[]>("/statements/supported_banks/");

/**
 * Uploads and imports in one request. Not JSON — the file goes as multipart,
 * and the browser must set its own boundary, so Content-Type is left unset.
 */
export async function uploadStatement(file: File, password?: string): Promise<UploadResult> {
  const body = new FormData();
  body.append("file", file);
  if (password) body.append("password", password);

  const token = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/)?.[2];

  const response = await fetch("/api/statements/", {
    method: "POST",
    body,
    credentials: "same-origin",
    headers: token ? { "X-CSRFToken": decodeURIComponent(token) } : undefined,
  });

  const payload = await response.json();
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null
        ? Object.values(payload).flat().join(" ")
        : "Upload failed.";
    throw new Error(detail);
  }
  return payload as UploadResult;
}
