import { api } from "./client";
import type { Paginated } from "./finance";

export interface Budget {
  id: number;
  category: number;
  category_name: string | null;
  category_colour: string | null;
  month: string;
  amount: string;
  note: string;
}

export interface BudgetProgressRow {
  category: number;
  category_name: string;
  category_colour: string;
  budgeted: string;
  spent: string;
  remaining: string;
  percent_used: number;
  is_over: boolean;
}

export interface BudgetProgress {
  month: string;
  total_budgeted: string;
  total_spent: string;
  categories: BudgetProgressRow[];
}

export interface CategorySpend {
  category: number | null;
  name: string;
  colour: string;
  /** Positive decimal string: money spent. */
  amount: string;
}

export interface SpendByCategory {
  month: string;
  total: string;
  categories: CategorySpend[];
}

export interface MonthTotals {
  month: string;
  spent: string;
  received: string;
  net: string;
}

/** `YYYY-MM` for the month a date falls in. */
export function monthKey(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export const listBudgets = (month: string) =>
  api.get<Paginated<Budget>>(`/budgets/?month=${month}`);

export const getBudgetProgress = (month: string) =>
  api.get<BudgetProgress>(`/budgets/progress/?month=${month}`);

export const setBudget = (category: number, month: string, amount: string) =>
  api.post<Budget>("/budgets/", { category, month: `${month}-01`, amount });

export const updateBudget = (id: number, amount: string) =>
  api.patch<Budget>(`/budgets/${id}/`, { amount });

export const deleteBudget = (id: number) => api.delete<void>(`/budgets/${id}/`);

export const copyBudgetsFromPreviousMonth = (month: string) =>
  api.post<{ created: number; copied_from: string; skipped_existing: number }>(
    "/budgets/copy_from_previous_month/",
    { month },
  );

export const getSpendByCategory = (month: string) =>
  api.get<SpendByCategory>(`/insights/spend_by_category/?month=${month}`);

export const getMonthlyTrend = (months = 12) =>
  api.get<{ months: MonthTotals[] }>(`/insights/monthly_trend/?months=${months}`);
