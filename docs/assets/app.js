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
    return el("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "presentation" }, container);
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
      const bar = el("rect", { x: x(0), y: y + 7, width: Math.max(x(r.MAE_mean) - x(0), 1), height: rowH - 14, rx: 4,
        fill: modelColour(r.name) }, svg);
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
      el("polyline", { points: pts, fill: "none", stroke: colour, "stroke-width": name === PROPOSED ? 3.5 : key ? 2 : 1.6,
        "stroke-dasharray": key ? "" : "4 4", "stroke-linejoin": "round" }, svg);
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
    el("polyline", { points: years.map((yr, i) => `${x(yr)},${y(medals[i])}`).join(" "), fill: "none",
      stroke: ink, "stroke-width": 2.5, "stroke-linejoin": "round" }, svg);
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

  /* ---------- render ---------- */
  function renderAll(animate = true) {
    if (!animate) raceState.animate = false;
    renderRace();
    renderBars();
    renderLines();
    renderHistory();
  }

  fillFindings();
  renderTokyo();
  setupPicker();
  selectCountry(current);
  renderAll();

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
