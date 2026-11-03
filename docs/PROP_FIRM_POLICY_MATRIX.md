# Prop-firm automation and rules research

Research snapshot: 4 November 2026. This is a moving policy snapshot, not legal advice or a recommendation to buy an evaluation. The firm's current agreement, dashboard terms and written support response for the exact account model take precedence.

## Current comparison

| Firm | Bot permission | Main constraints relevant to this project | Provisional fit |
|---|---|---|---|
| FundedNext Futures | Bots are allowed on Challenge and FundedNext accounts through platform integrations connecting to Tradovate | No overnight/weekend positions; flatten by 3:10 PM Central Time; no latency, stale-feed or platform exploit; repeatedly entering/exiting within 5 ticks or without a reasonable 15–20 second hold is prohibited; firm does not configure/support bots | Best current rules fit to investigate for a 3–15 minute bot, subject to exact API, India and payout checks |
| Topstep | Custom bots allowed through TopstepX/ProjectX API; no HFT | API is paid ($29/month list price); order flow must originate from personal device; VPS/VPN/remote-server order execution prohibited; API is unavailable on Live Funded accounts | Poor fit for a fully automated multi-stage career path because the live stage cannot use this API |
| Tradeify | Personal bots allowed under conditions; no HFT | Trader must prove sole ownership; bot must be used exclusively on Tradeify and not across multiple firms; sanctioned tools only; platform API access differs by account stage; Live transition is discretionary | Possible one-firm route, but bot exclusivity and evaluation/sim API limitations make it less flexible |

## Firm-by-firm official policy references

### FundedNext Futures

- Bots/automation: https://fundednext.com/general-rules/futures/what-is-allowed
- Tradable symbols: https://fundednext.com/general-rules/futures/symbols-and-conditions
- Detailed allowed-symbol FAQ: https://helpfutures.fundednext.com/en/articles/17225740-which-symbols-instruments-can-i-trade-on-fundednext-futures
- Trading hours: https://helpfutures.fundednext.com/en/articles/17225754-what-are-the-trading-hours-in-fundednext-futures
- Country restrictions and live eligibility: https://helpfutures.fundednext.com/en/articles/17228971-are-any-countries-restricted-on-fundednext-futures
- Challenge terms: https://fundednext.com/apidocs/futures-challenge-terms

Current published points:
- The general rules say EAs/bots are allowed on both the Challenge and FundedNext Account when used through a platform integration connecting to Tradovate. FundedNext does not provide bot setup, configuration or troubleshooting support.
- Its currently published tradable-symbol list includes MES, MNQ, M2K, MYM, MGC and MCL, among many other contracts. Confirm the exact model's allowed symbols and contract limits before purchase.
- It prohibits overnight/weekend holding. The official hours page says trading runs from 5:00 PM CT until 3:10 PM CT the following day, and any open position is automatically closed at 3:10 PM CT.
- The challenge terms allow automation and AI but prohibit automated activity that exploits platform vulnerabilities, latency, pricing errors, or unfair execution conditions.
- The terms say repeatedly entering/exiting within five ticks or without reasonable holding (15–20 seconds) is against the rules. Our planned 3–15 minute holding horizon is not a license to use micro-scalping or order spam.
- Rules and objectives vary by model and add-on. The bot must load the exact account model's daily loss, maximum loss, consistency, contract limits and flatten time. Never assume a single universal profile.
- The current country page's purchase-restricted list does not include India. Its separate live-review list also does not name India in the snapshot checked. This is not a guarantee of account acceptance, a live transition, payout approval or legal permissibility in India. Get written confirmation using your actual residency and payment details.

### Topstep

- API access and rules: https://help.topstep.com/en/articles/11187768-topstepx-api-access
- Country eligibility: https://help.topstep.com/en/articles/8284116-am-i-eligible-to-trade-with-topstep

Current published points:
- The latest API guide says API Access costs $29/month, apart from the Topstep subscription. There is no dedicated API sandbox; the guide recommends Practice accounts for testing.
- Custom automated strategies/bots are allowed through TopstepX/ProjectX, subject to standard rules and its HFT prohibition.
- All trading activity must originate from the personal device. VPS, VPN and remote-server order execution are prohibited. A server may be used for research, historical data, logging and read-only dashboards, not order transmission.
- The API Gateway is not available for Live Funded accounts. A system depending on this API therefore cannot remain fully automated through that live stage.
- This paid API also does not meet our current zero-budget development constraint.

### Tradeify

- Risk & compliance FAQ: https://help.tradeify.co/en/articles/17069653-risk-compliance-guidelines-faq
- Restricted countries: https://help.tradeify.co/en/articles/10495888-rules-restricted-countries
- Supported products: https://help.tradeify.co/en/articles/10468222-rules-supported-trading-products-assets
- Funded Trader Agreement: https://tradeify.co/funded-trader-agreement

Current published points:
- The October 2026 agreement permits automated bots only if the trader can prove sole ownership and exclusive use; using the bot across multiple prop firms is expressly prohibited by the agreement.
- HFT bots are prohibited. The firm can request proof, review the code and inspect how it is enabled on the trader's personal PC.
- Tradeify's supported micro list includes MES, MNQ, MYM, M2K, MGC and MCL.
- Its help page says the Tradovate API is available only for Live Funded accounts, not evaluation or simulated-funded accounts. This means permission to use a bot should not be confused with API availability for the exact evaluation stage.
- India is not in the current list of 65 completely restricted countries. The agreement separately says some jurisdictions can be eligible for evaluations but not eligible for Elite Live. Obtain written confirmation of live eligibility for an Indian resident; an omitted name is not a guarantee.

## Provisional decision for our architecture

**FundedNext Futures is currently the leading policy candidate to investigate**, because its published rules allow bots on both challenge and funded stages through a Tradovate-connected integration, it lists all six micro candidates, and it imposes a daily flat time that our risk/compliance layer can enforce.

This is not a firm selection. Before any purchase we must confirm:
1. How the precise Tradovate-connected automation path works for our account model, and whether its API access has any separate fees or restrictions.
2. Written India-resident eligibility for challenge, simulated rewards, live transition and payouts.
3. Exact account model, symbols, fees, contract limits, drawdown and consistency rules.
4. Data entitlements, order types, rate limits, platform execution requirements and daily close time.

Topstep is not a target for a full automation-to-live pathway while API is unavailable on Live Funded accounts. Tradeify is less attractive if we want to preserve the option to use the same strategy at other firms because its agreement says bot use is exclusive to Tradeify.

## India-specific legal and payment gate

The RBI material about unauthorised forex ETPs and remittances of margin to overseas exchanges/counterparties is specifically about permitted forex transactions and LRS margin remittances. It does not, by itself, determine the legal status of every simulated futures evaluation/reward contract. Do not treat a prop-firm's country list as Indian legal clearance. Before paying, remitting funds or accepting payouts, obtain advice from a qualified Indian FEMA/tax professional and retain written answers from the firm and payout provider.

Official RBI references:
- https://www.rbi.org.in/commonman/Upload/English/PressRelease/PDFs/PR166003022022.pdf
- https://systemhealth.rbi.org.in/Scripts/FAQView.aspx_Id%3D146.html

## Mandatory written confirmations before a paid evaluation

Ask using the true Indian residency, citizenship and payment details:
1. Can a resident of India purchase the exact evaluation, complete KYC and receive every advertised simulated performance reward?
2. Is India eligible for the live/real-funded transition? If not, does simulated funded status continue indefinitely and is there any payout cap or extra condition?
3. Is a Python bot written and owned by the trader permitted on the exact account model and platform?
4. Is unattended programmatic order entry available at evaluation, simulated-funded and live stages?
5. Is local Mac execution permitted? Are VPS/VPN/cloud restrictions different by stage?
6. Which exact symbols, contract months, order types, maximum order rates, news rules, daily close and drawdown/consistency rules apply?
7. Which payment and payout providers can lawfully serve an India resident, and what tax/KYC documents are required?

Never use a VPN, another person's identity/payment method, account sharing, false residency, latency exploitation or a technique to bypass a firm's rules.
