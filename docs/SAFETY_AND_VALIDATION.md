# Safety and validation gates

This system is research-only until every gate below is completed. Passing software tests is not proof of a trading edge.

## Safety controls already in the project

- No live broker class or live order endpoint exists.
- The paper broker is local and simulated.
- Risk limits are configurable and checked before each entry.
- Default instrument quantity is capped at one contract in the example config.
- Example data is synthetic and labelled as such.
- Secrets and local data are excluded from Git.
- Strategy signals are generated after a bar closes and filled at the next bar open in the backtester.

## Validation sequence

1. Unit tests for data parsing, risk limits, fills and accounting.
2. Verify contracts/tick values against the chosen firm's allowed-symbol page and current exchange specifications.
3. Check data completeness, timestamps, duplicate bars, missing bars and contract-roll handling.
4. Add commissions, exchange/NFA fees, spread and realistic slippage.
5. Test stop/target ambiguity conservatively (if both touched in one OHLC bar, assume the adverse stop first).
6. Use walk-forward and untouched out-of-sample validation; do not repeatedly tune against the test set.
7. Test across quiet, trending, choppy, high-volatility, news and roll periods.
8. Run a long forward paper-trading period with a frozen strategy version and audit logs.
9. Compare paper fills with observed real-time quotes where properly licensed.
10. Obtain written firm confirmation for bot, API, platform, account stage and India residency.
11. Obtain qualified India-specific legal/tax advice before payment, overseas remittance or payout.
12. Only then consider a low-cost evaluation; never use money needed for education, living costs or emergency savings.

## Mandatory research report statistics

Every strategy report must include net expectancy, profit factor, Sharpe/Sortino with stated assumptions, maximum drawdown, daily loss distribution, worst streak, trade count, average win/loss, MAE/MFE, exposure time, commissions, slippage sensitivity, missed/partial fills and performance by session/regime. Show the exact data window and parameter set.

## Non-negotiable stop conditions

- Daily or trailing drawdown buffer is reached.
- Data connection becomes stale or timestamps stop advancing.
- Position/order state is inconsistent with the broker.
- Duplicate order or repeated API error is detected.
- Instrument/contract month is not verified as active and permitted.
- Risk parameters are missing, invalid or changed without review.
- Kill switch is activated.

The live-trading state remains disabled in code. Any future live adapter requires a separate change review and explicit approval.
