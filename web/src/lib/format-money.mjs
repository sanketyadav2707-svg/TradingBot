const DEFAULT_LOCALE = "en-IN";

export function formatMoney(value, options = {}) {
  const fallback = options.fallback ?? "Unavailable";
  if (!value || typeof value.amount !== "string" || typeof value.currency !== "string") return fallback;
  const amount = Number(value.amount);
  if (!Number.isFinite(amount)) return fallback;
  try {
    return new Intl.NumberFormat(options.locale ?? DEFAULT_LOCALE, {
      style: "currency",
      currency: value.currency,
      signDisplay: options.signDisplay ?? "auto",
    }).format(amount);
  } catch {
    return fallback;
  }
}
