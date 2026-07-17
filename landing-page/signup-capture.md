# Intent Capture — Backend Recommendation, Fields, Attribution, Analytics

Answers the owner's question directly: **no, you do not need a backend.**
A static site + a form service captures every onboarding request this page
needs. Below: the comparison, the one recommendation, the exact field spec, and
the analytics plan.

---

## 1. Options compared

Criteria: cost, inline UX (own-styled form beats iframe beats redirect),
product attribution, spam protection, owner visibility (notification +
export), and setup effort.

| Option | Cost | UX | Attribution | Spam | Owner visibility | Effort | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Formspree** (1 endpoint) | Free 50 subs/mo; $10/mo for 1,000 | **Native HTML form, fully own-styled, AJAX inline success** | Trivial — `<input type="hidden">` per form | Honeypot + optional reCAPTCHA, built-in filtering | Email per submission + dashboard + CSV export | ~30 min | **Recommended** |
| **Tally.so** | Free, unlimited responses | Iframe embed — good but styling never fully matches; heavier | Hidden fields via URL params | Built-in captcha | Email notifications + free Google Sheets sync | ~45 min | **Fallback** |
| Google Forms | Free, unlimited | Worst: redirect or ugly iframe; kills conversion on a designed page | Prefill URL params — clunky | Weak | Native Sheets | ~20 min | No — UX cost too high for a conversion page |
| Typeform | Free tier: ~10 responses/mo | Nice, but modal/iframe | Hidden fields | OK | Integrations mostly paid | ~45 min | No — free tier is unusable for validation volume |
| Netlify Forms | Free 100 subs/mo | Native HTML | Hidden fields | Honeypot/Akismet | Dashboard + notifications | ~20 min | No — forces Netlify hosting; we chose GitHub Pages |
| Buttondown / Mailchimp waitlist | Free tiers exist | Embed forms, list-centric | Tags per product — awkward across 8 entry points | OK | List dashboard | ~1 h | No — built for newsletters, not multi-CTA attribution; adds a second tool later anyway |
| Firestore + Cloud Function (GCP) | ~Free at this volume | Perfect (own endpoint) | Perfect | You build it (rate limit, honeypot, abuse) | You build it (BigQuery/Sheets export, alerting) | 1–2 days + IAM/CORS/deploy upkeep | No **for v1** — real engineering spend before any demand signal exists. This is the post-validation upgrade path, and the migration is trivial (same HTML forms, new `action` URL) |

## 2. The recommendation

**Primary: Formspree, one form endpoint for the entire site.**

- All 8 capture points (5 card adopt forms, pricing form, calculator form,
  global banner form, plus modal footer forms reusing the card pipe) POST to
  the **same endpoint**; hidden fields distinguish agent and surface. One
  endpoint keeps the free plan's form-count limits irrelevant and puts every
  signup in one export.
- Submit via `fetch()` (AJAX) so the visitor never leaves the page; Formspree
  returns JSON; render the inline success line (copy.md §3).
- Owner gets an **email per signup** (instant "someone wants Payable" dopamine
  + zero-dashboard visibility) and exports **CSV weekly** for the tally sheet.

**Cost trigger, decided in advance:** free tier = 50 submissions/month. If
exceeded — which equals validation working — either pay $10/mo (recommended;
one lunch) or execute the fallback.

**Fallback: Tally.so** — free unlimited responses, hidden-field support, free
Google Sheets sync. Cost: iframe embeds replace the native forms (visual
match degrades slightly). Only migrate if volume > 50/mo AND owner won't pay.

**Later (post-validation, optional):** tiny Cloud Function → Firestore on the
existing GCP account. Same form markup, swap the `action` URL. Do not build
now.

## 3. Field spec (exact)

Every submission carries these fields. Names are final — the tally sheet and
GA4 events key off them.

| Field | Type | Required | Values / notes |
| --- | --- | --- | --- |
| `email` | visible input, `type=email` | yes | native validation + `required` |
| `product` | hidden | yes | `triage \| payable \| prospect \| followthrough \| redline \| all`; the pricing form carries the selected combination (comma-separated agent ids, or `all` when every agent is checked) |
| `source_cta` | hidden | yes | `adopt \| pricing \| calculator \| sample_modal \| global` |
| `company_size` | visible select | no | `solo \| 2-10 \| 11-50 \| 51-200 \| 200+` |
| `pain` | visible textarea | no (pricing form only) | max 280 chars |
| `calc_a`, `calc_b`, `calc_hours` | hidden | calculator form only | raw slider values + computed hours/mo |
| `utm_source`, `utm_campaign` | hidden | auto | JS copies them from the page URL query string on load into every form — attributes signups to the traffic post/channel |
| `_gotcha` | hidden text input (honeypot) | — | Formspree drops submissions where it's filled; also enable reCAPTCHA in Formspree settings |
| `_subject` | hidden | — | set per-form, e.g. `Get started: payable (calculator)` so the owner's inbox is scannable |

**Attribution encoding decision:** hidden fields on distinct forms — NOT
query params, NOT separate endpoints. Each of the 8 forms is its own `<form>`
element with `product`/`source_cta` baked in at build time; zero JS needed
for attribution correctness, and it can't be lost to a dropped redirect.

## 4. Setup steps (owner: ~10 min; intern wires the rest)

1. Owner creates a free Formspree account with the address that should
   receive signup notifications; creates one form; copies the endpoint URL
   (`https://formspree.io/f/XXXXXXXX`).
2. Owner enables reCAPTCHA + email notifications in the form's settings.
3. Intern puts the endpoint in one constant in `main.js`; all forms read it.
4. Test matrix before launch: one submission from each of the 8 forms →
   verify each arrives with correct `product` + `source_cta` + `_subject`;
   one honeypot-filled POST → verify it's dropped.

## 5. Owner's tally sheet (weekly, manual, 10 min)

A Google Sheet with two tabs, built once from the first CSV export:

- **Raw**: paste the Formspree CSV export weekly (columns = §3 fields +
  timestamp).
- **Requests**: per agent — adopt signups (`source_cta=adopt` + `sample_modal`),
  calculator signups, pricing/get-started requests, and total unique requests,
  deduped by email-within-agent. This tells the owner which agents to onboard
  and where interest is concentrated.

## 6. Analytics (measure intent even without a submit)

**Decision: Google Analytics 4** — free, event-based, no volume limits.
(Plausible is nicer but paid; Cloudflare Web Analytics is free but can't do
custom event parameters well. GA4's clunky UI is acceptable at this scale.)

Single `gtag.js` snippet in `<head>`. Events (name → params):

| Event | Fired when | Params |
| --- | --- | --- |
| `cta_click` | any adopt/pricing/calculator/global button clicked | `product`, `source_cta` |
| `form_submit_ok` | Formspree AJAX success | `product`, `source_cta` |
| `sample_open` | sample-run modal opened | `product` |
| `calc_used` | first slider interaction per product per session | `product` |
| `calc_result_emailed` | calculator email submitted | `product`, `calc_hours` |
| `scroll_depth` | 25 / 50 / 75 / 90 % (one IntersectionObserver on markers) | `percent` |

Funnel the owner reads in GA4 (per product): page views → `sample_open` /
`calc_used` (interest) → `cta_click` (intent) → `form_submit_ok` (capture).
A product with high `sample_open` but low submits = interesting but weak
offer → adjust that card's copy, not the whole page.

Consent note: GA4 + a form is lightweight enough to run with the privacy
paragraph in the footer (copy.md §9); no cookie banner for v1 US-focused
traffic. If EU traffic becomes a real channel, add a minimal consent notice
then — not a v1 task.
