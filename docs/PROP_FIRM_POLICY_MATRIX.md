# Prop-firm automation and rules research

Research snapshot: 4 November 2026. Firm rules change frequently; the official policy page and the agreement shown at checkout control. This matrix is a development constraint, not a recommendation to buy an evaluation.

## Current comparison

| Firm | Bot/automation position | Execution and funded-stage constraint | India notes |
|---|---|---|---|
| Topstep | Custom bots allowed through TopstepX/ProjectX API, subject to rules and no HFT | API is a separately billed service ($29/month list price); order flow must originate from personal device, no VPS/VPN/remote server for trading; API unavailable on Live Funded accounts | India is not named in the current XFA-only or ineligible country lists reviewed; re-check citizenship and permanent-residency eligibility at signup |
| Tradeify | Personal bots/algorithms allowed under conditions; no HFT; trader must be sole owner and bot must be exclusively for that trader on Tradeify | Must use sanctioned platforms/tools; bot ownership and activity can be reviewed; payout and live transition are separate compliance gates | India is not in the current 65-country restricted list reviewed; agreement separately reserves live-eligibility restrictions, so ask support for written confirmation before purchase |
| FundedNext Futures | EAs/bots allowed on Challenge and FundedNext Accounts through an integration connecting to Tradovate | No overnight/weekend holding; close by 3:10 PM CT; bot setup support is not provided; repeated ultra-short scalps and latency/stale-feed exploitation prohibited | India is absent from the current purchase-restricted list and from the listed special live-review country list reviewed; still obtain written confirmation for your exact residency, payment and payout route |

## Primary official sources

### Topstep
- API access, custom bots and API subscription: https://help.topstep.com/en/articles/11187768-topstepx-api-access
- Country eligibility: https://help.topstep.com/en/articles/8284116-am-i-eligible-to-trade-with-topstep

Important current details:
- API Access is documented as $29/month (Topstep discount may reduce it).
- Custom bots are allowed through the API, with a prohibition on HFT.
- Topstep says all order flow must originate from the personal device; VPS/VPN/remote-server order execution is prohibited.
- Private servers may be used for research, historical data, logs and read-only dashboards, but not order transmission.
- ProjectX API is not available in Live Funded Accounts. Topstep's own help page says to use a Practice account for testing because there is no separate API sandbox.

### Tradeify
- Risk & compliance FAQ: https://help.tradeify.co/en/articles/17069653-risk-compliance-guidelines-faq
- Restricted countries: https://help.tradeify.co/en/articles/10495888-rules-restricted-countries
- Funded Trader Agreement: https://tradeify.co/funded-trader-agreement

Important current details:
- Bots are not a blanket exemption from the trading rules.
- The October 2026 FAQ says automated trading is allowed only as expressly permitted; HFT, unowned/unauthorized bots, strategy sharing, coordination and exploitation can trigger review.
- The October 2026 agreement says the trader must be able to prove sole ownership and exclusive use of a bot on Tradeify; it prohibits HFT bots.
- Tradeify requires the trader personally to own, verify and operate the account. Another person must not access or trade the account; payment must be in the trader's own name.
- The agreement and restricted-country page distinguish evaluation eligibility from eligibility for the Elite Live account. Do not infer live eligibility from ability to buy an evaluation.

### FundedNext Futures
- General Rules: https://fundednext.com/general-rules/futures/what-is-allowed
- Futures FAQ: https://helpfutures.fundednext.com/en/articles/17225788-fundednext-futures-most-frequently-asked-questions
- Country restrictions/live eligibility: https://helpfutures.fundednext.com/en/articles/17228971-are-any-countries-restricted-on-fundednext-futures
- Futures Challenge Terms (updated 25 September 2026): https://fundednext.com/apidocs/futures-challenge-terms

Important current details:
- FundedNext says bots are allowed on Challenges and FundedNext Accounts when used through a platform integration connecting to Tradovate. It does not offer setup/configuration/troubleshooting support.
- Overnight/weekend positions are not allowed; positions must be closed by 3:10 PM CT.
- VPS/VPN is permitted by the FAQ, but inconsistent IP activity can prompt documentation requests.
- The terms allow automation and AI, but prohibit latency/data-feed exploitation, artificial order activity, coordinated trades, and repeated entries/exits within five ticks or without reasonable holding (15–20 seconds).
- Specific challenge models use different maximum-loss, trailing-loss and consistency terms. For example, the published terms state a 40% single-day profit threshold for the referenced models; add-ons may modify rules. The engine must load the exact purchased model's limits rather than assume one universal profile.

## Provisional compatibility conclusion

For our 3–15 minute, personal, fully automated futures-bot goal, **FundedNext Futures currently looks the most compatible of these three on its published bot/VPS rules**, subject to a written confirmation of India live-account eligibility, data/broker setup and payout mechanics.

Topstep is still useful as a future evaluation/practice testbed, but its current API cost, personal-device-only order flow, and no-API Live Funded stage are a material mismatch for unattended 24/7 deployment.

Tradeify may permit a personally-owned bot, but the bot must be exclusively used by the trader on Tradeify; this conflicts with using the same strategy code on several firms unless the firm confirms in writing that code reuse without shared access is acceptable. Its live eligibility also needs separate confirmation.

This is a provisional software-design ranking only. No prop firm has been selected, and no challenge should be purchased during development.

## Required pre-purchase written confirmations

Ask the firm, using your true Indian residency and citizenship, and retain the response:
1. Can a resident of India purchase the evaluation and receive every advertised payout?
2. Is India eligible for simulated funded status and for any live/real-funded transition?
3. Is a custom Python bot written and owned by the trader permitted on the exact platform/account model?
4. Is programmatic order entry allowed in every stage, including any live stage?
5. May the bot run locally on a personal Mac, and are VPS/VPN/cloud execution restrictions different by stage?
6. Which symbols, order types, maximum order rates, news rules, flat times, drawdown and consistency rules apply?
7. Which payment and payout providers can lawfully serve an India resident?

Do not use VPNs, another person's identity/payment method, account sharing, latency exploitation or any technique to bypass residency or firm restrictions.
