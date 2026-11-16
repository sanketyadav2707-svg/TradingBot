export interface MoneyLike { amount: string; currency: string; }
export interface MoneyFormatOptions {
  locale?: string;
  fallback?: string;
  signDisplay?: "auto" | "always" | "exceptZero" | "negative" | "never";
}
export function formatMoney(value: MoneyLike | null | undefined, options?: MoneyFormatOptions): string;
