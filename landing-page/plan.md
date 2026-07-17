# Landing Page — Master Plan (Company Site)

**Goal:** sell and onboard Fleet's five AI agents with one page. A visitor should
understand what Fleet is, see the five agents, and either adopt the ones they need
or request onboarding. Every capture is attributable: *email + which agent(s) +
(optionally) company size / pain*, so the owner knows what each new customer wants.

**This folder is the complete spec.** A frontend intern should be able to build
the entire page from these four documents without asking questions.

| Doc | Contents |
| --- | --- |
| `plan.md` (this file) | Positioning, page mechanics, end-to-end flow, success criteria, build checklist |
| `design.md` | Design system, section-by-section page spec, responsive/a11y/animation, tech stack + hosting |
| `copy.md` | All final copy: headlines, product cards, pricing, FAQ, buttons — paste-ready |
| `signup-capture.md` | Form-backend comparison + recommendation, exact fields, attribution encoding, analytics |

---

## 1. Positioning & narrative

### Site concept: ONE company brand, ONE page, five agent cards

**Decision: a single-page site for Fleet with five agent cards, each with its own
adopt CTA, plus a pricing/opt-in section.** Not five mini-pages, not five separate
sites.

Why:
- Fleet's whole pitch is **a fleet you assemble** — five agents on one page lets a
  visitor self-select the combination they need, which is exactly the buying
  decision. Separate pages fragment the story and hide the bundle.
- One page = one build, one deploy, one analytics setup. Intern-sized.
- The five agents share a real story ("one production-grade platform, five
  agents") that makes the company credible rather than scattered.

**Brand: "Fleet"** — tagline concept: *a fleet of AI agents that run your back
office; add the ones you need, add more as we ship them.*
- The name lives in ONE place (a `<span class="brand">` + a JS/config constant) so
  it can be swapped in minutes if the domain requires it.
- Never lock the brand to "five" — Fleet scales past five agents as we ship them.
- Agent names (short, evocative, honest — used on cards):
  1. **Triage** — support ticket triage & resolution agent
  2. **Payable** — AP / invoice-processing agent
  3. **Prospect** — lead research & outreach agent
  4. **Follow-Through** — meeting → action agent
  5. **Redline** — contract / compliance review agent

### Honest framing (a real company, no vaporware)

**Decision: frame the page as a real company you can adopt agents from.** Exact
framing rules:

- The page presents the five agents as **available products** an SMB can opt into
  and onboard — not a roadmap to vote on. No fake "trusted by" logos, no invented
  testimonials, no fabricated user/customer counts.
- Signup = "get started / request onboarding for the agent(s) you want." What they
  get: a real conversation about wiring the agent into their stack.
- Credibility comes from **how it's engineered**, not fake social proof: a section
  on the production platform (eval gates, full tracing/audit trail,
  human-in-the-loop, Google Cloud). This is true today — the spine exists.
- The contract agent always carries the **"assist, not legal advice"** disclaimer
  (see copy.md), everywhere it appears.
- Don't overclaim specific existing customers. Position as a real, buyable company
  without inventing who already bought.

### Opt-in / bundle model

- **Per-agent pricing.** A visitor can adopt one agent, or any subset.
- **Bundle discount** when they take all five.
- The page includes a **"build your fleet" selector / pricing section** so the
  visitor assembles the combination they want, and the capture carries which
  agents they selected.
- An honest **early-customer / design-partner** launch discount MAY be offered —
  but framed as a launch offer, never tied to voting or fabricated scarcity.

---

## 2. Page mechanics (the conversion pieces, exactly)

Four pieces, layered. Every capture ends in the same pipe (`signup-capture.md`)
with a distinct `source_cta` value, so the owner knows not just *which agent* but
*which surface* converted.

### Mechanic 1 — Adopt-an-agent CTAs (primary; structures the whole page)

**What it is:** each agent is a product you can adopt. The card's primary CTA is
**"Get {Name}"** (or "Add to your plan" / "Start with {Name}").

**How it works on the page:**
- Clicking opens an inline form on the card (no redirect, no modal): email +
  optional company-size select + submit. Hidden fields: `product`,
  `source_cta=adopt`.
- The visitor can adopt more than one agent (each is a separate submission — this
  is exactly the bundle signal), or use the pricing selector to pick a combination
  in one go.

**Why it works:** the ask is concrete — "start with the agent that matches the
work you have" — and the per-agent attribution tells the owner precisely what to
onboard for each new customer.

### Mechanic 2 — Pricing / build-your-fleet selector (the opt-in model, made visible)

**What it is:** "Per-agent pricing. Take one, or take all five for a bundle
discount." A selector where the visitor checks the agents they want and sees the
combination.

**How it works on the page:**
- A dedicated pricing section after the agent grid (see design.md §Section 6):
  per-agent price, the all-five bundle discount, and a checkbox selector so the
  visitor assembles a fleet.
- CTA **"Get started"** opens a short form: email, the selected agents (carried as
  `product`), company size, and one optional free-text field — *"What's the most
  painful part of this job today?"* Hidden `source_cta=pricing`.
- An honest launch/design-partner discount may live here, framed as a real
  launch offer — never as fabricated seat scarcity. Keep any number truthful and
  static-site simple.

**Why it works:** it makes the opt-in/bundle model legible and lets high-intent
visitors self-assemble exactly what they'll buy — the richest signal on the page.

### Mechanic 3 — Time-Saved Calculator (engagement → capture)

**What it is:** a small interactive calculator: pick an agent, drag 2 sliders, see
hours and dollars reclaimed per month.

**How it works on the page:**
- One shared component with an agent tab-switcher; per-agent inputs and math are
  in design.md §Section 7 (e.g. Triage: tickets/week × minutes/ticket; Payable:
  invoices/month × minutes/invoice). Automation/deflection rates are stated as the
  agent's target/typical capability, labeled as such — product capability, not a
  guarantee.
- The **result shows instantly and ungated** (gating the number itself kills
  trust). Below the result: *"Get this estimate emailed to you + get started with
  {Name}"* → email field. Hidden fields carry `product`, `source_cta=calculator`,
  **and the slider values** — so every calculator signup tells the owner the
  visitor's actual volume (tickets/week, invoices/month…). That's qualification
  data no plain form gets.

**Why it works:** the calculator does work *for* the visitor before asking for
anything (reciprocity), personalizes the value prop with their own numbers, and
captures at the moment the pain is quantified in dollars.

### Mechanic 4 — "See a sample run" (make the product concrete, zero backend)

**What it is:** each agent card has a secondary text link — *"See a sample run →"*
— opening a modal with a **static, styled artifact** of that agent's output, drawn
from each plan.md: a triaged ticket with a cited answer and an escalation (Triage),
an invoice audit trail with a caught duplicate (Payable), a scored lead dossier
with citations (Prospect), a meeting digest with a carried-over action item
(Follow-Through), a findings table with severities and a suggested redline
(Redline). Content is in copy.md §7; rendered as styled HTML "terminal/report"
panels, not images.

**How it works:** the modal footer repeats the adopt CTA: *"Want this for your
{tickets/invoices/leads}? Get {Name}."* Every modal open fires an analytics event
`sample_open{product}` — so even non-submitting visitors leave a per-agent interest
trace.

**Why it works:** the sample shows exactly what the agent produces — concrete and
honest, clearly labeled *"Sample output — this is what {Name} produces."* It also
measures depth of interest per agent independent of email submission.

### CTA structure decision: per-agent micro-CTAs, one global fallback

- **Every primary CTA carries an agent** (adopt / pricing / calculator). This
  maximizes attribution — the owner learns what each customer wants.
- **One global fallback CTA** in the final banner + footer: *"Not sure which? Talk
  to us / get the overview."* → `product=all`, `source_cta=global`. It catches
  generally-interested visitors without polluting per-agent signal.
- Explicitly rejected: a single global "contact us" as the only primary (destroys
  attribution).

---

## 3. Intent capture — summary of recommendation

Full comparison and spec in `signup-capture.md`. The decision:

- **No custom backend.** Static site + **Formspree** (one form endpoint, free
  tier): native HTML forms styled to match the design, per-agent attribution via
  hidden fields, email notification to the owner per signup, CSV export.
- **Fallback: Tally.so** (free unlimited responses + Google Sheets sync) if
  Formspree's free 50 submissions/month is exceeded — being over 50/month means
  the page is working.
- The GCP Firestore/Cloud Function option is deliberately deferred: same HTML
  forms, new `action` URL when there's reason to own the endpoint.
- **Analytics: Google Analytics 4** (free) with custom events + scroll depth, so
  intent is measurable even without a submit.

## 4. Design & build — summary of recommendation

Full spec in `design.md`. The decisions:

- **One static `index.html` + Tailwind CSS + ~150 lines vanilla JS.** No
  framework, no build step beyond the Tailwind CLI. Hosted on **GitHub Pages**
  (repo already lives on GitHub; free; custom domain when ready).
- Style: clean light "credible SaaS" base, ink-on-warm-white, indigo primary
  accent, **five per-agent accent hues** used consistently across cards, pricing
  selector, and calculator tabs (color = attribution made visible).
- Imagery: **no stock AI art, no fake screenshots.** Diagram-style pipeline chips
  on cards + dark terminal/report-styled sample panels, all HTML/CSS.
- Fonts: Space Grotesk (display) + Inter (body) + JetBrains Mono (samples).

---

## 5. End-to-end flow & measurement

### The journey

```
Visitor lands (LinkedIn post / community link / DM, with ?utm_source=…)
   │
   ▼
Hero: "A fleet of AI agents that run your back office." → primary CTA scrolls to grid
   │
   ├── Reads an agent card → clicks "Get {Name}"
   │       → inline form (email [+ company size]) → POST to Formspree
   │
   ├── Opens "See a sample run" → modal artifact → adopt CTA  (event: sample_open)
   │
   ├── Uses calculator → sees $/month → emails estimate       (source: calculator,
   │                                                            + volume data)
   ├── Pricing selector → picks a combination → "Get started"  (source: pricing,
   │                                                            + agents + pain)
   └── Unsure → final banner "talk to us / overview"           (product: all)
   │
   ▼
Formspree: stores submission, EMAILS THE OWNER instantly per signup
   │
   ▼
Owner: replies to onboard the requested agent(s); exports CSV weekly for a simple
tally; checks GA4 funnel (views → CTA clicks → submits, per agent)
```

What the owner sees, concretely: **(a)** one email per signup with all fields,
**(b)** the Formspree dashboard/CSV of all submissions with agent + source +
qualification fields, **(c)** GA4 per-agent event counts. No dashboards to build.

### Success criteria (a page that sells)

The page's job is to turn a qualified visitor into an onboarding conversation.

- **Conversion:** track submits / unique visitors per agent. A healthy page
  converts interested traffic into per-agent adopt/pricing/calculator signups.
- **Weak-page trigger:** if after ~500 visitors overall conversion (any submit /
  unique visitors) is **< 2%**, the page — not the agents — is the problem: revise
  hooks/copy before concluding anything.
- **Per-agent read:** an agent with high `sample_open` but low submits is
  interesting but has a weak card offer → adjust that card's copy.
- Deduplicate by email per agent when tallying; the same email across different
  agents is legitimate multi-agent (bundle) interest — note it.

### Owner ops cadence (post-launch, 15 min/week)

1. Export Formspree CSV → paste into the tally sheet.
2. Reply personally to every onboarding request within 24h.
3. Update any pricing/launch-offer copy in `index.html` if it changes.
4. Post updates wherever traffic comes from (new agents shipped, etc.).

---

## 6. Build checklist for the intern (ordered)

Work top-to-bottom; each step has a verify gate. Total estimate: 3–5 days.

1. **Read all four docs in this folder**, then skim the five agent `plan.md`s only
   if copy context is unclear. → verify: can state each agent's one-liner from
   memory.
2. **Scaffold**: `landing-page/site/` with `index.html`, `input.css`, Tailwind CLI
   build (`design.md` §8), `main.js`. → verify: styled hello page builds and opens
   locally.
3. **Design tokens**: colors, fonts, spacing from `design.md` §2 as Tailwind
   config + CSS variables. → verify: swatch test page matches hex values.
4. **Static sections in order** — header, hero, value strip, agent grid (cards
   only, no forms yet), how-it-works, pricing, credibility, FAQ, footer — using
   final copy from `copy.md`. → verify: full page reads end-to-end, no placeholder
   text ("lorem" grep returns nothing).
5. **Value strip** (design.md §Section 3) renders the "build your fleet" framing.
   → verify: matches copy.md.
6. **Formspree setup**: owner creates the account/endpoint (10 min, see
   signup-capture.md §4); intern wires the adopt form on ONE card. → verify: a real
   test submission arrives in owner's email with correct `product` and `source_cta`.
7. **Roll forms out** to all five cards + pricing section + global banner. →
   verify: one test submission per form; every one attributes correctly.
8. **Sample-run modals** (Mechanic 4) with the five artifacts from copy.md §7. →
   verify: keyboard-closable, scrollable on mobile, CTA inside works.
9. **Calculator** (Mechanic 3) per design.md §Section 7. → verify: math matches the
   worked examples; hidden fields carry slider values into the submission email.
10. **GA4**: add the tag + the events from signup-capture.md §6. → verify: events
    appear in GA4 DebugView for each CTA.
11. **Responsive + a11y pass** per design.md §6–7. → verify: Lighthouse ≥ 90
    accessibility & performance on mobile; page usable at 360px width; keyboard-only
    run-through completes an adopt.
12. **Spam guard**: honeypot field + Formspree reCAPTCHA setting. → verify:
    honeypot-filled submission is dropped.
13. **Deploy to GitHub Pages** (design.md §8). → verify: live URL loads, a live-site
    test submission arrives, GA4 shows the visit.
14. **Handoff note to owner**: live URL, where signups land, how to edit pricing/
    launch-offer copy, the weekly cadence (§5). → verify: owner completes one copy
    edit unassisted.
