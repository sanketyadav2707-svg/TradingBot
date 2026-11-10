# QuantConnect Futures Resolution Access Audit

**Audit date:** 10 November 2026  
**Project constraint:** ₹0 budget; QuantConnect Free Plan  
**Decision:** Minute-resolution MES/MNQ historical research remains available. Do not attempt second- or tick-resolution backtests on the Free Plan.

## Executive result

The Futures dataset page describes historical retention by resolution, but that table is not a statement that every organization tier can access every resolution. The current public plan comparison is the controlling entitlement check:

| Capability | Free Plan | Consequence |
|---|---|---|
| Futures asset class | Included | MES/MNQ futures research is supported |
| Minute/hour/daily resolution | Included | Continue the existing 1-minute research route |
| Second resolution | Not included | Do not schedule a second-resolution probe |
| Tick resolution | Not included | Do not schedule a tick-resolution probe |
| QuantConnect-hosted Futures Live Feed | Not included | No continuous QC-hosted real-time CME feed |
| QuantConnect paper trading | Not included on Free; listed paper-trading row covers equities, forex and crypto | Does not solve futures paper execution |

The Futures dataset documentation lists the available trailing history **when the corresponding resolution is entitled**: one year for minute, two months for second, and one month for tick. Those retention windows must not be mistaken for Free Plan access.

## Primary sources checked

1. QuantConnect plan comparison: https://www.quantconnect.com/pricing/planFree?billing=mo  
   The comparison lists the Free Plan as including minute/hour/daily resolution, while the separate Tick/Second row is unavailable on Free. The Futures Live Feed row is also unavailable on Free.
2. QuantConnect Futures dataset: https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/futures  
   The dataset page documents minute history of one year, second history of two months, and tick history of one month. It also says the Futures dataset is served free. Dataset pricing does not override plan-level resolution entitlements.

## What is verified for this project

- The user previously ran the MES/MNQ one-minute coverage probe on the Free Plan.
- That run returned 267,325 MES bars and 267,349 MNQ bars over 2025-11-04 through 2026-11-03, with 238 active dates for each root and three mapping changes per root.
- This verifies that the tested one-minute continuous-futures subscriptions returned historical bars for that run.
- It does not verify tick/second access, bid/ask quality, live feed, paper execution, or profitable performance.

## Decision and next action

1. Mark the planned Free-Plan second/tick access check as **completed: not entitled**. No cloud backtest is required for this check.
2. Do not upgrade, purchase credits, or use another person's credentials. This project remains ₹0-budget unless the user explicitly changes that constraint.
3. Continue the Week 1 audit using minute data: exchange timezone/DST, session classification, contract mapping transitions, and gap resets.
4. Keep second/tick research as a future optional task only if a legitimate entitlement becomes available and the user explicitly approves any cost.
5. Keep all market data within QuantConnect unless its current licence expressly permits another use. Export only permitted aggregate results.

## Important distinction

"Futures data is free" does not mean "all resolutions and live feed are included in every plan." For this account, the Free Plan supports the minute-resolution route already tested, not the second/tick route or a QuantConnect-hosted live futures feed.
