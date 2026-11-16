const DEFAULT_LOCALE = "en-IN";

const CURRENCY_MINOR_UNITS = Object.freeze({
  BHD: 3, KWD: 3, OMR: 3,
  JPY: 0, KRW: 0,
  INR: 2, USD: 2, EUR: 2, GBP: 2, AED: 2, SGD: 2,
  AUD: 2, CAD: 2, CHF: 2, CNY: 2, HKD: 2, NZD: 2,
});

const DECIMAL_PATTERN = /^([+-]?)(\d+)(?:\.(\d+))?$/;

export function formatMoney(value, options = {}) {
  const fallback = options.fallback ?? "Unavailable";
  if (!value || typeof value.amount !== "string" || typeof value.currency !== "string") {
    return fallback;
  }

  const currency = value.currency.toUpperCase();
  const minorUnits = CURRENCY_MINOR_UNITS[currency];
  if (minorUnits === undefined) return fallback;

  const match = DECIMAL_PATTERN.exec(value.amount);
  if (!match) return fallback;

  const [, sign, whole, fraction = ""] = match;
  // Price fields may legitimately carry more decimal places than currency
  // minor units (for example, an instrument tick smaller than one paisa).
  // Render them exactly, using BigInt grouping and never Number(amount).
  const fractionDigits = Math.max(minorUnits, fraction.length);
  if (fractionDigits > 8) return fallback;

  try {
    const integer = BigInt(whole || "0");
    const signedInteger = sign === "-" ? -integer : integer;
    const number = new Intl.NumberFormat(options.locale ?? DEFAULT_LOCALE, {
      style: "currency",
      currency,
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
      signDisplay: options.signDisplay ?? "auto",
    });

    const exactFraction = fraction.padEnd(fractionDigits, "0");
    return number.formatToParts(signedInteger)
      .map((part) => part.type === "fraction" ? exactFraction : part.value)
      .join("");
  } catch {
    return fallback;
  }
}
