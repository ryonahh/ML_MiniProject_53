/* Medal Momentum: renders every chart from window.OLYMPIC_DATA (written by the pipeline). */
(() => {
  "use strict";

  const D = window.OLYMPIC_DATA;
  if (!D) {
    document.getElementById("race-track").textContent =
      "Results not found. Run python scripts/run_pipeline.py to create docs/assets/data.js.";
    return;
  }

  const PROPOSED = D.meta.proposed;
  const REFERENCE = D.meta.reference;
  const NS = "http://www.w3.org/2000/svg";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel, root = document) => root.querySelector(sel);
  const fmt = (v, d = 2) => Number(v).toFixed(d);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  /* ---------- small helpers ---------- */
  function el(tag, attrs = {}, parent, text) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function svgFor(container, width, height) {
    container.replaceChildren();
    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "presentation" }, container);
    el("defs", {}, svg);
    // Charts animate once, the first time they scroll into view.
    if (!reduceMotion && container.dataset.anim === "go") {
      svg.classList.add("anim");
      container.dataset.anim = "done";
    }
    return svg;
  }

  let defId = 0;
  function gradient(svg, colour) {
    const id = `grad${++defId}`;
    const g = el("linearGradient", { id, x1: 0, x2: 1, y1: 0, y2: 0 }, svg.querySelector("defs"));
    el("stop", { offset: "0%", "stop-color": colour, "stop-opacity": 0.55 }, g);
    el("stop", { offset: "100%", "stop-color": colour }, g);
    return `url(#${id})`;
  }

  function glow(svg, colour) {
    const id = `glow${++defId}`;
    const f = el("filter", { id, x: "-20%", y: "-20%", width: "140%", height: "140%" }, svg.querySelector("defs"));
    el("feDropShadow", { dx: 0, dy: 0, stdDeviation: 3.5, "flood-color": colour, "flood-opacity": 0.7 }, f);
    return `url(#${id})`;
  }

  function drawIn(svg, path) {
    if (!svg.classList.contains("anim")) return;
    const len = path.getTotalLength ? path.getTotalLength() : 1000;
    path.classList.add("draw");
    path.style.setProperty("--len", len);
    path.setAttribute("stroke-dasharray", len);
  }

  function countUp(node, delay = 0) {
    const m = node.textContent.match(/^([\d.]+)(.*)$/);
    if (!m || reduceMotion) return;
    const target = parseFloat(m[1]), decimals = (m[1].split(".")[1] || "").length, rest = m[2];
    const start = performance.now() + delay, dur = 1100;
    node.textContent = `${(0).toFixed(decimals)}${rest}`;
    const step = (now) => {
      const k = Math.max(0, Math.min(1, (now - start) / dur)), e = 1 - Math.pow(1 - k, 3);
      node.textContent = `${(target * e).toFixed(decimals)}${rest}`;
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  const scale = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);

  function niceMax(v, step) {
    return Math.ceil(v / step) * step;
  }

  const tip = $("#tip");
  function showTip(evt, html) {
    tip.innerHTML = html;
    tip.hidden = false;
    const x = evt.clientX ?? evt.target.getBoundingClientRect().left;
    const y = evt.clientY ?? evt.target.getBoundingClientRect().top;
    tip.style.left = `${Math.min(Math.max(x, 90), window.innerWidth - 90)}px`;
    tip.style.top = `${y}px`;
  }
  const hideTip = () => { tip.hidden = true; };
  function withTip(node, html) {
    node.setAttribute("tabindex", "0");
    node.addEventListener("pointerenter", (e) => showTip(e, html));
    node.addEventListener("pointermove", (e) => showTip(e, html));
    node.addEventListener("pointerleave", hideTip);
    node.addEventListener("focus", (e) => {
      const r = e.target.getBoundingClientRect();
      showTip({ clientX: r.left + r.width / 2, clientY: r.top }, html);
    });
    node.addEventListener("blur", hideTip);
  }

  const modelColour = (name) =>
    name === PROPOSED ? css("--gold") : name === REFERENCE ? css("--silver")
      : name === "Baseline" ? css("--bronze") : css("--other");

  /* ---------- theme ---------- */
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("theme");
    if (saved) root.dataset.theme = saved;
  } catch (_) { /* storage unavailable */ }
  $("[data-theme-toggle]").addEventListener("click", () => {
    const dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (_) { /* ignore */ }
    renderAll(false);
  });

  /* ---------- hero: the race ---------- */
  const raceState = { games: "2020", animate: !reduceMotion };

  function raceRows(games) {
    if (games === "2020") {
      return D.forecast2020
        .filter((r) => r.actual !== null)
        .sort((a, b) => b.actual - a.actual)
        .slice(0, 8)
        .map((r) => ({ country: r.country, prev: r.previous, pred: r.predicted, actual: r.actual }));
    }
    return D.predictions2016
      .slice()
      .sort((a, b) => b.actual - a.actual)
      .slice(0, 8)
      .map((r) => ({ country: r.country, prev: r.previous, pred: r[PROPOSED], actual: r.actual }));
  }

  function renderRace() {
    const box = $("#race-track");
    const rows = raceRows(raceState.games);
    const W = Math.max(box.clientWidth, 320);
    const narrow = W < 560;
    const lane = narrow ? 40 : 48;
    const top = 26;
    const labelW = narrow ? 78 : 130;
    const H = top + rows.length * lane + 6;
    const svg = svgFor(box, W, H);
    const max = niceMax(Math.max(...rows.flatMap((r) => [r.prev, r.pred, r.actual])) * 1.04, 20);
    const x = scale(0, max, labelW, W - 12);
    const laneLine = css("--lane") || "rgba(255,255,255,.5)";

    // distance markers along the top of the track
    for (let v = 0; v <= max; v += 20) {
      el("line", { x1: x(v), x2: x(v), y1: top - 6, y2: H - 4, stroke: "rgba(255,255,255,.12)" }, svg);
      el("text", { x: x(v), y: 12, "text-anchor": "middle", fill: "rgba(255,255,255,.75)", "font-size": 13 }, svg,
        v === 0 && !narrow ? "0 medals" : v);
    }
    // lanes
    rows.forEach((r, i) => {
      const y0 = top + i * lane;
      el("line", { x1: 0, x2: W, y1: y0, y2: y0, stroke: laneLine, "stroke-width": 1.5 }, svg);
      el("text", { x: 2, y: y0 + lane / 2 + 6, fill: "#fff", "font-size": narrow ? 15 : 18, "font-weight": 600 }, svg,
        r.country);
    });
    el("line", { x1: 0, x2: W, y1: top + rows.length * lane, y2: top + rows.length * lane, stroke: laneLine, "stroke-width": 1.5 }, svg);
    el("line", { x1: labelW, x2: labelW, y1: top, y2: top + rows.length * lane, stroke: "#fff", "stroke-width": 3 }, svg);

    const gold = css("--gold");
    rows.forEach((r, i) => {
      const cy = top + i * lane + lane / 2;
      const g = el("g", {}, svg);
      el("circle", { cx: x(r.prev), cy, r: 7, fill: "none", stroke: "rgba(255,255,255,.85)", "stroke-width": 2 }, g);
      el("rect", { x: x(r.actual) - 1.75, y: cy - 13, width: 3.5, height: 26, rx: 1.5, fill: "#fff" }, g);
      const runner = el("circle", { cx: x(r.pred), cy, r: 9, fill: gold, stroke: "#13223a", "stroke-width": 1.5 }, g);
      if (raceState.animate) {
        const dx = x(r.pred) - labelW;
        runner.style.transform = `translateX(${-dx}px)`;
        runner.style.transition = `transform ${900 + i * 90}ms cubic-bezier(.2,.7,.2,1) ${i * 70}ms`;
        requestAnimationFrame(() => requestAnimationFrame(() => { runner.style.transform = "translateX(0)"; }));
      }
      const err = r.pred - r.actual;
      withTip(g, `<b>${r.country}</b><br>Previous Games: ${r.prev}<br>Forecast: ${fmt(r.pred, 1)}<br>Actual: ${r.actual}<br>Off by ${fmt(Math.abs(err), 1)} (${err > 0 ? "over" : "under"})`);
      g.setAttribute("aria-label", `${r.country}: forecast ${fmt(r.pred, 1)}, actual ${r.actual}`);
    });
    raceState.animate = false;

    const tokyo = D.tokyo && D.tokyo.find((m) => m.name === PROPOSED);
    const ours = D.models.find((m) => m.name === PROPOSED);
    $("#race-note").textContent = raceState.games === "2020"
      ? `Trained on 1964–2016 and made without any 2020 information. Average error across all ${D.meta.forecast_countries} countries: ${fmt(tokyo ? tokyo.MAE : NaN)} medals.`
      : `Trained on 1964–2012, tested on Rio. Average error across all countries: ${fmt(ours.MAE_mean, 3)} medals.`;
  }

  document.querySelectorAll(".seg button").forEach((btn) =>
    btn.addEventListener("click", () => {
      document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      raceState.games = btn.dataset.games;
      raceState.animate = !reduceMotion;
      renderRace();
    }));

  /* ---------- findings ---------- */
  function familyStats() {
    if (!D.families) return {};
    const names = [...new Set(D.families.map((r) => r.model))];
    const pairs = names.map((m) => [D.families.find((r) => r.model === m && r.target === "Count"),
      D.families.find((r) => r.model === m && r.target === "Momentum")]).filter(([c, mo]) => c && mo);
    const better = pairs.filter(([c, mo]) => mo.MAE < c.MAE).length;
    const nb = pairs.find(([c]) => c.model.startsWith("Paper best"));
    return {
      families: `${better} of ${pairs.length}`,
      familiesShort: `${better} of ${pairs.length}`,
      nbCount: nb ? fmt(nb[0].MAE, 2) : "",
      nbMom: nb ? fmt(nb[1].MAE, 2) : "",
    };
  }

  function fillFindings() {
    const by = Object.fromEntries(D.models.map((m) => [m.name, m]));
    const ours = by[PROPOSED], hist = by[REFERENCE], base = by.Baseline;
    const series = D.backtest.series;
    // Games where a momentum-target model (with or without the score) beat every count model.
    const momentumModels = D.models.filter((m) => m.target === "momentum").map((m) => m.name);
    const wins = D.backtest.years.filter((_, i) => {
      const best = (names) => Math.min(...names.map((m) => series[m][i]));
      const others = Object.keys(series).filter((m) => !momentumModels.includes(m));
      return best(momentumModels) < best(others);
    }).length;
    const s = D.significance;
    const values = {
      mae: fmt(ours.MAE_mean, 2),
      vsBase: fmt(100 * (1 - ours.MAE_mean / base.MAE_mean), 0),
      vsHist: fmt(100 * (1 - ours.MAE_mean / hist.MAE_mean), 0),
      wins: `${wins} of ${D.backtest.years.length}`,
      prob: `${fmt(100 * s.prob_a_better, 0)}%`,
      ci: `${fmt(-s.ci_high, 2)} to ${fmt(-s.ci_low, 2)}`,
      scoreMae: fmt(by["Historical + Momentum Score"].MAE_mean, 3),
      histMae: fmt(hist.MAE_mean, 3),
      ecoMissing: `${fmt(100 * (1 - (D.economicCoverage ?? 1)), 0)}%`,
      winsShort: `${wins}/${D.backtest.years.length}`,
      ...familyStats(),
    };
    document.querySelectorAll("[data-k]").forEach((node) => { node.textContent = values[node.dataset.k]; });
    $("#params").textContent =
      `${D.meta.params.n_estimators} trees, at least ${D.meta.params.min_samples_leaf} rows per leaf, ${Math.round(D.meta.params.max_features * 100)}% of features per split`;
    $("#seeds").textContent = D.meta.seeds;
  }

  /* ---------- results: bar chart ---------- */
  function renderBars() {
    const box = $("#bars");
    const W = Math.max(box.clientWidth, 300);
    const narrow = W < 460;
    const rows = D.models.slice().sort((a, b) => a.MAE_mean - b.MAE_mean);
    const rowH = 40, top = 6, labelW = narrow ? 0 : 190, bottom = 28;
    const H = top + rows.length * (narrow ? rowH + 18 : rowH) + bottom;
    const svg = svgFor(box, W, H);
    const max = niceMax(Math.max(...rows.map((r) => r.MAE_mean + r.MAE_std)) * 1.05, 0.5);
    const x = scale(0, max, labelW, W - 48);
    const plotBottom = H - bottom;

    for (let v = 0; v <= max + 1e-9; v += 0.5) {
      el("line", { x1: x(v), x2: x(v), y1: top, y2: plotBottom, class: "grid", stroke: css("--rule") }, svg);
      el("text", { x: x(v), y: H - 8, "text-anchor": "middle", class: "axis", fill: css("--ink-2"), "font-size": 13 }, svg, fmt(v, 1));
    }
    rows.forEach((r, i) => {
      const step = narrow ? rowH + 18 : rowH;
      const y = top + i * step + (narrow ? 18 : 0);
      if (narrow) {
        el("text", { x: 0, y: y - 4, class: "lbl" }, svg, r.name);
      } else {
        el("text", { x: labelW - 12, y: y + rowH / 2 + 1, "text-anchor": "end", "dominant-baseline": "middle", class: "lbl",
          "font-weight": r.name === PROPOSED ? 700 : 500 }, svg, r.name);
      }
      const bar = el("rect", { x: x(0), y: y + 7, width: Math.max(x(r.MAE_mean) - x(0), 1), height: rowH - 14, rx: 5,
        fill: gradient(svg, modelColour(r.name)), class: "bar", style: `animation-delay:${i * 70}ms` }, svg);
      el("line", { x1: x(r.MAE_mean - r.MAE_std), x2: x(r.MAE_mean + r.MAE_std), y1: y + rowH / 2, y2: y + rowH / 2,
        stroke: css("--ink"), "stroke-width": 1.4, opacity: 0.55 }, svg);
      el("text", { x: x(r.MAE_mean + r.MAE_std) + 6, y: y + rowH / 2 + 1, "dominant-baseline": "middle", class: "val" }, svg,
        fmt(r.MAE_mean, 3));
      withTip(bar, `<b>${r.name}</b><br>${r.description}<br>MAE ${fmt(r.MAE_mean, 3)} ± ${fmt(r.MAE_std, 3)}<br>RMSE ${fmt(r.RMSE_mean, 2)}, R² ${fmt(r.R2_mean, 3)}`);
    });
  }

  /* ---------- results: backtest lines ---------- */
  const hiddenLines = new Set();
  function renderLines() {
    const box = $("#lines");
    const W = Math.max(box.clientWidth, 300);
    const H = Math.round(Math.min(Math.max(W * 0.62, 240), 330));
    const pad = { l: 40, r: 14, t: 12, b: 30 };
    const svg = svgFor(box, W, H);
    const { years, series } = D.backtest;
    const all = Object.values(series).flat();
    const lo = Math.floor(Math.min(...all) * 10) / 10 - 0.1;
    const hi = Math.ceil(Math.max(...all) * 10) / 10 + 0.05;
    const x = scale(0, years.length - 1, pad.l, W - pad.r);
    const y = scale(lo, hi, H - pad.b, pad.t);

    for (let v = Math.ceil(lo * 5) / 5; v <= hi; v += 0.2) {
      el("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: css("--rule") }, svg);
      el("text", { x: pad.l - 8, y: y(v) + 4, "text-anchor": "end", fill: css("--ink-2"), "font-size": 13 }, svg, fmt(v, 1));
    }
    years.forEach((yr, i) =>
      el("text", { x: x(i), y: H - 8, "text-anchor": "middle", fill: css("--ink-2"), "font-size": 13 }, svg, yr));

    const order = Object.keys(series).sort((a, b) => (a === PROPOSED) - (b === PROPOSED));
    order.forEach((name) => {
      if (hiddenLines.has(name)) return;
      const colour = modelColour(name);
      const key = name === PROPOSED || name === REFERENCE || name === "Baseline";
      const pts = series[name].map((v, i) => `${x(i)},${y(v)}`).join(" ");
      const line = el("polyline", { points: pts, fill: "none", stroke: colour, "stroke-width": name === PROPOSED ? 3.5 : key ? 2 : 1.6,
        "stroke-dasharray": key ? "" : "4 4", "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
      if (name === PROPOSED) line.setAttribute("filter", glow(svg, colour));
      if (key) drawIn(svg, line);
      series[name].forEach((v, i) => {
        const dot = el("circle", { cx: x(i), cy: y(v), r: name === PROPOSED ? 5 : 3.5, fill: colour,
          stroke: css("--surface"), "stroke-width": 1.5 }, svg);
        withTip(dot, `<b>${name}</b><br>${years[i]} Games: MAE ${fmt(v, 3)}`);
      });
    });

    const keyBox = $("#lines-key");
    if (!keyBox.childElementCount) {
      Object.keys(series).forEach((name) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("aria-pressed", "true");
        btn.innerHTML = `<span class="mk" style="background:${modelColour(name)}"></span>${name}`;
        btn.addEventListener("click", () => {
          if (hiddenLines.has(name)) hiddenLines.delete(name); else hiddenLines.add(name);
          btn.setAttribute("aria-pressed", String(!hiddenLines.has(name)));
          renderLines();
        });
        li.appendChild(btn);
        keyBox.appendChild(li);
      });
    } else {
      keyBox.querySelectorAll(".mk").forEach((mk, i) => { mk.style.background = modelColour(Object.keys(series)[i]); });
    }
  }

  /* ---------- results: model families (count vs momentum) ---------- */
  function renderFamilies() {
    const box = $("#families");
    if (!D.families) { box.closest(".chart").hidden = true; return; }
    const names = [...new Set(D.families.map((r) => r.model))];
    const get = (m, t) => D.families.find((r) => r.model === m && r.target === t);
    const W = Math.max(box.clientWidth, 300);
    const narrow = W < 460;
    const labelW = narrow ? 0 : 200, group = narrow ? 64 : 46, top = 4, bottom = 26;
    const H = top + names.length * group + bottom;
    const svg = svgFor(box, W, H);
    const max = niceMax(Math.max(...D.families.map((r) => r.MAE)) * 1.08, 0.5);
    const x = scale(0, max, labelW, W - 44);
    for (let v = 0; v <= max + 1e-9; v += 0.5) {
      el("line", { x1: x(v), x2: x(v), y1: top, y2: H - bottom, stroke: css("--rule") }, svg);
      el("text", { x: x(v), y: H - 8, "text-anchor": "middle", fill: css("--ink-2"), "font-size": 13 }, svg, fmt(v, 1));
    }
    names.forEach((m, i) => {
      const y0 = top + i * group + (narrow ? 18 : 0);
      if (narrow) el("text", { x: 0, y: y0 - 4, class: "lbl" }, svg, m);
      else el("text", { x: labelW - 12, y: y0 + 19, "text-anchor": "end", class: "lbl" }, svg, m);
      [["Count", css("--other")], ["Momentum", css("--gold")]].forEach(([t, colour], j) => {
        const r = get(m, t);
        const y = y0 + 4 + j * 16;
        if (!r) {
          el("text", { x: x(0) + 4, y: y + 11, fill: css("--ink-2"), "font-size": 12 }, svg, "needs a count target");
          return;
        }
        const bar = el("rect", { x: x(0), y, width: Math.max(x(r.MAE) - x(0), 1), height: 14, rx: 4,
          fill: gradient(svg, colour), class: "bar", style: `animation-delay:${i * 80 + j * 40}ms` }, svg);
        el("text", { x: x(r.MAE) + 5, y: y + 11, class: "val", "font-size": 12 }, svg, fmt(r.MAE, 2));
        withTip(bar, `<b>${m}, predicting ${t === "Count" ? "the count" : "momentum"}</b><br>MAE ${fmt(r.MAE, 3)}, RMSE ${fmt(r.RMSE, 2)}<br>Top-10 MAE ${fmt(r.Top10, 2)}`);
      });
    });
  }

  function renderClassifiers() {
    const table = $("#clf-table");
    if (!D.classifiers) { table.closest(".chart").hidden = true; return; }
    const best = Math.max(...D.classifiers.map((r) => r.acc2016));
    table.innerHTML = `<thead><tr><th scope="col">Classifier</th><th scope="col">2012</th><th scope="col">2016</th><th scope="col">F1 2016</th></tr></thead>
      <tbody>${D.classifiers.map((r) => `<tr><td>${r.model}</td><td>${fmt(100 * r.acc2012, 1)}%</td>
        <td class="${r.acc2016 === best ? "best" : ""}">${fmt(100 * r.acc2016, 1)}%</td><td>${fmt(r.f12016, 3)}</td></tr>`).join("")}</tbody>`;
  }

  /* ---------- Tokyo table ---------- */
  function renderTokyo() {
    const table = $("#tokyo-table");
    if (!D.tokyo) { table.closest(".tokyo").hidden = true; return; }
    const cols = [["MAE", "MAE", 3, "min"], ["RMSE", "RMSE", 2, "min"], ["R2", "R²", 3, "max"], ["Top10_MAE", "Top-10 MAE", 2, "min"]];
    const best = Object.fromEntries(cols.map(([k, , , dir]) => {
      const vals = D.tokyo.map((m) => m[k]);
      return [k, dir === "min" ? Math.min(...vals) : Math.max(...vals)];
    }));
    table.innerHTML = `<thead><tr><th scope="col">Model</th>${cols.map(([, label]) => `<th scope="col">${label}</th>`).join("")}</tr></thead>
      <tbody>${D.tokyo.map((m) => `<tr class="${m.name === PROPOSED ? "ours" : ""}"><td>${m.name}</td>${cols
        .map(([k, , d]) => `<td class="${m[k] === best[k] ? "best" : ""}">${fmt(m[k], d)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  }

  /* ---------- explore a country ---------- */
  const QUICK = ["USA", "China", "UK", "Japan", "India", "Kenya", "Australia", "Brazil"];
  const forecastBy = Object.fromEntries(D.forecast2020.map((r) => [r.country, r]));
  const rioBy = Object.fromEntries(D.predictions2016.map((r) => [r.country, r]));
  const countries = Object.keys(D.history).sort();
  let current = "UK";

  function setupPicker() {
    $("#country-list").innerHTML = countries.map((c) => `<option value="${c}"></option>`).join("");
    const quick = $("#quick");
    QUICK.filter((c) => D.history[c]).forEach((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = c;
      b.addEventListener("click", () => selectCountry(c));
      quick.appendChild(b);
    });
    const input = $("#country");
    input.addEventListener("change", () => {
      const match = countries.find((c) => c.toLowerCase() === input.value.trim().toLowerCase());
      if (match) selectCountry(match);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const q = input.value.trim().toLowerCase();
      const match = countries.find((c) => c.toLowerCase() === q) || countries.find((c) => c.toLowerCase().startsWith(q));
      if (match) selectCountry(match);
    });
  }

  function selectCountry(name) {
    current = name;
    $("#country").value = name;
    document.querySelectorAll("#quick button").forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === name)));
    renderStory();
    renderHistory();
  }

  function renderStory() {
    const f = forecastBy[current];
    const story = $("#story");
    if (!f) { story.textContent = `${current} has no 2020 forecast because it did not compete in Rio 2016.`; return; }
    const pct = (Math.exp(f.change) - 1) * 100;
    const dir = pct >= 0 ? "a rise" : "a fall";
    const actual = f.actual === null ? "" : ` It won <b>${f.actual}</b>.`;
    story.innerHTML = `${current} won <b>${f.previous}</b> medals in Rio 2016. The model predicts momentum of ${dir} of ${fmt(Math.abs(pct), 1)}%, so the Tokyo 2020 forecast was <b>${fmt(f.predicted, 1)}</b>.${actual}`;
  }

  function renderHistory() {
    const box = $("#history");
    const W = Math.max(box.clientWidth, 300);
    const H = Math.round(Math.min(Math.max(W * 0.42, 240), 380));
    const pad = { l: 40, r: 30, t: 16, b: 30 };
    const svg = svgFor(box, W, H);
    const h = D.history[current];
    if (!h) return;
    const f = forecastBy[current];
    const rio = rioBy[current];
    const years = h.years.concat(f && f.actual !== null ? [2020] : []);
    const medals = h.medals.concat(f && f.actual !== null ? [f.actual] : []);
    const x0 = Math.min(1964, years[0]);
    const x = scale(x0, 2020, pad.l, W - pad.r);
    const peaks = [...medals, ...(f ? [f.predicted, f.historical] : []), ...(rio ? [rio[PROPOSED], rio[REFERENCE]] : [])];
    const step = Math.max(...peaks) > 40 ? 20 : Math.max(...peaks) > 12 ? 5 : 1;
    const max = niceMax(Math.max(...peaks, 1) * 1.08, step);
    const y = scale(0, max, H - pad.b, pad.t);
    const ink = css("--ink"), ink2 = css("--ink-2"), rule = css("--rule");

    for (let v = 0; v <= max; v += step) {
      el("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: rule }, svg);
      el("text", { x: pad.l - 8, y: y(v) + 4, "text-anchor": "end", fill: ink2, "font-size": 13 }, svg, v);
    }
    const tickEvery = W < 520 ? 16 : 8;
    for (let yr = 1964; yr <= 2020; yr += tickEvery) {
      el("text", { x: x(yr), y: H - 8, "text-anchor": "middle", fill: ink2, "font-size": 13 }, svg, yr);
    }
    if ((2020 - 1964) % tickEvery) el("text", { x: x(2020), y: H - 8, "text-anchor": "middle", fill: ink2, "font-size": 13 }, svg, 2020);
    // forecast zone
    el("rect", { x: x(2014), y: pad.t, width: x(2020) - x(2014) + 14, height: H - pad.b - pad.t, fill: css("--gold"), opacity: 0.08 }, svg);

    el("polyline", { points: h.years.map((yr, i) => `${x(yr)},${y(h.gold[i])}`).join(" "), fill: "none",
      stroke: css("--gold"), "stroke-width": 2, "stroke-dasharray": "5 4" }, svg);
    const medalLine = el("polyline", { points: years.map((yr, i) => `${x(yr)},${y(medals[i])}`).join(" "), fill: "none",
      stroke: ink, "stroke-width": 2.5, "stroke-linejoin": "round" }, svg);
    drawIn(svg, medalLine);
    years.forEach((yr, i) => {
      const dot = el("circle", { cx: x(yr), cy: y(medals[i]), r: 3.5, fill: ink }, svg);
      const gold = i < h.gold.length ? `, ${h.gold[i]} gold` : "";
      withTip(dot, `<b>${current} ${yr}</b><br>${medals[i]} medals${gold}`);
    });

    const marker = (yr, value, colour, label) => {
      const g = el("g", {}, svg);
      el("circle", { cx: x(yr), cy: y(value), r: 7, fill: colour, stroke: css("--page"), "stroke-width": 2 }, g);
      withTip(g, label);
    };
    if (rio) {
      marker(2016 - 0.7, rio[REFERENCE], css("--silver"), `<b>Rio 2016, historical features</b><br>Forecast ${fmt(rio[REFERENCE], 1)}, actual ${rio.actual}`);
      marker(2016 + 0.7, rio[PROPOSED], css("--gold"), `<b>Rio 2016, our model</b><br>Forecast ${fmt(rio[PROPOSED], 1)}, actual ${rio.actual}`);
    }
    if (f) {
      marker(2020 - 0.7, f.historical, css("--silver"), `<b>Tokyo 2020, historical features</b><br>Forecast ${fmt(f.historical, 1)}${f.actual !== null ? `, actual ${f.actual}` : ""}`);
      marker(2020 + 0.7, f.predicted, css("--gold"), `<b>Tokyo 2020, our model</b><br>Forecast ${fmt(f.predicted, 1)}${f.actual !== null ? `, actual ${f.actual}` : ""}`);
    }
    box.setAttribute("aria-label", `${current}: medals by Games from ${years[0]} to ${years[years.length - 1]}`);
  }

  /* ---------- live predictor (our forest, exported from scikit-learn) ---------- */
  const MODEL = window.MEDAL_MODEL;
  const SLIDERS = ["m1", "g", "a1", "s", "e", "m2", "a2", "m3"];
  const pState = { country: "India", inputs: null, edited: false, shown: 0 };

  // Same feature recipe as src/olympic_momentum/features.py.
  function featureVector(v) {
    const growth = (a, b) => Math.log1p(a) - Math.log1p(b);
    return [
      v.m1, v.g, v.a1, v.s, v.e,
      growth(v.m1, v.m2), growth(v.a1, v.a2),
      (v.m1 + v.m2 + v.m3) / 3,
      v.a1 > 0 ? v.m1 / v.a1 : 0,
    ];
  }

  // Walk every tree exactly as scikit-learn does (float32 inputs, x <= threshold goes left).
  function predictMomentum(x) {
    const xf = x.map(Math.fround);
    let sum = 0;
    for (const t of MODEL.trees) {
      let n = 0;
      while (t.f[n] !== -1) n = xf[t.f[n]] <= t.t[n] ? t.l[n] : t.r[n];
      sum += t.v[n];
    }
    return sum / MODEL.trees.length;
  }

  function forecastFor(v) {
    const change = predictMomentum(featureVector(v));
    return { change, medals: Math.max(0, Math.expm1(Math.log1p(v.m1) + change)) };
  }

  function realInputs(country) {
    const c = MODEL.countries[country];
    // A missing earlier Games is treated like "same as the last one": zero growth,
    // and the rolling average falls back to the medals we have, as in the pipeline.
    const m2 = c.m[1] ?? c.m[0];
    const m3 = c.m[2] ?? (c.m[1] !== null && c.m[1] !== undefined ? (c.m[0] + c.m[1]) / 2 : c.m[0]);
    return { m1: c.m[0], g: c.g, a1: c.a[0], s: c.s, e: c.e, m2, a2: c.a[1] ?? c.a[0], m3 };
  }

  let baseBoard = null;
  function forecastBoard() {
    if (!baseBoard) {
      baseBoard = Object.keys(MODEL.countries).map((c) => ({ country: c, medals: forecastFor(realInputs(c)).medals }));
    }
    return baseBoard;
  }

  function setupPredictor() {
    if (!MODEL) { $("#predict").hidden = true; return; }
    // Small console API, also used by the export check: MedalMomentum.forecast("India")
    window.MedalMomentum = { forecast: (c) => forecastFor(realInputs(c)), features: (c) => featureVector(realInputs(c)) };
    const names = Object.keys(MODEL.countries).sort();
    $("#p-country-list").innerHTML = names.map((c) => `<option value="${c}"></option>`).join("");
    const quick = $("#p-quick");
    ["India", "USA", "China", "Japan", "UK", "Kenya", "Brazil", "Australia"].filter((c) => MODEL.countries[c]).forEach((c) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = c;
      b.addEventListener("click", () => loadCountry(c));
      quick.appendChild(b);
    });
    const input = $("#p-country");
    const pick = () => {
      const q = input.value.trim().toLowerCase();
      const match = names.find((c) => c.toLowerCase() === q) || names.find((c) => c.toLowerCase().startsWith(q));
      if (match && q) loadCountry(match);
    };
    input.addEventListener("change", pick);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") pick(); });
    SLIDERS.forEach((k) => $(`#p-${k}`).addEventListener("input", (e) => {
      pState.inputs[k] = Number(e.target.value);
      if (k === "m1" && pState.inputs.g > pState.inputs.m1) { pState.inputs.g = pState.inputs.m1; $("#p-g").value = pState.inputs.g; }
      if (k === "g" && pState.inputs.g > pState.inputs.m1) { pState.inputs.m1 = pState.inputs.g; $("#p-m1").value = pState.inputs.m1; }
      pState.edited = true;
      renderPrediction();
    }));
    $("#p-reset").addEventListener("click", () => loadCountry(pState.country));
    loadCountry(pState.country);
  }

  function loadCountry(country) {
    pState.country = country;
    pState.inputs = realInputs(country);
    pState.edited = false;
    $("#p-country").value = country;
    document.querySelectorAll("#p-quick button").forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === country)));
    SLIDERS.forEach((k) => {
      const el2 = $(`#p-${k}`);
      el2.max = Math.max(Number(el2.max), Math.ceil(pState.inputs[k]));
      el2.value = pState.inputs[k];
    });
    renderPrediction();
  }

  function animateNumber(node, from, to) {
    if (reduceMotion) { node.textContent = fmt(to, 1); return; }
    const start = performance.now(), dur = 380;
    const step = (now) => {
      const k = Math.min(1, (now - start) / dur), e = 1 - Math.pow(1 - k, 3);
      node.textContent = fmt(from + (to - from) * e, 1);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function renderPrediction() {
    const v = pState.inputs;
    SLIDERS.forEach((k) => { $(`#o-${k}`).textContent = Math.round(v[k]); });
    const { change, medals } = forecastFor(v);
    animateNumber($("#p-result"), pState.shown, medals);
    pState.shown = medals;

    $("#p-title").textContent = pState.edited ? `${pState.country}, with your changes` : `${pState.country}, Tokyo 2020 forecast`;
    const pct = (Math.exp(change) - 1) * 100;
    const pill = $("#p-change");
    pill.className = `pill ${pct > 0.5 ? "pill--up" : pct < -0.5 ? "pill--down" : "pill--flat"}`;
    pill.textContent = `${pct >= 0 ? "+" : "−"}${fmt(Math.abs(pct), 1)}% momentum`;

    const actual = (D.forecast2020.find((r) => r.country === pState.country) || {}).actual;
    const rows = [["Last Games", v.m1, css("--silver")], ["Our forecast", medals, css("--gold")]];
    if (actual !== null && actual !== undefined) rows.push(["Actual, Tokyo 2020", actual, css("--o-blue")]);
    const max = Math.max(...rows.map((r) => r[1]), 1) * 1.08;
    $("#p-compare").innerHTML = rows.map(([label, value, colour]) =>
      `<div class="cmp"><span>${label}</span><span class="cmp__bar"><i style="width:${(100 * value / max).toFixed(1)}%;background:${colour}"></i></span><b>${fmt(value, value % 1 ? 1 : 0)}</b></div>`).join("");

    const board = forecastBoard().map((r) => (r.country === pState.country ? { ...r, medals } : r))
      .sort((a, b) => b.medals - a.medals);
    const rank = board.findIndex((r) => r.country === pState.country);
    const from = Math.max(0, Math.min(rank - 2, board.length - 5));
    const medalColour = [css("--gold"), css("--silver"), css("--bronze")];
    $("#p-board").innerHTML = board.slice(from, from + 5).map((r, i) => {
      const pos = from + i;
      const dot = pos < 3 ? `<span class="medal-dot" style="background:${medalColour[pos]}"></span>` : "";
      return `<li class="${pos === rank ? "you" : ""}"><span class="rk">${pos + 1}</span><span>${dot}${r.country}</span><span>${fmt(r.medals, 1)}</span></li>`;
    }).join("");

    renderPodium(board, rank);

    $("#p-foot").textContent = `forecast = (1 + ${Math.round(v.m1)}) × e^(${change >= 0 ? "" : "−"}${fmt(Math.abs(change), 3)}) − 1 = ${fmt(medals, 1)} medals. The ranking uses this browser model for all ${board.length} countries.`;
  }

  function renderPodium(board, rank) {
    const slots = [[1, "pod--2"], [0, "pod--1"], [2, "pod--3"]];
    $("#p-podium").innerHTML = slots.map(([i, cls]) => {
      const r = board[i];
      const you = r.country === pState.country;
      return `<div class="pod ${cls}${you ? " you" : ""}">${you ? '<span class="you-tag">You</span>' : ""}
        <span class="pod__name" title="${r.country}">${r.country}</span>
        <span class="pod__val">${fmt(r.medals, 1)} medals</span><div class="pod__step">${i + 1}</div></div>`;
    }).join("");

    // Log scale, so climbing from #40 to #20 is as visible as #4 to #2.
    const n = board.length;
    const pos = 100 * (1 - Math.log(rank + 1) / Math.log(n));
    const track = $("#p-rank");
    if (!track.firstChild) {
      track.innerHTML = `<div class="ranktrack__label"></div><div class="ranktrack__bar"></div><div class="ranktrack__dot"></div>
        <div class="ranktrack__ends"><span>#${n}</span><span>#1</span></div>`;
    }
    track.querySelector(".ranktrack__dot").style.left = `${pos}%`;
    const label = track.querySelector(".ranktrack__label");
    label.style.left = `${Math.min(88, Math.max(12, pos))}%`;
    label.textContent = `${pState.country}: #${rank + 1} of ${n}`;
  }

  /* ---------- first-view animations ---------- */
  function setupAnimations() {
    const oval = document.querySelector(".hero__oval");
    if (reduceMotion) {
      oval?.querySelectorAll("animateMotion").forEach((a) => a.remove());
      oval?.querySelectorAll(".runner").forEach((c) => c.remove());
      return;
    }
    document.querySelectorAll(".chip b [data-k], .chip b[data-k]").forEach((node, i) => countUp(node, 350 + i * 80));
    if (!("IntersectionObserver" in window)) return;
    const renderers = { bars: renderBars, lines: renderLines, families: renderFamilies, history: renderHistory };
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      if (e.target.id in renderers) {
        e.target.dataset.anim = "go";
        renderers[e.target.id]();
      } else {
        e.target.querySelectorAll(".num").forEach((node, i) => countUp(node, i * 120));
      }
    }), { threshold: 0.15 });
    Object.keys(renderers).forEach((id) => io.observe($(`#${id}`)));
    io.observe($("#findings"));
  }

  /* ---------- render ---------- */
  function renderAll(animate = true) {
    if (!animate) raceState.animate = false;
    renderRace();
    renderBars();
    renderLines();
    renderFamilies();
    renderHistory();
  }

  fillFindings();
  renderTokyo();
  renderClassifiers();
  setupPredictor();
  setupPicker();
  selectCountry(current);
  renderAll();
  setupAnimations();

  let resizeTimer;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderAll(false), 150);
  });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => renderAll(false));
})();
