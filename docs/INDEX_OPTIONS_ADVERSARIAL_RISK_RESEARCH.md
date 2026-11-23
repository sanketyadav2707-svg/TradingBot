# Index Options Buying: Adversarial Risk Audit and Development Protocol

**Last reviewed:** 21 November 2026. **Market:** NSE NIFTY index calls/puts first. BSE SENSEX is a comparison candidate, not an automatically interchangeable route. **Scope:** offline research and synthetic paper trading only. No live order route.

## Core decision

Index option buying is **not proven to be the best way to maximize weekly returns**, and no AI model can be made loss-proof or aware of every future market state. We optimize for measurable **out-of-sample net expectancy subject to strict tail-loss, drawdown, liquidity, availability and operations constraints**. Trade abstention is a valid and often necessary outcome.

SEBI's August 2026 FY25–FY26 study reports substantial aggregate losses among individual equity-derivatives traders, with options accounting for 92% of individual aggregate losses in the report. This is a base-rate warning, not a prediction of this particular strategy's performance:
https://www.sebi.gov.in/reports-and-statistics/research/aug-2026/study-profitability-of-individual-traders-in-the-equity-derivatives-segment-fy25-fy26-_103835.html

NSE explicitly warns that option holders can lose the entire amount paid in a relatively short time:
https://betanseapi.nseindia.com/static/invest/be-a-smart-investor

## P0: failure modes that block entries

| Failure | Concrete control implemented | Remaining limitation |
|---|---|---|
| Wrong strike, call/put, expiry or exchange | `OptionContract` requires explicit right, strike, expiry, instrument key and exchange/underlying mapping | Authentic current NSE/BSE master binding is not yet implemented |
| Incorrect or stale quote, clock skew | `OptionQuote` validates bid/ask and timestamps; entry gate requires fresh underlying and option quotes | Real feed timestamp semantics and 2-second feasibility remain untested |
| Quote substitution after approval | SHA-256 quote snapshot fingerprint and strict instrument key matching | In-process forged inputs remain possible; separate order gateway must recheck before live use |
| Entire option premium at risk | Pre-trade risk uses **full ask debit plus verified round-trip fees**, never a stop-loss amount as a guarantee | Realized losses may also include additional charges, operational errors or uncontrolled position handling |
| Account wipeout from oversized lots | Minimum complete lot and full-debit per-trade/account/day checks; fail closed when a lot is unaffordable | Policy defaults must be tested; not proof a funded account can trade profitably |
| Bid/ask spread and shallow depth | Max spread, best bid/ask quantity, open interest and max moneyness checks | Top-of-book liquidity can vanish before execution; depth is not guaranteed |
| Multiple positions and duplicate orders | Blocks simultaneous option positions, unresolved orders, unreconciled accounts, excessive daily trades | Not yet wired to a durable options-specific broker lifecycle |
| Wrong market session, unverified fees, permission | Explicit bool gates for official session, market health, contract matching and broker authorization | Caller assertions are not evidence; operational gateway must verify independently |
| Trading halts, sudden disconnections, API errors | Refuses halted quotes; existing durable market-data inbox and session supervisor fail closed | Exit execution can become impossible: **kill switch cannot guarantee liquidation** |
| Options expiry gamma acceleration | Option entry blocks expiry day by default, limits days-to-expiry and checks IV ceiling | Delta/gamma/theta/vega scenario validation and regime modeling still needed |
| News-driven gaps and flash crashes | Stress suite models full premium wipeout, exit slippage and falling bid; paper exits use actual bid | No real order-book replay, event calendar, or validated gap model |

## P1: research failure modes

| Failure | Testing requirement |
|---|---|
| Direction right, option still loses | Measure option premium returns after theta, IV, spread, strike selection and fees, not just underlying movement |
| IV crush after event or open | Capture option IV before/after and stress exit bid reductions |
| Theta decay and expiry | Split analysis by DTE; compare expiry-day avoidance with alternatives; no assumed constant theta |
| Delta/gamma and unstable moneyness | Sample options chains by time with exact strike/expiry; test moneyness drift and delta exposure |
| Fee drag on small accounts | Broker-specific dated brokerage, STT, exchange charges, GST, stamp duty and regulatory fees; use pessimistic scenarios |
| Data leakage and lookahead | Event-time joins; ensure chain quotes and index levels existed before signal; next-tick/next-bar paper fill |
| Wrong contract roll or survivorship | Preserve raw contract key for every quote and full historical expiry chain; no stitching option prices across expiries |
| Liquidity illusion | Replay bid/ask and executable size, not LTP; model reject, partial fills, queue loss and outages |
| Regime change and overfitting | Chronological holdout, embargoed cross-validation where needed, confidence intervals, frozen model versions and forward walk |
| Sudden exposure from averaging down | Long-only, one position, no averaging down, no martingale, no revenge trades |
| AI hallucinations or uncertain probabilities | Models produce **signals only**. A separate deterministic risk gateway controls every order; uncertainty triggers abstention |

## Implementation in this branch

- `src/tradingbot/risk/index_options.py`: buy-only NSE/BSE candidate safety gate; Decimal INR accounting; full-premium-at-risk position sizing; current-master/quote checks; spread, size, IV, expiry, drawdown, fees and market-health filters.
- `src/tradingbot/risk/option_stress.py`: explicit IV-crush, zero-bid, worsening spread/slippage and transaction cost P&L stress calculator, without fabricated probabilities.
- `src/tradingbot/paper/index_options.py`: **offline, in-memory** bought-option paper model using ask for entry and bid for exit. Models stop/target/time signals, but fills only when a supplied quote/depth permits them. Stale data and unavailable depth halt and leave the position open. Quote SHA-256 fingerprints prevent using a risk decision with a different market snapshot.
- `src/tradingbot/data/option_quote_store.py`: SQLite append-only normalized option quote snapshots with source IDs, timestamp/provenance, Decimal-preserving values and duplicate/conflict rejection. This is **not** the Upstox Protobuf decoder and does not prove feed authenticity.
- Adversarial unit tests cover full premium wipeout, thin depth, stale quotes, wrong contract, adverse exit, gap-through-stop, risk budget, quote identity binding, recovery block, duplicate entries and tick journal integrity.

### Critical budget reality

For an illustrative **65-unit lot** with option ask **₹100**, premium debit is **₹6,500**, *before charges*. At an account equity of **₹20,000**, that is **32.5% of capital at risk** if the premium becomes worthless. Under this experimental **2% full-premium-risk policy**, the entry is therefore rejected. These are example inputs, **not** a claim that current Nifty contracts have those values. The current instrument master, lot size, quote and fees must be fetched and verified at trading time. Never increase the limit merely to force a trade.

## Mandatory real-data acceptance gates

1. Licensed time-aligned NIFTY underlying/index data and raw option bid/ask, quantity, traded volume, IV and contract metadata at a usable frequency, covering multiple volatility regimes.
2. Correct per-timestamp contract master, historical lot sizes, expiry and session calendars; BSE must be validated independently.
3. Dated exact Upstox/NSE/BSE costs, API entitlements and broker/exchange order restrictions.
4. Formal signal definition, chronological train/validation/untouched test split, leakage audit, and frozen parameter selection without holdout tuning.
5. Realistic queue-aware execution stress, order rejection simulations, stale feed/latency tests, stuck position and reconciliation drills.
6. Paper operation for 8–12 weeks (or longer if regimes are underrepresented), audited net expectancy, maximum drawdown and worst losses. **No automatic transition to live trading.**

Upstox V3 documents a Protobuf WebSocket market feed with bid/ask depth, Greeks and current timestamps; it is not equivalent to a guaranteed historical option-chain archive:
https://upstox.com/developer/api-documentation/v3/get-market-data-feed/

SEBI's retail algorithmic framework and broker conditions must be verified at account onboarding, not assumed from the order-per-second threshold:
https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html
https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html

## Release decision

**NO-GO for live orders and unattended capital exposure.** The new code is an offline options safety/research foundation. It must not be misrepresented as a fully trained, verified, profitable AI trading system. Code tests cannot create the missing market conditions or regulatory evidence.


## 23 November 2026: screenshot-driven safety hardening

The two user-provided screenshots described the following proposed benefits and hazards. These claims are treated as **hypotheses**, not trading guarantees.

| Screenshot claim | Audit finding | Engineering response |
|---|---|---|
| ₹20,000 can access a full index option lot | A whole bought option lot is accessible *only if* its current premium, lot size and charges fit cash and risk budgets; contract specifications change | Keep exact instrument master and whole-lot sizing; never relax the 2% premium-at-risk cap automatically |
| Options can rise 20–50% quickly | Possible but not a reliable expected return | Evaluate net P&L after spread, fees, slippage, and unfavorable exit quotes; no fabricated probability of a breakout |
| Tight bid-ask spread means clean execution | False in thin strikes, sudden news, freezes, and fast markets | Enforce depth/spread/freshness and quote-identity checks; paper fills at bid/ask, not last-traded price |
| Theta causes option value to fall every hour | Overgeneralized: theta is a model sensitivity, not a guaranteed constant loss per hour; price also changes with underlying, volatility, and microstructure | Do not hardcode deterministic hourly theta deductions; require historical bid/ask chains and time-to-expiry-aware research |
| Excellent option bots win only 40–50% | No universal defensible win-rate range | `research/option_performance.py` calculates realized net expectancy, average wins/losses, profit factor, max drawdown, losing streak, and estimated break-even win rate |
| Five losses can create 30–40% drawdown | Possible only at sufficiently large per-trade losses; not an automatic consequence of five losses | Existing 2% full-premium-risk gate plus optional two-loss streak breaker and 20-minute cooldown |
| VIX, policy, budget, and regulatory events can cause spikes and failed stops | True risk category, but market spikes are not directly *caused* by algorithmic throttling in every case | `risk/option_conditions.py` adds verified high-impact-event blackout, IV change and index move shock filters, exchange-state gate, latency, feed recovery, broker health and exchange order eligibility |

### Additional implementation caveats

- The market-conditions layer is **optional in the legacy research entry function** for backward-compatible offline fixtures. Production-grade entry MUST provide a verified `OptionMarketConditions` and `OptionConditionPolicy`, with independently authenticated data sources. An optional caller-supplied boolean is not a regulatory attestation.
- The high-impact-event input is a **single nearest event time** and requires a verified calendar snapshot. It does not discover RBI announcements, elections, company news or surprise events. Unknown or stale event coverage blocks when the conditions layer is used.
- Loss-streak and cooldown values must come from reconciled durable realized trade history. A process restart must not reset these. Current market-context integration is not a production-ready account state machine.
- A zero-bid option quote is now representable for realistic worthless-option and failed-exit simulations. No executable bid quantity means the paper simulator must leave the position unresolved rather than falsely close it.
- The in-memory option paper simulator now halts on an explicit trading halt even when the stop/target/time threshold has not yet triggered. **Halting software does not close a position**.
- The 2% full-premium exposure policy may leave a ₹20,000 account with zero eligible index option trades. That is preferable to falsely claiming controlled risk.

**Still missing:** authenticated historical and live option-chain data, independently verified corporate/economic event calendar, bid/ask depth replay, theta/IV/Greeks sensitivity calibrated to actual options, fee schedules, actual broker acknowledgements, order-state reconciliation, durable option position state, and 8–12 weeks of forward paper evidence. No prediction model has been trained or shown to beat costs.
