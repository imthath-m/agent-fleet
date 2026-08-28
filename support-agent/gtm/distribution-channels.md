# Triage — where it can actually be listed and sold

Research date: 2026-08-28. Scope: the support agent (Triage) only.

## The overriding finding

Almost every channel with real buyer volume requires a working integration with
the host platform *first*. Triage currently runs on in-memory fakes with no
helpdesk integration, so **the marketplace decision is the integration-roadmap
decision**.

Second finding: every major helpdesk now ships a first-party AI agent (Zendesk
AI Agents/Forethought, Intercom Fin, Freshworks Freddy, Gorgias AI Agent). We
would be the third-party alternative in each — a real but contested position
(eesel AI, Ada, Stylo, DigitalGenius all occupy it today).

## Comparison

| Channel | Lift to list | Cost / rev share | Time to list | SMB volume | Fit / crowding | Verdict |
|---|---|---|---|---|---|---|
| Zendesk Marketplace | High: OAuth global tokens + AI-agent reqs (all channels, dedicated bot account) | Free; paid apps billed via your Stripe | 1–3 wk review | High (~58% of customers install apps) | Natural fit; ~253 AI/bot apps + first-party AI | **Do** — integration #1 or #2 |
| Freshworks Marketplace (Freshdesk) | Medium: Freshworks App SDK + security review | Free; 80/20 (we keep 80%) | Few weeks | High, SMB-heavy | Natural fit, less crowded | **Do** — best SMB match |
| Gorgias App Store | Medium: OAuth2 app | Free | ~2 wk | Modest but exact ICP (ecom SMB) | Good; first-party AI competitor | **Do** if we go e-commerce |
| HubSpot App Marketplace | Medium: OAuth + 3 live installs before listing | Free | Weeks + install gate | High | OK; Breeze competes | Later |
| Intercom App Store | Medium | Free | Weeks | High | Poor — Fin's home turf | Skip |
| Zoho Marketplace (Zoho Desk) | Medium (Sigma extension) | Free; own pricing | ~5–7 working days | Medium, SMB | Decent | Optional |
| Help Scout / Front / Crisp / Kustomer | Low | Free | Days–weeks | Small | Fine | Cheap adds |
| Salesforce AgentExchange | Very high (SFDC-native managed package) | $999/security review + $150/yr + 15% | 5–9 months | Enterprise | Closed to us | Skip |
| Google Cloud AI Agent Marketplace | Low–medium for us (A2A agent card; Partner Advantage Build; "enterprise-ready" bar) | 3%, tiered to 1.5% | Weeks–months | Low for SMB (Gemini Enterprise buyers) | Perfect stack fit, wrong buyer | **Do** for strategy, not volume |
| AWS Marketplace (AI Agents & Tools) | Medium (metering/entitlement APIs, or MCP container) | 3% | Weeks | Low for SMB | OK | Later |
| Microsoft AppSource / M365 Agent Store | High (Copilot declarative agent rebuild + MAICPP) | Marketplace fees | Months | Medium | Different product shape | Skip for now |
| Slack Marketplace | Medium (Slack app + 5 active workspaces as of 2026-08-11) | Free | Weeks | Medium | Good policy fit — their AI rules require HITL on consequential decisions | v2 |
| Atlassian Marketplace (JSM/Forge) | High (Forge rebuild) | 0% on first $1M Forge revenue from 2026-01-01 | Months | ITSM, not CX | Mismatch | Skip |
| Shopify App Store | High (GDPR webhooks, GraphQL Billing API, Polaris) | 0% to $1M lifetime, then 15% | Weeks | Very high | Crowded; buyers want a full inbox, not a triage layer | Only paired with a helpdesk integration |
| Wix App Market | Medium | 100% year 1, then 80% (−2.5% txn) | Weeks | Real SMB volume | Dominated by Wix's own + chat apps | Optional |
| BigCommerce / WooCommerce / Squarespace | Medium–high | Woo 70/30; Squarespace curated | Weeks | Low | — | Skip |
| Zapier | Medium (needs a public API) | Free | 90-day beta; 50 active users + 10 templates to fully launch | Long-tail SEO | Fine | v2 |
| Make / n8n / Pipedream | Low–medium | Free | Days–weeks | Developer traffic | Cheap credibility | Optional |
| G2 / Capterra / GetApp / TrustRadius / SaaSHub | Trivial | Free profiles (Capterra PPC from $2/click, $500/mo floor; G2 paid ~$2.3k–$30k+/yr) | Days | High intent — but needs reviews | Crowded category pages | **Do now** |
| Product Hunt | Low | Free | One launch day | ~50–300 signups + backlink | Saturated with AI launches | Once, when a trial exists |
| AppSumo | Low | ~60/40 in their favour on an 80–95% discounted lifetime deal | Negotiated | High deal-hunters | Lifetime pricing vs per-ticket inference COGS = negative margin forever | Avoid |
| Pax8 / MSP channel | High + waitlist | Negotiated | Months | High (via MSPs) | Curated, favours proven vendors | Revisit ~$500k ARR |

## Priorities for a pre-customer team

1. **Freshdesk + Zendesk.** We have to build a real helpdesk connector anyway to
   get off the in-memory fakes; the marketplace listing then comes nearly free.
   Freshdesk is the purer SMB audience, less crowded, and pays 80/20. Zendesk is
   the bigger pool. Pick **Gorgias instead of Freshdesk** if we commit to
   e-commerce SMBs — the refund / order-lookup actions are strongest there.
2. **Free discovery layer, now.** G2, Capterra, TrustRadius, SaaSHub profiles
   cost nothing and seed the review flywheel. One Product Hunt launch once a
   self-serve trial exists.
3. **Google Cloud AI Agent Marketplace**, in parallel. Our Vertex/ADK stack means
   the technical lift (A2A agent card in Cloud Storage) is the smallest of any
   team's. Payoff is the Gemini Enterprise Agent Gallery, the "Google Cloud Ready
   – Gemini Enterprise" badge and co-sell — credibility more than SMB volume. The
   gate to clear is their "production-ready, defined sales motion, real support"
   requirement; no alpha/beta.

## Effectively closed to us today

- **Salesforce AgentExchange** — cost, 5–9 month timeline, platform rebuild.
- **Pax8 / MSP channels** — curated, want traction and channel-ready billing.
- **Microsoft Agent Store** — product-shape mismatch (Copilot declarative agent).
- **HubSpot certification** — 60 active installs + 6 months listed.
- **Zapier full launch** — 50 active users.
- **Squarespace Extensions** — curated.
- **AppSumo** — open, but economically hostile to an inference-priced product.

## Key sources

- Zendesk: <https://developer.zendesk.com/documentation/marketplace/publishing-to-the-marketplace/submit-your-app/>, AI-agent app requirements <https://developer.zendesk.com/documentation/marketplace/building-a-marketplace-app/build-and-test-your-app/>
- Freshworks Paid Apps Program: <https://developers.freshworks.com/docs/getting-started/paid-apps-program/>
- Gorgias developers: <https://developers.gorgias.com/> · app partners <https://www.gorgias.com/app-partners>
- Intercom App Partner Program: <https://www.intercom.com/app-partner-program>
- HubSpot certification requirements: <https://developers.hubspot.com/docs/apps/developer-platform/list-apps/apply-for-certification/certification-requirements>
- Shopify revenue share: <https://shopify.dev/docs/apps/launch/distribution/revenue-share>
- Wix monetization: <https://dev.wix.com/docs/build-apps/launch-your-app/pricing-and-billing/about-monetizing-your-app>
- Google Cloud, offering AI agents: <https://docs.cloud.google.com/marketplace/docs/partners/ai-agents> · partner requirements <https://docs.cloud.google.com/marketplace/docs/partners/get-started>
- AWS AI Agents & Tools: <https://aws.amazon.com/about-aws/whats-new/2025/07/ai-agents-tools-aws-marketplace>
- Microsoft AI app/agent publishing: <https://learn.microsoft.com/en-us/partner-center/marketplace-offers/artificial-intelligence-app-agent-publish-release>
- Slack Marketplace guidelines: <https://docs.slack.dev/slack-marketplace/slack-marketplace-app-guidelines-and-requirements/>
- Atlassian 2026 revenue share: <https://www.atlassian.com/blog/development/updates-to-marketplace-revenue-share-2026>
- Zapier publishing requirements: <https://docs.zapier.com/platform/publish/integration-publishing-requirements>
- Salesforce security review 2026: <https://appnigma.ai/blogs/salesforce-security-review-guide-2026/>
- Pax8 vendor application: <https://www.pax8.com/en-us/marketplace/vendors/>
