# Market shortlist and decision framework

Research snapshot: 4 November 2026. This is a shortlist, not a final selection. Product eligibility differs by firm/account model; verify each allowed-symbol list before any challenge.

## Initial candidate set

| Contract | Market | Tick size | Tick value | Initial view |
|---|---|---:|---:|---|
| MES | Micro S&P 500 | 0.25 index points | $1.25 | First test candidate: broad US index exposure and substantial volume |
| MNQ | Micro Nasdaq-100 | 0.25 index points | $0.50 | First test candidate: exceptionally active, but price swings can be sharp |
| MGC | Micro Gold | $0.10/oz | $1.00 | First test candidate: strong micro-metals activity; distinct macro drivers |
| MCL | Micro WTI Crude Oil | $0.01/barrel | $1.00 | Secondary test: active, but oil inventory/geopolitical news and contract expiry matter |
| M2K | Micro Russell 2000 | 0.10 index points | $0.50 | Secondary test: compare spread and depth against MES/MNQ |
| MYM | Micro Dow | 1 index point | $0.50 | Secondary test: compare actual spread/depth and opportunity count |

CME contract-spec references:
- MES: https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.contractSpecs.html
- MNQ: https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html
- Micro equity index tick table: https://www.cmegroup.com/articles/faqs/frequently-asked-questions-micro-e-mini-equity-index-futures.html
- MGC: https://www.cmegroup.com/education/courses/event-contracts-underlying-markets/product-gold
- MCL: https://www.cmegroup.com/education/articles-and-reports/micro-wti-crude-oil-futures-faq

## What the recent volume data actually says

CME's September 2026 monthly report cited:
- MNQ average daily volume: 2.4 million contracts.
- MES average daily volume: 1.1 million contracts.
- MCL average daily volume: 240,000 contracts.

Source: https://www.cmegroup.com/media-room/press-releases/2026/10/02/cme_group_reportsrecordaveragedailyvolumeforseptemberandq3driven.html

CME's September 2026 ADV report also shows Micro Gold at 378,000 contracts (up 21% year over year). The same report confirms the volume figures above.
Source: https://www.cmegroup.com/media-room/press-releases/2026/10/02/cme_group_reportsrecordaveragedailyvolumeforseptemberandq3driven.html

These are market-wide exchange statistics, not proof that a specific contract month has tight spreads at every time of day. We still need to measure bid/ask spread, depth, slippage and trade frequency in the precise US session we intend to use. CME's September 2026 report lists E-mini S&P 500 ADV of 1.8m, which is the full-size ES contract and must not be confused with MES at 1.1m. Public reports found in this pass do not provide a comparable verified ADV series for M2K and MYM, so they remain secondary until measured.

## Prop-firm symbol cross-check

FundedNext Futures' current published futures symbol list includes all six shortlisted micros: MES, MNQ, M2K, MYM, MGC and MCL. Tradeify's supported-products list also includes all six. This establishes only product-list availability, not the contract limit or API permission for every account model. Topstep symbol access must be checked in the account's current platform/product list.

Sources:
- FundedNext: https://helpfutures.fundednext.com/en/articles/17225740-which-symbols-instruments-can-i-trade-on-fundednext-futures
- Tradeify: https://help.tradeify.co/en/articles/10468222-rules-supported-trading-products-assets

## Preliminary research order

1. MES and MNQ side-by-side, same strategy and same dates.
2. MGC after the data pipeline can represent its different tick scale and session.
3. MCL after adding scheduled inventory-event filters and contract-expiry controls.
4. M2K and MYM only if their measured cost and fill quality compete with the leading candidates.

Do not decide based solely on volatility. A market with larger candles can still be worse after spread, slippage, fees and drawdown.

## US cash-session timing in India

The US equity cash session is 09:30–16:00 America/New_York. It maps to:
- 19:00–01:30 IST while US daylight saving time is active.
- 20:00–02:30 IST while US standard time is active.

Use IANA time zones (America/New_York), not fixed UTC offsets, because daylight saving time changes. The CME futures session is much longer than the cash session; the cash-session window is only the first window to benchmark, not an instruction to trade every minute.

## Final selection scorecard

We will not declare a winner until the same test harness measures each candidate on comparable, correctly licensed data.

| Criterion | Weight | Measurement |
|---|---:|---|
| Executable liquidity | 20% | Median spread, spread percentiles, depth, simulated slippage |
| Strategy fit at 3–15 min | 20% | Out-of-sample expectancy after all costs, trade count, MAE/MFE |
| Firm compatibility | 20% | Written bot permission, symbol availability, execution/API at each account stage |
| Data quality and cost | 15% | Licensed 1-minute/tick history, real-time access, gaps, roll quality |
| Drawdown behaviour | 15% | Daily and total drawdown, worst streak, tail loss, rule-buffer usage |
| Operational fit | 10% | Session time in IST, news schedule, contract roll/expiry complexity |

A candidate can be removed for a hard disqualifier (no legal access, no permitted API, poor data, or firm symbol prohibition) regardless of its numerical score.

## Decision status

**No live market selected yet.** MES/MNQ are the first comparative tests. The engine is instrument-agnostic so the choice can be changed in config without rewriting strategy or risk code.
