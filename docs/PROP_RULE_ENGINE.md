# Prop-firm rule engine design

The rule gate in src/tradingbot/compliance/rules.py is intentionally fail-closed.

## Why it exists

The same strategy can be compliant at one firm/account stage and prohibited at another. Bot permission, symbols, API availability, position size, drawdown methodology, payout consistency and mandatory flatten times are not interchangeable between firms or account models.

## Current behaviour

- An unverified profile blocks every entry.
- Automated trading must be explicitly confirmed.
- Every symbol must be on the exact account-model allow-list.
- Quantity must not exceed the profile's max contract count.
- New entries are blocked at or after the configured last-entry time.
- The bot can determine when the mandatory flatten time has been reached.
- The profile must specify verified loss limits and source/version metadata.

The included config/prop_firm_rules.example.toml is deliberately invalid and cannot enable trading.

## What remains before this can drive a paper or live session

1. Select the exact firm and account model.
2. Save an official source URL and verification date.
3. Confirm India purchase, payout and live-stage eligibility in writing.
4. Confirm the platform API and automation permission at each account stage.
5. Fill every rule field from the exact current terms.
6. Add exact trailing/static drawdown logic, consistency calculations, news restrictions, max positions, order rate and daily session calendar.
7. Add tests against a rulebook-specific fixture and have the configuration independently reviewed.

No live order interface exists. The rule gate is a control foundation, not proof of compliance by itself.
