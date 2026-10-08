import { api } from "./client";
import type { Paginated } from "./finance";

export type MatchType = "contains" | "exact" | "starts_with" | "regex" | "upi_vpa";

export interface CategoryRule {
  id: number;
  category: number;
  category_name: string | null;
  match_type: MatchType;
  match_type_label: string;
  pattern: string;
  origin: "user" | "learned" | "builtin";
  priority: number;
  is_active: boolean;
  match_count: number;
}

export interface RuleSuggestion {
  match_type: MatchType;
  match_type_label: string;
  pattern: string;
  /** How many of the household's transactions this pattern already matches. */
  matches: number;
  /** Of those, how many were filed by hand and so will be left untouched. */
  protected: number;
  examples: {
    id: number;
    description: string;
    txn_date: string;
    category_name: string | null;
    is_categorised_by_user: boolean;
  }[];
}

/** What rule would identify this merchant, and what else it would catch. */
export function suggestRule(description: string): Promise<RuleSuggestion> {
  return api.get<RuleSuggestion>(`/rules/suggest/?description=${encodeURIComponent(description)}`);
}

/** Preview a pattern the user has edited, rather than the suggested one. */
export function previewRule(pattern: string, matchType: MatchType): Promise<RuleSuggestion> {
  const params = new URLSearchParams({ pattern, match_type: matchType });
  return api.get<RuleSuggestion>(`/rules/suggest/?${params}`);
}

export function listRules(): Promise<Paginated<CategoryRule>> {
  return api.get<Paginated<CategoryRule>>("/rules/");
}

/** The count of transactions the new rule categorised on save. */
export type CreatedRule = CategoryRule & { applied: number };

export function createRule(rule: {
  category: number;
  match_type: MatchType;
  pattern: string;
}): Promise<CreatedRule> {
  return api.post<CreatedRule>("/rules/", rule);
}

export function setRuleActive(id: number, isActive: boolean): Promise<CategoryRule> {
  return api.patch<CategoryRule>(`/rules/${id}/`, { is_active: isActive });
}

export function deleteRule(id: number): Promise<void> {
  return api.delete<void>(`/rules/${id}/`);
}
