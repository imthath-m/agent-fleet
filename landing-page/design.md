# Design Spec — Fleet Landing Page

Intern-ready visual + structural spec. All copy referenced here lives in
`copy.md`; capture/form behavior in `signup-capture.md`.

---

## 1. Style direction

**"Credible engineering, warm surface."** Light, editorial SaaS page — closer
to Linear/Stripe restraint than to gradient-heavy AI hype. Rationale: the
audience is SMB owners/ops leads who are skeptical of AI vaporware; the page's
credibility strategy (plan.md §1) is engineering honesty, so the design must
read *precise and calm*, with the dark, mono-spaced sample panels providing
the "this is real software" contrast.

Rules of thumb:
- Lots of whitespace; one accent color doing the work per element.
- No stock photos, no 3D robots, no glassmorphism, no purple-haze gradients.
- The five product hues are the only "loud" color moments, and they always
  mean the same product everywhere (cards, pricing selector, calculator tabs,
  modals). Color IS the attribution system, visualized.

## 2. Design tokens

### Color palette (exact hex)

| Token | Hex | Usage |
| --- | --- | --- |
| `ink` | `#0F172A` | Headings, body-strong, footer bg |
| `body` | `#334155` | Body text |
| `muted` | `#64748B` | Secondary text, captions |
| `bg` | `#FAFAF7` | Page background (warm off-white) |
| `surface` | `#FFFFFF` | Cards, forms |
| `border` | `#E2E8F0` | Card borders, dividers, input borders |
| `accent` | `#4F46E5` | Primary buttons, links, focus rings |
| `accent-hover` | `#4338CA` | Button hover |
| `accent-soft` | `#EEF2FF` | Accent tint backgrounds (badges, hero eyebrow) |
| `success` | `#059669` | Form success states |
| `panel` | `#0B1220` | Dark sample-run panels, terminal mocks |
| `panel-text` | `#C9D4E3` | Text on dark panels |

Per-product hues (each with a `-soft` tint for card badges/backgrounds):

| Product | Hue | Soft tint |
| --- | --- | --- |
| Triage (support) | `#0284C7` | `#E0F2FE` |
| Payable (invoices) | `#059669` | `#D1FAE5` |
| Prospect (leads) | `#D97706` | `#FEF3C7` |
| Follow-Through (meetings) | `#7C3AED` | `#EDE9FE` |
| Redline (contracts) | `#E11D48` | `#FFE4E6` |

Contrast note: all five hues pass WCAG AA (≥4.5:1) as text on white; never
put white text on `Prospect #D97706` at small sizes — use ink on the soft
tint instead.

### Typography

| Role | Font | Fallback stack | Sizes |
| --- | --- | --- | --- |
| Display / headings | **Space Grotesk** (Google Fonts, 500/700) | `system-ui, -apple-system, sans-serif` | h1 clamp(2.25rem→3.5rem); h2 2rem; h3 1.25rem |
| Body / UI | **Inter** (Google Fonts, 400/500/600) | same | 1rem/1.65 body; 0.875rem captions |
| Mono (sample panels, numbers) | **JetBrains Mono** (400/500) | `ui-monospace, SFMono-Regular, Menlo, monospace` | 0.8125rem in panels |

Load via one `<link>` with `display=swap`, preconnect to
`fonts.gstatic.com`. Letter-spacing `-0.02em` on h1/h2 only.

### Spacing, radius, shadow, layout

- Spacing scale: Tailwind default (4px base). Section vertical padding:
  `py-24` desktop / `py-16` mobile. Content max-width: `max-w-6xl` (1152px),
  `px-6` gutters.
- Radius: cards `rounded-2xl` (16px); buttons/inputs `rounded-lg` (8px);
  badges `rounded-full`.
- Shadows: cards `shadow-sm` at rest, `shadow-md` on hover — nothing heavier.
- Buttons: primary = accent bg / white text / `font-semibold` /
  `px-5 py-3`; secondary = white bg, `border`, ink text. Product-card adopt
  buttons use the **product hue** as bg (Prospect: use hue bg + white text at
  ≥1rem bold only, else soft tint + ink).

## 3. Page structure — section by section

Order is the buying narrative: promise → pain → products (capture) → how it
works → pricing/calculator → credibility → FAQ → last chance.

### Section 0 — Header (sticky)
- Purpose: orientation + persistent CTA.
- Left: brand wordmark (text, Space Grotesk 700 — no logo needed). Right:
  anchor links `The agents · How it works · Pricing · FAQ` +
  primary button **"Get started"** → smooth-scroll to product grid.
- Sticky, `bg/90` with `backdrop-blur`, bottom border appears after 8px
  scroll. Mobile: links collapse into the button only (no hamburger — anchors
  aren't worth a menu).

### Section 1 — Hero
- Purpose: state the offer + the honest frame in 5 seconds; route to grid.
- Layout: single centered column, max-w-3xl.
- Contents (copy.md §1): eyebrow badge ("A fleet of AI agents for your back
  office", accent-soft bg), h1, subhead, two buttons: primary "See the five
  agents ↓" (scroll), secondary "See pricing" (scroll). Below buttons,
  one line of `muted` microcopy: "Per-agent pricing. Take one, or all five for
  a bundle discount."
- No hero illustration. The value strip (next) is the visual.

### Section 2 — Value strip / build-your-fleet
- Purpose: make the opt-in model legible instantly; set up "assemble a fleet."
- A `surface` card containing five slim horizontal rows, one per agent:
  left label (agent name + emoji-free icon dot in product hue) + the agent's
  one-job tagline (e.g. "Support tickets", "Invoices"), each row tinted in the
  agent's soft hue. Reads as a menu of the fleet you can assemble.
- Caption under the strip: *"Add the agents you need — add more as we ship
  them."* Optional: each row anchors to its card in the grid below.
- Static markup; no data constant. No counts, no fabricated numbers of any
  kind — it's a menu of the fleet, not a scoreboard.

### Section 3 — Problem strip
- Purpose: name the pain before the products; earns the grid.
- Three short pain statements (copy.md §2) in a 3-col row (stack on mobile),
  each: bold first line + one muted sentence. No icons needed; a thin top
  border in `accent` on each.

### Section 4 — The Five Agents (product grid; the core)
- Purpose: present the agents + capture adoption. This section is the page.
- Layout: 2-column card grid (desktop), the 5th card centered full-row
  (`lg:col-span-2 lg:max-w-[calc(50%-12px)] lg:mx-auto`); 1 column mobile.
- **Anatomy of a product card** (`surface`, border, `rounded-2xl`, `p-8`):
  1. Top row: product-hue badge with agent name + status pill
     `Available · onboarding now` (muted).
  2. h3 one-liner (the real headline of the card — benefit, not name).
  3. Mini pipeline diagram: 3–4 step chips (`text-xs`, mono, soft-tint bg,
     hue text) joined by `→`, showing the agent's actual flow, e.g. Triage:
     `classify → answer w/ citations → act → escalate to you`. Chips come
     from copy.md §3. This is the "screenshot substitute" #1.
  4. Three pain bullets (copy.md §3) — each starts with a bolded 2–4 word
     pain, then the resolution phrase.
  5. Footer row: primary button **"Get {Name}"** (product hue) +
     text link **"See a sample run →"** (opens modal, §Section 4b).
  6. **Inline adopt form** (hidden until CTA click; replaces the footer row,
     120ms fade): email input + optional company-size select + submit
     ("Get started"), honeypot + hidden fields per signup-capture.md §4.
     On success (AJAX): swap form for success line in `success` color:
     *"Got it. We'll reach out to onboard {Name} onto your stack — usually
     within a day."*
- Card hover: `shadow-md` + 4px top border in product hue (transition 150ms).

### Section 4b — Sample-run modal (Mechanic 4)
- One modal component, five content payloads (copy.md §7).
- Visual: dark `panel` bg, `rounded-2xl`, max-w-2xl, JetBrains Mono
  0.8125rem, syntax-like coloring: keys in product hue, values in
  `panel-text`, statuses (`ESCALATED`, `DUPLICATE — HELD`, severity tags) in
  amber/rose. Header bar with three fake window dots + label
  `sample-output.log — illustrative`.
- Mandatory caption above content: *"Sample output — this is what {Name}
  produces."*
- Footer inside modal: adopt CTA button (product hue) — submits via the same
  form pipe with `source_cta=sample_modal` (its own inline email field).
- Behavior: open on link click; close on ✕, backdrop click, and `Escape`;
  focus-trapped; body scroll locked; fires `sample_open` event on open.

### Section 5 — How Fleet works
- Purpose: make adoption legible + reinforce control/honesty.
- Three numbered steps in a row (copy.md §4): 1 Pick your agents → 2 We wire it
  into your stack → 3 It runs, you stay in control. Step numbers in Space
  Grotesk, accent color, large (3rem).

### Section 6 — Pricing / build your fleet
- Purpose: present the opt-in/bundle model + capture the high-intent buyer.
- Full-width `ink` background section (the page's one dark section — signals
  weight). White text.
- Left: h2 + the three pricing tiers (copy.md §5) as rows: any one agent /
  any combination / all five (bundle discount). Optional honest launch-offer
  line beneath (check in `success`). No fabricated seat counts.
- Right: the **get-started form** on a `surface` card: email, the
  build-your-fleet checkbox selector (the 5 agents; selected agents become the
  `product` value), company-size select, one optional textarea ("What's the
  most painful part of this job today?" — 280 char max), submit
  **"Get started"**. Hidden `source_cta=pricing`.
- Per-agent prices and any launch-offer copy are edited directly in the markup
  and must always be true; no dynamic counters.

### Section 7 — Time-saved calculator (Mechanic 3)
- Purpose: engage, quantify pain, capture with volume data attached.
- `surface` card, max-w-3xl centered. Product tab-switcher (5 pills in
  product hues; active = filled, inactive = soft tint).
- Per product: 2 sliders + fixed assumption, all client-side JS:

| Product | Slider A (range, default) | Slider B (range, default) | Formula (hours/mo) | Stated capability |
| --- | --- | --- | --- | --- |
| Triage | tickets/week (10–500, 80) | min/ticket (2–30, 8) | `A×B/60 ×4.33 ×0.6` | "deflects ~60% of routine tickets" |
| Payable | invoices/month (20–1000, 120) | min/invoice (3–20, 8) | `A×B/60 ×0.8` | "~80% straight-through processing" |
| Prospect | leads researched/week (5–200, 25) | min/lead (10–60, 25) | `A×B/60 ×4.33 ×0.9` | "research automated; you still approve every draft" |
| Follow-Through | meetings/week (3–40, 12) | min of follow-up/meeting (5–45, 15) | `A×B/60 ×4.33 ×0.9` | "capture + routing automated; you approve external sends" |
| Redline | contracts/month (2–60, 8) | hours first-pass/contract (0.5–6, 2, step 0.5) | `A×B ×0.5` | "~50% faster first pass — a human always reviews" |

- Dollar line: `hours × $38/hr` (label: "at a $38/hr loaded ops cost —
  adjustable soon"). Round hours to whole, dollars to nearest $50.
- Result renders live in mono, large (2.5rem), product hue. Worked example
  for the intern's verify step: Triage defaults → 80×8/60×4.33×0.6 =
  **27.7 → "28 hrs/month" and "$1,050/month"**.
- Below result: email field + button **"Email me this estimate + get
  started"**; hidden fields: `product`, `source_cta=calculator`, `calc_a`,
  `calc_b`, `calc_hours` (see signup-capture.md §4). The estimate is sent when
  the owner replies (there's no auto-emailer; do not promise instant delivery).

### Section 8 — Built like production software (credibility)
- Purpose: replace social proof with engineering truth.
- h2 + intro line, then 4 fact cards in a 2×2 grid (copy.md §6): eval-gated
  releases, full audit trail, human-in-the-loop by design, runs on Google
  Cloud. Each: small mono keyword tag + 2 sentences. Muted, factual tone;
  no product hues here — accent only.

### Section 9 — FAQ
- Purpose: answer the skeptical-buyer objections directly.
- Accordion (native `<details>/<summary>`, styled): 6 Q&As from copy.md §8 —
  "can I adopt just one agent?", what getting started commits you to (a
  conversation), how onboarding works, data handling, data isolation once an
  agent runs, and the legal disclaimer for Redline.

### Section 10 — Final CTA banner
- Purpose: last capture chance, incl. the undecided.
- Accent-soft bg band: h2 ("Ready to hand off the busywork?"),
  primary button back to grid, and the **global fallback form** inline:
  email + "Talk to us" (`product=all`, `source_cta=global`).

### Section 11 — Footer
- `ink` bg. Brand line + one-sentence description; contact email
  (mailto); links: FAQ anchor, privacy note (one hosted paragraph — what we
  store: your email + form answers, never sold, one-click removal by reply);
  the Redline disclaimer line; `© 2026 {brand}`.

## 4. Micro-interactions & animation (tasteful, cheap)

- **Scroll-reveal**: sections fade-up 12px, 350ms ease-out, staggered 60ms
  for cards — via one `IntersectionObserver` + a `.revealed` class. Nothing
  animates more than once.
- **Value-strip rows** fade-up on first reveal (staggered 60ms, no width
  animation — they carry no data to fill).
- **Buttons**: 150ms bg transition; active state `scale(0.98)`.
- **Card hover**: shadow + top-border reveal, 150ms.
- **Form success**: 200ms crossfade to success line; no confetti.
- **Respect `prefers-reduced-motion: reduce`**: disable reveal and bar
  animations (render final state immediately).
- Performance rules: animate only `opacity`/`transform`; no scroll-jacking,
  no parallax, no autoplaying anything, no Lottie.

## 5. Responsive behavior

- Breakpoints: default mobile-first; `md:` 768 (problem strip → 3-col, steps
  → row); `lg:` 1024 (product grid → 2-col, pricing section → 2-col).
- Hero h1 uses `clamp()`; all tap targets ≥ 44px; inputs `text-base` (16px)
  to prevent iOS zoom.
- Calculator: tabs wrap to 2 rows at <480px; sliders full-width.
- Modal: on mobile becomes full-screen sheet (inset-0, scrollable); sample
  panels get `overflow-x-auto`.
- Test at 360px, 768px, 1280px minimum.

## 6. Accessibility basics (non-negotiable)

- Semantic landmarks: `header/nav/main/section/footer`; one `h1`; sections
  headed by `h2` with `id`s matching nav anchors.
- Every input has a `<label>` (visually hidden where design omits it);
  form success/error announced via `aria-live="polite"` region.
- Modal: `role="dialog"` `aria-modal="true"`, labelled by its heading,
  focus trap + return-focus-on-close.
- Sliders: native `<input type="range">` with `aria-valuetext` (e.g. "80
  tickets per week"); value also shown as text.
- Focus visible everywhere: 2px `accent` ring, 2px offset. Color is never
  the only signal (product names always accompany hues).
- Contrast: tokens in §2 chosen to pass AA; verify with Lighthouse ≥ 90.

## 7. SEO / head basics

- `<title>`: "Fleet — a fleet of AI agents that run your back office."
  Meta description from hero subhead. Open Graph title/description + a simple
  1200×630 OG image (brand name + tagline on `bg`, can be made in Figma/Canva
  in 10 min — the only image asset on the site).
- Favicon: simple wordmark glyph (e.g. "F"), ink on accent-soft.

## 8. Tech stack & hosting (decisions)

- **Stack: one static `index.html` + Tailwind CSS (standalone CLI) + one
  `main.js` (vanilla, ~150 lines: reveal observer, modal, tabs/sliders,
  value-strip render, AJAX form submit).**
  - Why not Next.js/React: zero routing, zero server logic, one page — a
    framework adds build/deploy surface for an intern with no payoff.
  - Why not Tailwind Play CDN: fine for drafts, but ships ~300KB of runtime
    JS; the standalone CLI (`tailwindcss -i input.css -o dist/style.css
    --minify`) needs no Node project and outputs ~10KB purged CSS.
  - Location: `landing-page/site/` in this repo.
- **Hosting: GitHub Pages.** The repo already lives on GitHub; free; deploy =
  push (serve `landing-page/site/` via an Actions workflow or a `docs/`
  copy — intern's choice, document it in the handoff note). Custom domain
  later via CNAME. Fallback: Firebase Hosting (GCP alignment) if the owner
  wants one console — but it adds a CLI + project setup for no v1 gain.
- Perf budget: < 150KB total transfer, zero images besides OG (all visuals
  are HTML/CSS), Lighthouse performance ≥ 90 mobile.
