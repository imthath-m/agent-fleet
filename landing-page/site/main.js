/* Fleet landing page — vanilla JS: reveal, adopt forms, sample modal, calculator, AJAX submit. */
(function () {
  "use strict";

  // Owner sets this to their Formspree endpoint (signup-capture.md §4). All forms POST here.
  var FORMSPREE_ENDPOINT = "https://formspree.io/f/XXXXXXXX";

  var PRODUCTS = {
    triage:        { name: "Triage",         noun: "tickets",   hue: "triage" },
    payable:       { name: "Payable",        noun: "invoices",  hue: "payable" },
    prospect:      { name: "Prospect",       noun: "leads",     hue: "prospect" },
    followthrough: { name: "Follow-Through", noun: "meetings",  hue: "followthrough" },
    redline:       { name: "Redline",        noun: "contracts", hue: "redline" }
  };

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Prospect (#D97706) fails AA contrast for white text at normal button weight/size
  // (design.md §2/§3) — use ink on the soft tint instead; other hues use hue bg + white text.
  function ctaClass(hue) { return hue === "prospect" ? "text-ink bg-prospect-soft" : "text-white bg-" + hue; }

  function track(name, params) { if (window.gtag) window.gtag("event", name, params || {}); }

  /* ---- UTM capture: copy query params into every hidden utm field ---- */
  var qs = new URLSearchParams(location.search);
  document.querySelectorAll("[data-utm]").forEach(function (el) {
    var v = qs.get(el.getAttribute("data-utm"));
    if (v) el.value = v;
  });

  /* ---- Header border after 8px scroll ---- */
  var header = document.getElementById("site-header");
  function onScroll() { header.classList.toggle("border-border", window.scrollY > 8); }
  onScroll(); addEventListener("scroll", onScroll, { passive: true });

  /* ---- Scroll-reveal ---- */
  var reveals = document.querySelectorAll(".reveal");
  if (reduce || !("IntersectionObserver" in window)) {
    reveals.forEach(function (el) { el.classList.add("revealed"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e, i) {
        if (e.isIntersecting) {
          setTimeout(function () { e.target.classList.add("revealed"); }, (i % 4) * 60);
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    reveals.forEach(function (el) { io.observe(el); });
  }

  /* ---- AJAX form submit (delegated across all .capture-form) ---- */
  document.addEventListener("submit", function (ev) {
    var form = ev.target.closest(".capture-form");
    if (!form) return;
    ev.preventDefault();
    if (form.querySelector('[name="_gotcha"]').value) return; // honeypot filled → silently drop
    var err = form.querySelector(".capture-error");
    var success = form.parentElement.querySelector(".capture-success");
    var product = form.querySelector('[name="product"]').value;
    var source = form.querySelector('[name="source_cta"]').value;
    if (err) err.classList.add("hidden");

    fetch(FORMSPREE_ENDPOINT, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("bad");
        form.classList.add("hidden");
        if (success) success.classList.remove("hidden");
        track("form_submit_ok", { product: product, source_cta: source });
        if (source === "calculator") track("calc_result_emailed", { product: product, calc_hours: form.querySelector('[name="calc_hours"]').value });
      })
      .catch(function () { if (err) err.classList.remove("hidden"); });
  });

  /* ---- CTA click analytics ---- */
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-cta],[data-adopt]");
    if (!b) return;
    var card = b.closest("[data-product]");
    var form = b.closest(".capture-form");
    var product = b.getAttribute("data-adopt") || (card && card.dataset.product) || (form && form.querySelector('[name="product"]').value);
    var source = form ? form.querySelector('[name="source_cta"]').value : "adopt";
    track("cta_click", { product: product, source_cta: source });
  });

  /* ---- Inline adopt form (built on demand, replaces the CTA row) ---- */
  var SIZE_OPTS = '<option value="">Company size (optional)</option><option value="solo">Just me</option><option value="2-10">2–10</option><option value="11-50">11–50</option><option value="51-200">51–200</option><option value="200+">200+</option>';
  document.querySelectorAll("[data-adopt]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var product = btn.getAttribute("data-adopt");
      var p = PRODUCTS[product];
      var footer = btn.closest("[data-footer]");
      var row = footer.querySelector("[data-cta-row]");
      var wrap = document.createElement("div");
      wrap.style.transition = "opacity 120ms";
      wrap.style.opacity = "0";
      wrap.innerHTML =
        '<form class="capture-form" data-source="adopt" novalidate>' +
        '<input type="hidden" name="product" value="' + product + '">' +
        '<input type="hidden" name="source_cta" value="adopt">' +
        '<input type="hidden" name="_subject" value="Get started: ' + product + ' (adopt)">' +
        '<input type="hidden" name="utm_source" value="' + (qs.get("utm_source") || "") + '">' +
        '<input type="hidden" name="utm_campaign" value="' + (qs.get("utm_campaign") || "") + '">' +
        '<input type="text" name="_gotcha" tabindex="-1" autocomplete="off" class="hidden" aria-hidden="true">' +
        '<div class="flex flex-col gap-2">' +
        '<label class="block"><span class="sr-only-label">Work email</span><input class="input" type="email" name="email" required placeholder="you@company.com"></label>' +
        '<label class="block"><span class="sr-only-label">Company size (optional)</span><select class="input" name="company_size">' + SIZE_OPTS + '</select></label>' +
        '<button type="submit" class="btn ' + ctaClass(p.hue) + '" data-cta>Get started</button>' +
        '</div>' +
        '<p class="capture-error text-sm text-redline mt-2 hidden" role="alert" aria-live="polite">That didn\'t go through — mind trying again?</p>' +
        '</form>' +
        '<p class="capture-success text-success font-medium mt-2 hidden" role="status" aria-live="polite">Got it. We\'ll reach out to onboard ' + p.name + ' onto your stack — usually within a day.</p>';
      row.replaceWith(wrap);
      requestAnimationFrame(function () { wrap.style.opacity = "1"; });
      var email = wrap.querySelector('input[type="email"]');
      if (email) email.focus();
    });
  });

  /* ============================ SAMPLE-RUN MODAL ============================ */
  var modal = document.getElementById("modal");
  var modalBody = document.getElementById("modal-body");
  var lastFocused = null;

  function openModal(product) {
    var p = PRODUCTS[product];
    var src = document.querySelector('#samples [data-sample="' + product + '"]');
    modalBody.innerHTML = "";
    modalBody.appendChild(src.cloneNode(true));
    modal.querySelector("[data-modal-name]").textContent = p.name;
    modal.querySelector("[data-modal-cta-text]").textContent = "Want this for your " + p.noun + "? Get " + p.name + ".";
    var f = modal.querySelector(".capture-form");
    f.querySelector('[name="product"]').value = product;
    f.querySelector('[name="_subject"]').value = "Get started: " + product + " (sample modal)";
    var btn = modal.querySelector("[data-modal-submit]");
    btn.className = "btn " + ctaClass(p.hue) + " whitespace-nowrap";
    btn.setAttribute("data-cta", "");
    btn.setAttribute("data-modal-submit", "");
    btn.textContent = "Get " + p.name;
    f.classList.remove("hidden");
    modal.querySelector(".capture-success").classList.add("hidden");
    modal.querySelector("[data-modal-success]").textContent = "Got it. We'll reach out to onboard " + p.name + " onto your stack — usually within a day.";
    lastFocused = document.activeElement;
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    modal.querySelector("[data-modal-close]").focus();
    track("sample_open", { product: product });
  }
  function closeModal() {
    modal.classList.add("hidden");
    document.body.style.overflow = "";
    if (lastFocused) lastFocused.focus();
  }
  document.querySelectorAll("[data-sample]").forEach(function (b) {
    b.addEventListener("click", function () { openModal(b.getAttribute("data-sample")); });
  });
  modal.querySelectorAll("[data-modal-close]").forEach(function (el) { el.addEventListener("click", closeModal); });
  document.addEventListener("keydown", function (e) {
    if (modal.classList.contains("hidden")) return;
    if (e.key === "Escape") { closeModal(); return; }
    if (e.key === "Tab") { // focus trap
      var f = modal.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])');
      f = Array.prototype.filter.call(f, function (el) { return !el.disabled && el.offsetParent !== null; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  /* ============================ CALCULATOR ============================ */
  var CALC = {
    triage:        { a: { min: 10, max: 500, def: 80, step: 1, unit: "tickets per week", label: "Tickets per week" },        b: { min: 2, max: 30, def: 8, step: 1, unit: "minutes per ticket", label: "Minutes per ticket" },                   f: function (a, b) { return a * b / 60 * 4.33 * 0.6; }, cap: "Deflects ~60% of routine tickets." },
    payable:       { a: { min: 20, max: 1000, def: 120, step: 1, unit: "invoices per month", label: "Invoices per month" },   b: { min: 3, max: 20, def: 8, step: 1, unit: "minutes per invoice", label: "Minutes per invoice" },                  f: function (a, b) { return a * b / 60 * 0.8; }, cap: "~80% straight-through processing." },
    prospect:      { a: { min: 5, max: 200, def: 25, step: 1, unit: "leads researched per week", label: "Leads researched per week" }, b: { min: 10, max: 60, def: 25, step: 1, unit: "minutes per lead", label: "Minutes per lead" },        f: function (a, b) { return a * b / 60 * 4.33 * 0.9; }, cap: "Research automated; you still approve every draft." },
    followthrough: { a: { min: 3, max: 40, def: 12, step: 1, unit: "meetings per week", label: "Meetings per week" },         b: { min: 5, max: 45, def: 15, step: 1, unit: "minutes of follow-up per meeting", label: "Minutes of follow-up per meeting" }, f: function (a, b) { return a * b / 60 * 4.33 * 0.9; }, cap: "Capture + routing automated; you approve external sends." },
    redline:       { a: { min: 2, max: 60, def: 8, step: 1, unit: "contracts per month", label: "Contracts per month" },      b: { min: 0.5, max: 6, def: 2, step: 0.5, unit: "hours of first-pass review per contract", label: "Hours first-pass per contract" }, f: function (a, b) { return a * b * 0.5; }, cap: "~50% faster first pass — a human always reviews." }
  };
  var calcCur = "triage";
  var calcUsed = {};
  var elA = document.getElementById("calc-a"), elB = document.getElementById("calc-b");
  var valA = document.getElementById("calc-a-val"), valB = document.getElementById("calc-b-val");
  var labA = document.getElementById("calc-a-label"), labB = document.getElementById("calc-b-label");
  var outH = document.getElementById("calc-hours-out"), outD = document.getElementById("calc-dollars-out");
  var capEl = document.getElementById("calc-capability");
  var calcForm = document.querySelector('.capture-form[data-source="calculator"]');
  var tabs = document.querySelectorAll(".calc-tab");

  function setTab(product) {
    calcCur = product;
    var c = CALC[product];
    tabs.forEach(function (t) {
      var on = t.dataset.tab === product;
      var h = t.dataset.tab;
      // Prospect (#D97706) fails AA contrast for white text at this size — ink reads fine on the fill.
      var onText = h === "prospect" ? "text-ink" : "text-white";
      t.className = "calc-tab rounded-full px-4 py-2 text-sm font-medium " + (on ? "bg-" + h + " " + onText : "bg-" + h + "-soft text-" + h);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    labA.textContent = c.a.label; labB.textContent = c.b.label;
    elA.min = c.a.min; elA.max = c.a.max; elA.step = c.a.step; elA.value = c.a.def;
    elB.min = c.b.min; elB.max = c.b.max; elB.step = c.b.step; elB.value = c.b.def;
    capEl.textContent = c.cap;
    calcForm.querySelector('[name="product"]').value = product;
    calcForm.querySelector('[name="_subject"]').value = "Get started: " + product + " (calculator)";
    outH.className = "font-mono font-medium text-" + product;
    outH.style.fontSize = "2.5rem"; outH.style.lineHeight = "1.1";
    compute();
  }
  function compute() {
    var c = CALC[calcCur];
    var a = parseFloat(elA.value), b = parseFloat(elB.value);
    valA.textContent = a; valB.textContent = b;
    elA.setAttribute("aria-valuetext", a + " " + c.a.unit);
    elB.setAttribute("aria-valuetext", b + " " + c.b.unit);
    var hours = Math.round(c.f(a, b));
    var dollars = Math.round(hours * 38 / 50) * 50;
    outH.textContent = hours + " hrs/month";
    outD.textContent = "$" + dollars.toLocaleString("en-US") + "/month";
    calcForm.querySelector('[name="calc_a"]').value = a;
    calcForm.querySelector('[name="calc_b"]').value = b;
    calcForm.querySelector('[name="calc_hours"]').value = hours;
  }
  function onSlide() {
    compute();
    if (!calcUsed[calcCur]) { calcUsed[calcCur] = true; track("calc_used", { product: calcCur }); }
  }
  tabs.forEach(function (t) { t.addEventListener("click", function () { setTab(t.dataset.tab); }); });
  elA.addEventListener("input", onSlide);
  elB.addEventListener("input", onSlide);
  setTab("triage");

  /* ---- Pricing checkbox selector → product value (comma list, or 'all') ---- */
  var picks = document.querySelectorAll(".fleet-pick");
  var pricingForm = document.querySelector('.capture-form[data-source="pricing"]');
  if (pricingForm) {
    picks.forEach(function (cb) {
      cb.addEventListener("change", function () {
        var sel = Array.prototype.filter.call(picks, function (c) { return c.checked; }).map(function (c) { return c.value; });
        pricingForm.querySelector('[name="product"]').value = sel.length === picks.length ? "all" : sel.join(",");
      });
    });
  }
})();
