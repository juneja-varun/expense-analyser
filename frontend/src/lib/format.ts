/**
 * Indian number formatting.
 *
 * Amounts arrive from the API as decimal strings and are only converted to a
 * number at the point of display — never for arithmetic, which stays on the
 * server in `Decimal`.
 */

const RUPEES = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** ₹1,20,450.00 — lakh grouping, as an Indian user expects to read it. */
export function formatAmount(value: string | number): string {
  const amount = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(amount)) return "—";
  return RUPEES.format(amount);
}

/** The magnitude, for places where a +/− column already carries the sign. */
export function formatMagnitude(value: string | number): string {
  const amount = typeof value === "string" ? Number(value) : value;
  return formatAmount(Math.abs(amount));
}

export function isDebit(amount: string): boolean {
  return Number(amount) < 0;
}

const DATE = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function formatDate(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : DATE.format(parsed);
}
