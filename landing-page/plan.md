# Landing Page — Master Plan (Demand Validation)

**Goal:** validate demand for five pre-launch AI agent products with one page.
Every visitor action must produce an attributable signal: *email + which product
+ (optionally) company size / pain*. Whichever product wins gets built first.

**This folder is the complete spec.** A frontend intern should be able to build
the entire page from these four documents without asking questions.

| Doc | Contents |
| --- | --- |
| `plan.md` (this file) | Positioning, conversion hooks, end-to-end flow, success criteria, build checklist |
| `design.md` | Design system, section-by-section page spec, responsive/a11y/animation, tech stack + hosting |
| `copy.md` | All final copy: headlines, product cards, FAQ, buttons — paste-ready |
| `signup-capture.md` | Form-backend comparison + recommendation, exact fields, attribution encoding, analytics |

---

## 1. Positioning & narrative

### Site concept: ONE umbrella brand, ONE page, five product cards

**Decision: a single-page umbrella site with five product cards, each with its
own CTA.** Not five mini-pages, not five separate sites.

Why:
- Demand validation needs **comparative signal** — five products on one page
  lets a visitor self-select, which is exactly the data we want. Separate pages
  fragment traffic and make comparison impossible.
- One page = one build, one deploy, one analytics setup. Intern-sized.
- SEO/ads aren't the channel yet (traffic will be founder-driven: communities,
  LinkedIn, direct outreach), so per-product landing pages buy nothing.
- The five products share a real story ("one production-grade platform, five
  agents"), which makes the umbrella brand credible rather than scattered.

**Umbrella working brand: "Fivefold"** — tagline *"Five AI agents. Built like
production software. You pick what ships first."*
- The name is a placeholder decision so the intern isn't blocked. Put it in ONE
  place (a `<span class="brand">` + a JS/config constant) so it can be swapped
  in minutes if the owner picks another name or the domain is taken.
- Product working names (short, evocative, honest — used on cards):
  1. **Triage** — support ticket triage & resolution agent
  2. **Payable** — AP / invoice-processing agent
  3. **Prospect** — lead research & outreach agent
  4. **Follow-Through** — meeting → action agent
  5. **Redline** — contract / compliance review agent

### Honest pre-launch framing

**Decision: frame the page as a public build-queue vote + founding-user
program.** Exact framing rules:

- The page says plainly, above the fold and in the FAQ: **"These agents are in
  development. We build the one you vote for first."** No fake "trusted by"
  logos, no invented testimonials, no fabricated user counts.
- Signup = "Vote + join the founding list for that agent." What they get:
  build-progress updates, first access, founding-user pricing.
- Credibility comes from **how it's engineered**, not fake social proof: a
  section on the production platform (eval gates, full tracing/audit trail,
  human-in-the-loop, Google Cloud). This is true today — the spine exists.
- The contract agent always carries the **"assist, not legal advice"**
  disclaimer (see copy.md), even pre-launch.
- Never use the word "customers." Use "founding users" / "design partners."

This framing turns pre-launch from a weakness into the hook: visitors get
agency ("you decide what exists"), which no shipped product can offer.

---

## 2. Conversion hooks (the mechanics, exactly)

Four mechanics, layered. Every one ends in the same capture pipe
(`signup-capture.md`) with a distinct `source_cta` value, so we know not just
*which product* but *which hook* converted.

### Hook 1 — The Build-Queue Vote (primary; structures the whole page)

**What it is:** "We're building five agents. Vote for the one you need — the
winner gets built first, and voters get it first."

**How it works on the page:**
- Each product card's primary CTA is **"Vote for {Name}"**. Clicking opens an
  inline email form on the card (no redirect, no modal): email + optional
  company-size select + submit. Hidden fields: `product`, `source_cta=vote`.
- A **leaderboard strip** near the hero shows the five products as horizontal
  bars in their accent colors. Until total votes ≥ 25, bars show no numbers —
  label reads *"Early voting open — standings published weekly."* After 25,
  the owner updates a small JSON constant in the page weekly with real counts
  (static site: no live tally, and that's fine — weekly cadence creates a
  reason to revisit). **Never display invented numbers.**
- Voting for more than one product is allowed (each is a separate submission —
  more signal, and multi-votes reveal bundle demand).

**Why it converts:** signup stops being "give us your email for vague updates"
and becomes **agency** — the visitor's action visibly changes what gets built.
Voting is also a lighter psychological ask than "join a waitlist" while
producing the identical data (email + product). It's the honest version of a
fake-door test: the door is real, it just opens later.

### Hook 2 — Founding Partner slots (scarcity + depth of signal)

**What it is:** "The first 10 companies per agent become design partners:
50% off for the first year, direct roadmap input, white-glove onboarding, and
we build your integrations first."

**How it works on the page:**
- A dedicated section after the product grid (see design.md §Section 6) with
  the perk list and a per-product slot counter ("10 of 10 slots open" —
  manually updated, must always reflect reality; it starts full and that's
  honest).
- CTA **"Apply for a founding slot"** opens a slightly longer inline form:
  email, product select, company size, and one free-text field — *"What's the
  most painful part of this job today?"* Hidden `source_cta=founding`.
- Founding applications are the **high-intent tier**: a founding application
  counts 3x a vote in the build decision (see §5).

**Why it converts:** scarcity ("10 per product") is credible at this scale and
true — a solo builder genuinely can't onboard more. The longer form filters
for seriousness and harvests the pain-point language we'll reuse as copy.

### Hook 3 — Time-Saved Calculator (engagement → gated capture)

**What it is:** a small interactive calculator: pick a product, drag 2 sliders,
see hours and dollars reclaimed per month.

**How it works on the page:**
- One shared component with a product tab-switcher; per-product inputs and
  math are specified in design.md §Section 7 (e.g. Triage: tickets/week ×
  minutes/ticket; Payable: invoices/month × minutes/invoice; assumptions
  stated under the result — deflection/automation rates are labeled
  "target," not claimed fact).
- The **result shows instantly and ungated** (gating the number itself feels
  cheap and kills trust). Below the result: *"Get this estimate emailed to you
  + first access when {Name} launches"* → email field. Hidden fields carry
  `product`, `source_cta=calculator`, **and the slider values** — so every
  calculator signup tells us the visitor's actual volume (tickets/week,
  invoices/month…). That's qualification data no waitlist form gets.

**Why it converts:** the calculator does work *for* the visitor before asking
for anything (reciprocity), personalizes the value prop with their own
numbers, and converts at the exact moment the pain is quantified in dollars.

### Hook 4 — "Peek at a sample run" (fake-door depth probe, zero backend)

**What it is:** each product card has a secondary text link — *"See a sample
run →"* — opening a modal with a **static, styled mock artifact** of the
agent's real output, drawn from each plan.md: a triaged ticket with a cited
answer and an escalation decision (Triage), an invoice audit trail with a
caught duplicate (Payable), a scored lead dossier with citations (Prospect),
a meeting digest with a carried-over action item (Follow-Through), a findings
table with severities and a suggested redline (Redline). Content is in
copy.md §7; rendered as styled HTML "terminal/report" panels, not images.

**How it works:** the modal footer repeats the vote CTA: *"Want this for your
{tickets/invoices/leads}? Vote for {Name}."* Every modal open fires an
analytics event `sample_open{product}` — so even non-submitting visitors
leave a per-product interest trace.

**Why it converts:** pre-launch pages fail when the product feels abstract.
A concrete artifact ("this is literally what lands in your inbox") makes the
promise tangible and honest — it's clearly labeled *"Illustrative sample —
this is what {Name} will produce."* It also measures depth of interest per
product independent of email submission.

### CTA structure decision: per-product micro-CTAs, one global fallback

- **Every primary CTA is per-product** (vote / founding / calculator all carry
  a product). This maximizes attribution — the entire point of the page.
- **One global fallback CTA** exists in the final banner + footer: *"Not sure
  which? Get the build updates for all five."* → `product=all`,
  `source_cta=global`. It catches generally-interested visitors without
  polluting per-product signal.
- Explicitly rejected: a single global "join waitlist" as primary (destroys
  attribution), and payment/preorder CTAs (goal is intent, not revenue).

---

## 3. Intent capture — summary of recommendation

Full comparison and spec in `signup-capture.md`. The decision:

- **No custom backend.** Static site + **Formspree** (one form endpoint, free
  tier): native HTML forms styled to match the design, product attribution via
  hidden fields, email notification to the owner per signup, CSV export.
- **Fallback: Tally.so** (free unlimited responses + Google Sheets sync) if
  Formspree's free 50 submissions/month is exceeded and the owner won't pay
  $10/mo — being over 50/month is itself a validation success.
- The GCP Firestore/Cloud Function option is deliberately deferred: it's the
  *post-validation* upgrade, not worth build time before signal exists.
- **Analytics: Google Analytics 4** (free) with 6 custom events + scroll
  depth, so intent is measurable even without a submit.

## 4. Design & build — summary of recommendation

Full spec in `design.md`. The decisions:

- **One static `index.html` + Tailwind CSS + ~150 lines vanilla JS.** No
  framework, no build step beyond the Tailwind CLI. Hosted on **GitHub Pages**
  (repo already lives on GitHub; free; custom domain when ready).
- Style: clean light "credible SaaS" base, ink-on-warm-white, indigo primary
  accent, **five per-product accent hues** used consistently across cards,
  vote bars, and calculator tabs (color = attribution made visible).
- Imagery: **no stock AI art, no fake screenshots.** Diagram-style pipeline
  chips on cards + dark terminal/report-styled sample panels, all HTML/CSS.
- Fonts: Space Grotesk (display) + Inter (body) + JetBrains Mono (samples).

---

## 5. End-to-end flow & measurement

### The journey

```
Visitor lands (LinkedIn post / community link / DM, with ?utm_source=…)
   │
   ▼
Hero: "Five agents. You pick what ships first." → primary CTA scrolls to grid
   │
   ├── Reads product card → clicks "Vote for {Name}"
   │       → inline form (email [+ company size]) → POST to Formspree
   │
   ├── Opens "See a sample run" → modal artifact → vote CTA  (event: sample_open)
   │
   ├── Uses calculator → sees $/month → emails estimate     (source: calculator,
   │                                                          + volume data)
   ├── Applies for founding slot → longer form               (source: founding,
   │                                                          + pain text)
   └── Unsure → final banner "updates on all five"           (product: all)
   │
   ▼
Formspree: stores submission, EMAILS THE OWNER instantly per signup
   │
   ▼
Owner: weekly — export Formspree CSV → tally sheet (template in
signup-capture.md §5) → update the leaderboard JSON on the page → check GA4
funnel (views → CTA clicks → submits, per product)
```

What the owner sees, concretely: **(a)** one email per signup with all fields,
**(b)** the Formspree dashboard/CSV of all submissions with product + source +
qualification fields, **(c)** GA4 per-product event counts. No dashboards to
build.

### Success criteria (decide the build queue mechanically)

Scoring: **intent points per product = votes×1 + calculator signups×2 +
founding applications×3** (weight = effort the visitor invested). Global
(`product=all`) signups count for nobody.

- **Build trigger:** a product is greenlit when it reaches **30 intent points
  including ≥3 founding applications, within 4 weeks** of the page getting
  ≥300 unique visitors. If two products qualify, higher points win;
  tie-break on founding applications.
- **Weak-signal trigger:** if after 500 visitors overall conversion
  (any submit / unique visitors) is **< 2%**, the page — not the products —
  is the problem: revise hooks/copy before concluding anything.
- **No-signal trigger:** ≥500 visitors, 4 weeks, no product above 10 points →
  demand evidence is absent; proceed on the learning roadmap (overview.md)
  and treat the page as a portfolio piece.
- Deduplicate by email per product when tallying; the same email across
  different products is legitimate multi-product interest (note it — it's
  bundle evidence).

### Owner ops cadence (post-launch, 15 min/week)

1. Export Formspree CSV → paste into the tally sheet.
2. Update leaderboard values + founding-slot counters in `index.html`.
3. Post the weekly standings wherever traffic comes from (the update IS the
   re-engagement content).
4. Reply personally to every founding application within 24h.

---

## 6. Build checklist for the intern (ordered)

Work top-to-bottom; each step has a verify gate. Total estimate: 3–5 days.

1. **Read all four docs in this folder**, then skim the five product
   `plan.md`s only if copy context is unclear. → verify: can state each
   product's one-liner from memory.
2. **Scaffold**: `landing-page/site/` with `index.html`, `input.css`,
   Tailwind CLI build (`design.md` §8), `main.js`. → verify: styled hello
   page builds and opens locally.
3. **Design tokens**: colors, fonts, spacing from `design.md` §2 as Tailwind
   config + CSS variables. → verify: swatch test page matches hex values.
4. **Static sections in order** — header, hero, problem strip, product grid
   (cards only, no forms yet), how-it-works, credibility, FAQ, footer — using
   final copy from `copy.md`. → verify: full page reads end-to-end, no
   placeholder text ("lorem" grep returns nothing).
5. **Leaderboard strip** driven by the `VOTE_DATA` JS constant (design.md §4,
   Section 3). → verify: editing the constant re-renders bars; pre-threshold
   state shows no numbers.
6. **Formspree setup**: owner creates the account/endpoint (10 min, see
   signup-capture.md §4); intern wires the vote form on ONE card. → verify: a
   real test submission arrives in owner's email with correct `product` and
   `source_cta`.
7. **Roll forms out** to all five cards + founding section + global banner.
   → verify: one test submission per form; every one attributes correctly.
8. **Sample-run modals** (Hook 4) with the five artifacts from copy.md §7.
   → verify: keyboard-closable, scrollable on mobile, CTA inside works.
9. **Calculator** (Hook 3) per design.md §Section 7. → verify: math matches
   the worked examples; hidden fields carry slider values into the
   submission email.
10. **GA4**: add the tag + the 6 events from signup-capture.md §6. → verify:
    events appear in GA4 DebugView for each CTA.
11. **Responsive + a11y pass** per design.md §6–7. → verify: Lighthouse
    ≥ 90 accessibility & performance on mobile; page usable at 360px width;
    keyboard-only run-through completes a vote.
12. **Spam guard**: honeypot field + Formspree reCAPTCHA setting. → verify:
    honeypot-filled submission is dropped.
13. **Deploy to GitHub Pages** (design.md §8). → verify: live URL loads, a
    live-site test submission arrives, GA4 shows the visit.
14. **Handoff note to owner**: live URL, how to update `VOTE_DATA` + slot
    counters, where signups land, the weekly cadence (§5). → verify: owner
    completes one leaderboard update unassisted.
