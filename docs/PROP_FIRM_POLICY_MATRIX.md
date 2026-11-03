# Prop-firm automation and rules research

Research snapshot: 4 November 2026. This is a moving policy snapshot, not legal advice or a recommendation to buy an evaluation. The firm's current agreement, dashboard terms and written support response for the exact account model take precedence.

## Shortlist summary

| Firm | Published automation position | Main issue for our use case | Current assessment |
|---|---|---|---|
| MyFundedFutures (MFFU) | Personalised automated strategies allowed; HFT and simulated-fill exploitation prohibited; live automation must follow CME guidelines | Exact custom-code/API route for evaluation and sim-funded stages is not documented clearly. Standard individual Tradovate API docs require a live account with >$1,000 equity and paid API access; confirm whether MFFU's partner/account integration changes this | Serious candidate; clearest published support for personal automation including live, subject to API path and India confirmation |
| FundedNext Futures | Bots/EAs allowed on Challenge and FundedNext Account through a platform integration connecting to Tradovate | Bot setup support not provided; exact Python/API route and India payout/live-stage details need written confirmation | Serious candidate; clear challenge-to-funded bot wording and all six micro symbols appear on allowed list |
| Tradeify | Personally owned automation allowed subject to agreement; HFT prohibited | Bot must be exclusively used on Tradeify; Tradovate API is reported as available only on Live Funded, not evaluation/sim-funded stage | Lower fit for reusable, fully automated system |
| Topstep | Custom bots allowed through TopstepX/ProjectX API; HFT prohibited | API costs $29/month; VPS/VPN/remote-server order execution prohibited; API unavailable on Live Funded | Poor fit for zero-budget and end-to-end live automation |
| TradeDay | Agreement prohibits bots/ATS purchased from third parties or shared between users; platform rules prohibit exploitative/disruptive systems | Wording does not clearly approve a self-written private bot; firm discretion is broad. Written approval required | Do not assume a custom bot is allowed |
| Apex Trader Funding | Automated order entry/management is prohibited on PA/Live; manual order submission required | Direct conflict with fully automated execution | Exclude |

## 1. MyFundedFutures (MFFU)

Official sources:
- Automation and fair-play rules: https://help.myfundedfutures.com/en/articles/8444599-fair-play-and-prohibited-trading-practices
- Restricted countries: https://help.myfundedfutures.com/en/articles/8229993-restricted-countries-policy
- KYC/AML: https://help.myfundedfutures.com/en/articles/9717961-kyc-aml-policies
- Supported instruments, fees and trading hours: https://help.myfundedfutures.com/en/articles/9735811-futures-instrument-list
- Evaluation parameters: https://help.myfundedfutures.com/en/articles/11802636-traders-evaluation-simplified
- Payout route: https://help.myfundedfutures.com/en/articles/11542406-guide-to-your-first-payout-quick-and-easy-process

Current published points:
- MFFU says HFT is not allowed. Traders may use automated strategies tailored to their own settings if they do not exploit favourable fills in the simulated environment. It says live-account automated trading must abide by CME guidelines.
- Its instrument list currently includes all our main micro candidates: MES, MNQ, M2K, MYM, MGC and MCL.
- Published round-trip cost figures in its instrument table (verify current model and platform before use): MES $1.90, MNQ $1.90, M2K $1.90, MYM $1.90, MGC $2.20, MCL $1.16. These are MFFU's listed total-cost figures, not a promise of the final cost for every account or platform.
- MFFU's instrument page states trading hours 6:00 PM ET to 4:10 PM ET. Its futures-instrument table also lists the Globex sessions and metal micro contract caps, which vary by account size.
- Example Flex 25K/50K evaluation rules show EOD maximum loss of $1,000/$2,000, no daily-loss limit, 50% evaluation consistency and 2 minimum trading days. This is only one plan family; Rapid/Pro/Flex/Builder and add-ons differ. Load the purchased plan's exact limits.
- Its restricted-country list does not include India in the current snapshot. KYC requires proof of identity and address. Payout guide uses Rise; Rise's September 2026 local-currency withdrawal list includes India/INR. None of these facts guarantees that a particular Indian resident will pass KYC, receive a payout, or meet Indian law.
- The unresolved technical issue is the exact API route. MFFU policy allows automation, but its help pages do not clearly promise user-level programmatic API order entry at every evaluation and sim-funded stage. Tradovate's direct individual API documentation says API access requires a live account with more than $1,000 equity and an API Access subscription. That may not describe an MFFU partner integration, so ask MFFU and Tradovate in writing before designing around it.
  Tradovate source: https://api.tradovate.com/

## 2. FundedNext Futures

Official sources:
- Bot/EA rules: https://fundednext.com/general-rules/futures/what-is-allowed
- Tradable instruments: https://helpfutures.fundednext.com/en/articles/17225740-which-symbols-instruments-can-i-trade-on-fundednext-futures
- Trading hours: https://helpfutures.fundednext.com/en/articles/17225754-what-are-the-trading-hours-in-fundednext-futures
- Country and live eligibility: https://helpfutures.fundednext.com/en/articles/17228971-are-any-countries-restricted-on-fundednext-futures
- Challenge terms: https://fundednext.com/apidocs/futures-challenge-terms
- FAQ: https://helpfutures.fundednext.com/en/articles/17225788-fundednext-futures-most-frequently-asked-questions

Current published points:
- EAs/bots are allowed on Challenge and FundedNext accounts through a platform integration connecting to Tradovate. FundedNext does not provide bot setup, configuration or troubleshooting support.
- Its currently published tradable-symbol list includes MES, MNQ, M2K, MYM, MGC and MCL.
- Overnight/weekend holding is prohibited; positions must be closed by 3:10 PM CT. This must be encoded in the risk/session layer.
- The rules prohibit exploiting latency, stale or erroneous data, and repeated ultra-short entries/exits. The terms describe repeated entries/exits within five ticks or without a reasonable 15–20 second hold as prohibited.
- Account model/add-on terms define different drawdown, consistency and contract limits. No universal rule profile should be assumed.
- India does not appear on the currently published purchase-restricted list; the current live-eligibility page still reserves review by its Risk Desk. That is not guaranteed approval or payout access for an Indian resident.
- Confirm the actual Python order-entry/API path and permissions for Challenge and FundedNext Account before we implement a connector.

## 3. Tradeify

Official sources:
- Risk/compliance FAQ: https://help.tradeify.co/en/articles/17069653-risk-compliance-guidelines-faq
- Restricted countries: https://help.tradeify.co/en/articles/10495888-rules-restricted-countries
- Supported products: https://help.tradeify.co/en/articles/10468222-rules-supported-trading-products-assets
- Funded Trader Agreement: https://tradeify.co/funded-trader-agreement

Current published points:
- The October 2026 agreement requires the trader to prove sole ownership and exclusive use of a bot and prohibits use of that bot across multiple firms. HFT bots are prohibited.
- The official product list supports the shortlisted micros.
- Help documentation says Tradovate API access is available only on Live Funded accounts, not evaluation/sim-funded stages. Verify current plan and platform before any integration.
- India is not in the current restricted-country list reviewed, but live eligibility is a separate decision. Do not infer payout/live approval from country-list omission.

## 4. Topstep

Official sources:
- API rules and pricing: https://help.topstep.com/en/articles/11187768-topstepx-api-access
- Country eligibility: https://help.topstep.com/en/articles/8284116-am-i-eligible-to-trade-with-topstep

Current published points:
- TopstepX/ProjectX API permits custom bots subject to normal rules and HFT prohibition.
- API list price is $29/month (discounts may apply).
- Trading activity must originate from the personal device. VPS/VPN/remote-server order execution is prohibited.
- ProjectX API is unavailable on Live Funded accounts.
- This is a poor fit for our zero-budget, fully automated path across all account stages.

## 5. TradeDay

Official source:
- Terms: https://www.tradeday.com/terms-and-conditions
- Payment/payout details: https://tradeday.freshdesk.com/en/support/solutions/articles/103000008898-what-are-the-payment-methods-for-my-trading-profits-

Current published points:
- Its terms prohibit use of bots/ATS purchased from third parties or shared between multiple users. It also reserves broad discretion over disruptive or non-viable strategies.
- This wording may leave room for a trader's private self-written bot, but does not explicitly give blanket approval to every custom automated strategy. Obtain written approval before use.

## 6. Apex Trader Funding

Official sources:
- User agreement: https://sim.apextraderfunding.com/legal/user-agreement
- Automation/PA compliance: https://apextraderfunding.com/help-center/performance-accounts-pa-compliance/
- Live program FAQ: https://apextraderfunding.com/help-center/getting-started/apex-live-prop-trading-program-faq/

Current published points:
- Its manual-order-submission requirement says the user must personally input and confirm each order; pre-programmed systems that auto-execute or modify orders are prohibited.
- Its PA/Live compliance page explicitly says automated trading systems and AI/autobots are prohibited.
- Exclude Apex for this fully automated project.

## Provisional decision

**Do not select or purchase a prop-firm evaluation yet.** MFFU and FundedNext are the two strongest policy candidates to investigate next:

- MFFU has the clearest public statement permitting personalised automated strategies and applying a CME-guidelines condition to live automation. The customer API/order-entry path at evaluation and sim-funded stages is not yet confirmed.
- FundedNext clearly states that bots are allowed on Challenge and FundedNext accounts through a Tradovate-connected integration, lists the candidate micros and has an enforceable mandatory daily close. Its precise API route and India payout/live eligibility still need confirmation.

The system therefore remains broker/firm neutral. We will not hard-code either firm's rules or API. No paid challenge or API subscription will be bought during development.

## India legal, KYC and payout gate

- RBI guidance prohibits LRS remittances for margin/margin calls to overseas exchanges/counterparties and covers unauthorised online forex ETPs. That specific guidance does not, by itself, settle the legal treatment of every simulated futures evaluation fee, simulated performance reward or contractor-style payout.
- MFFU's current restricted-country list does not name India; it requires KYC and uses Rise for payouts. Rise currently lists India/INR local withdrawals. A supported payout rail is not legal clearance and does not guarantee the prop firm will approve a given Indian account.
- Before any purchase, overseas payment, payout or live transition, get written responses from the firm and payment provider and obtain advice from a qualified Indian FEMA/tax professional or authorised dealer bank.

RBI references:
- https://systemhealth.rbi.org.in/Scripts/FAQDisplay.aspx_Id%3D146.html
- https://systemhealth.rbi.org.in/Scripts/BS_ViewMasDirections.aspx_id%3D10192%283%29.html

## Mandatory questions for MFFU and FundedNext support

Send these questions using your truthful Indian residency, citizenship and payout details:
1. Is an Indian resident eligible to purchase the exact evaluation, complete KYC, trade a simulated-funded account, receive every eligible payout, and transition to any live account?
2. Is a custom Python bot written and owned by the trader explicitly permitted on this exact account model?
3. Can the bot place and manage orders programmatically during evaluation and sim-funded stages, not merely manage brackets after a manual entry?
4. Which exact API or platform integration is supported, and does it require a paid API add-on, funded-live account, Windows PC, subscription, or minimum real-account balance?
5. Is local execution on the trader's Mac permitted? Are VPS/VPN/cloud restrictions different by stage?
6. Which symbols, contract limits, order types, order-rate limits, news rules, mandatory flat time, drawdown calculation and consistency rules apply to this plan?
7. Which payout provider handles Indian-resident payouts, what KYC and documents are required, and are INR bank withdrawals supported for this exact payout account?

Do not use a VPN, another person's identity/payment method, account sharing, false residency, latency exploitation or any technique to bypass a firm's rules.
