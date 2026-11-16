import assert from "node:assert/strict";
import test from "node:test";
import { formatMoney } from "../src/lib/format-money.mjs";

test("INR uses two decimals and Indian grouping", () => {
  const text = formatMoney({ amount: "100000.50", currency: "INR" });
  assert.match(text, /1,00,000\.50/);
  assert.match(text, /₹/);
});
test("USD uses two decimals", () => {
  const text = formatMoney({ amount: "1234.5", currency: "USD" });
  assert.match(text, /1,234\.50/);
  assert.match(text, /\$/);
});
test("JPY uses zero decimals", () => {
  const text = formatMoney({ amount: "1234", currency: "JPY" });
  assert.match(text, /1,234/);
  assert.doesNotMatch(text, /\.\d/);
});
test("KWD uses three decimals", () => {
  const text = formatMoney({ amount: "1234.567", currency: "KWD" });
  assert.match(text, /1,234\.567/);
});
test("signed P&L and unavailable values are explicit", () => {
  assert.match(formatMoney({ amount: "1.25", currency: "INR" }, { signDisplay: "always" }), /\+/);
  assert.match(formatMoney({ amount: "-1.25", currency: "INR" }, { signDisplay: "always" }), /-/);
  assert.equal(formatMoney(null), "Unavailable");
  assert.equal(formatMoney({ amount: "NaN", currency: "INR" }), "Unavailable");
  assert.equal(formatMoney({ amount: "1.00", currency: "XYZ" }), "Unavailable");
});
