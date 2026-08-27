# Fleet — landing page

Static single-page site for Fleet. No framework, no runtime JS libraries, no images
(all visuals are HTML/CSS). Files:

| File | Purpose |
| --- | --- |
| `index.html` | The whole page — 11 sections, header → footer. |
| `main.js` | Vanilla JS: scroll-reveal, inline adopt forms, sample-run modal, calculator, AJAX form submit. |
| `input.css` | Tailwind directives + design tokens / component styles. **Source** for the build. |
| `tailwind.config.js` | Design tokens (colors, fonts) from the design spec. |
| `dist/style.css` | **Built, minified** output — this is what `index.html` loads. Committed. |

## Rebuild the CSS

The site uses the Tailwind **standalone CLI** (no Node project required). `dist/style.css`
is already built and committed; only rebuild if you edit `index.html`, `main.js`, `input.css`,
or `tailwind.config.js`.

Option A — standalone binary (preferred):

```bash
curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64
chmod +x tailwindcss-linux-x64
./tailwindcss-linux-x64 -c ./tailwind.config.js -i ./input.css -o ./dist/style.css --minify
```

Option B — via npm/npx (if you have Node):

```bash
npx tailwindcss@3.4.17 -c ./tailwind.config.js -i ./input.css -o ./dist/style.css --minify
```

Add `--watch` (drop `--minify`) while developing. Current build is ~20 KB.

> Note: per-product hue utility classes (`bg-triage`, `text-redline`, …) are applied
> dynamically from `main.js`, so they are listed in the `safelist` in `tailwind.config.js`.
> If you add a new product hue, add it to both the theme colors and the safelist.

## Wire up form capture (before launch)

All 8 capture points POST to one **Formspree** endpoint (see `../signup-capture.md`).

1. Create a free Formspree account + one form; copy its endpoint URL.
2. In `main.js`, set the `FORMSPREE_ENDPOINT` constant (top of file) to that URL.
3. In Formspree, enable email notifications + reCAPTCHA. The honeypot field (`_gotcha`)
   is already wired; Formspree drops submissions where it is filled.

Each form carries hidden `product` + `source_cta` fields for attribution; the calculator
form also sends `calc_a` / `calc_b` / `calc_hours`. No backend or build step is needed.

Optional analytics: `main.js` fires GA4 events (`cta_click`, `form_submit_ok`,
`sample_open`, `calc_used`, `calc_result_emailed`) via `window.gtag` if present. To enable,
add your GA4 `gtag.js` snippet to the top of `index.html`. It is a no-op without it.

## Deploy (pure static — any host works)

The folder is self-contained static files. Pick one:

- **GitHub Pages** — commit the repo, then either serve `landing-page/site/` via a Pages
  Actions workflow, or copy it to a `docs/` folder and set Pages → *Deploy from branch → /docs*.
  Custom domain later via a `CNAME` file.
- **Vercel** — `vercel deploy` with the project root set to `landing-page/site/` (framework
  preset: *Other*). No build command needed. `vercel.json` here disables automatic
  deployments on every branch except `main`, so PRs elsewhere in the repo get no Vercel
  check; pushes to `main` rebuild only when this folder changed.
- **Cloud Run / GCS bucket** — upload the folder to a bucket and enable static website
  hosting (aligns with the GCP stack), or serve it from any static file server.

There is no server logic and no build to run at deploy time — just publish the files as-is.

## Run locally

Zero dependencies.
```
cd ~/prod-agents/landing-page/site
python3 -m http.server 8000
```

## Notes / to-do before going live

- `index.html` references `og.png` for social sharing. Create a 1200×630 OG image
  (brand name + tagline on the `#FAFAF7` background) and drop it in this folder, or remove
  the `og:image` meta tag. It is the only image asset the site would use.
- Replace the placeholder contact address `hello@fleet.example.com` (footer) and the
  `og:url` with the real domain.
