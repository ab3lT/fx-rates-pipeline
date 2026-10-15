(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { base: "USD", latest: [], quote: null, days: 90, chart: null };

  const nf = new Intl.NumberFormat(undefined);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function getJSON(url) {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`${url} → ${res.status}`);
    return res.json();
  }

  function fmtRate(v) {
    if (v == null) return "—";
    const digits = v >= 100 ? 2 : v >= 1 ? 4 : 5;
    return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function fmtPct(v) {
    if (v == null || Number.isNaN(v)) return { text: "—", cls: "flat" };
    const cls = v > 0.0001 ? "up" : v < -0.0001 ? "down" : "flat";
    const sign = v > 0 ? "+" : "";
    return { text: `${sign}${v.toFixed(2)}%`, cls };
  }

  function timeAgo(iso) {
    if (!iso) return "—";
    const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (secs < 60) return "just now";
    const units = [["day", 86400], ["hour", 3600], ["minute", 60]];
    for (const [name, size] of units) {
      const n = Math.floor(secs / size);
      if (n >= 1) return `${n} ${name}${n > 1 ? "s" : ""} ago`;
    }
    return "just now";
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    return new Date(iso + (iso.length === 10 ? "T00:00:00" : "")).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function fmtDateTime(iso) {
    return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // ---------- Summary ----------
  async function loadSummary() {
    const s = await getJSON("/api/summary");
    state.base = s.base_currency;
    $("kpi-rows").textContent = nf.format(s.total_rows);
    $("kpi-coverage").textContent = s.first_date ? `${fmtDate(s.first_date)} – ${fmtDate(s.last_date)}` : "—";
    $("kpi-coverage").style.fontSize = s.first_date ? "16px" : "";
    $("kpi-runs").textContent = nf.format(s.total_runs);
    $("kpi-success").textContent = s.success_rate == null ? "—" : `${s.success_rate}%`;

    const hrs = s.schedule_hours;
    $("status-schedule").textContent = `Every ${hrs} hour${hrs === 1 ? "" : "s"}`;
    $("status-base").textContent = s.base_currency;

    const dot = $("status-dot");
    const run = s.last_run;
    if (!run) {
      dot.className = "dot";
      $("status-text").textContent = "Waiting for first run";
      $("status-last").textContent = "—";
    } else {
      const map = { success: ["ok", "Pipeline healthy"], warning: ["warn", "Healthy, with warnings"], failed: ["fail", "Last run failed"], running: ["", "Run in progress"] };
      const [cls, label] = map[run.status] || ["", run.status];
      dot.className = `dot ${cls}`;
      $("status-text").textContent = label;
      $("status-last").textContent = timeAgo(run.finished_at || run.started_at);
      $("status-last").title = new Date(run.started_at).toLocaleString();
    }
  }

  // ---------- Latest tiles ----------
  async function loadLatest() {
    state.latest = await getJSON("/api/latest");
    const tiles = $("tiles");
    if (!state.latest.length) {
      tiles.innerHTML = `<p class="muted">No data yet. The scheduler fills in history on its first run.</p>`;
      return;
    }
    const newest = state.latest.reduce((a, b) => (a.rate_date > b.rate_date ? a : b));
    $("latest-date").textContent = `As of ${fmtDate(newest.rate_date)}`;
    if (!state.quote || !state.latest.some((r) => r.quote_currency === state.quote)) {
      state.quote = (state.latest.find((r) => r.quote_currency === "EUR") || state.latest[0]).quote_currency;
    }
    tiles.innerHTML = state.latest.map((r) => {
      const p = fmtPct(r.pct_change);
      return `<button class="tile${r.quote_currency === state.quote ? " active" : ""}" data-quote="${esc(r.quote_currency)}">
        <span class="tile-pair">${esc(r.base_currency)} / ${esc(r.quote_currency)}</span>
        <span class="tile-rate">${fmtRate(r.rate)}</span>
        <span class="chg ${p.cls}">${p.text}</span>
      </button>`;
    }).join("");
    tiles.querySelectorAll(".tile").forEach((el) => el.addEventListener("click", () => selectQuote(el.dataset.quote)));
    setupConverter();
  }

  function selectQuote(q) {
    state.quote = q;
    document.querySelectorAll(".tile").forEach((el) => el.classList.toggle("active", el.dataset.quote === q));
    loadChart();
  }

  // ---------- Chart ----------
  async function loadChart() {
    if (!state.quote) return;
    const data = await getJSON(`/api/rates?quote=${encodeURIComponent(state.quote)}&days=${state.days}`);
    const pts = data.points;
    $("chart-title").textContent = `${state.base} / ${state.quote}`;
    if (pts.length) {
      const first = pts[0].rate, last = pts[pts.length - 1].rate;
      const p = fmtPct(((last - first) / first) * 100);
      $("chart-sub").innerHTML = `${pts.length} observations · <span class="chg ${p.cls}">${p.text}</span> over the period`;
    } else {
      $("chart-sub").textContent = "No observations in this window";
    }

    if (typeof Chart === "undefined") return;
    const accent = cssVar("--accent");
    const muted = cssVar("--muted");
    const border = cssVar("--border");
    const ctx = $("chart").getContext("2d");
    const grad = ctx.createLinearGradient(0, 0, 0, 320);
    grad.addColorStop(0, accent + "33");
    grad.addColorStop(1, accent + "00");

    const cfg = {
      type: "line",
      data: {
        labels: pts.map((p) => p.date),
        datasets: [{ data: pts.map((p) => p.rate), borderColor: accent, backgroundColor: grad, fill: true, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.25 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              title: (items) => fmtDate(items[0].label),
              label: (item) => {
                const pc = pts[item.dataIndex].pct_change;
                return [`${fmtRate(item.parsed.y)} ${state.quote}`, pc == null ? "" : `Day change ${fmtPct(pc).text}`].filter(Boolean);
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: muted, maxTicksLimit: 6, maxRotation: 0, callback: function (v) { return new Date(this.getLabelForValue(v) + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }); } }, grid: { display: false }, border: { color: border } },
          y: { ticks: { color: muted, callback: (v) => fmtRate(v) }, grid: { color: border }, border: { display: false } },
        },
      },
    };
    if (state.chart) state.chart.destroy();
    state.chart = new Chart(ctx, cfg);
  }

  $("range").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-days]");
    if (!btn) return;
    state.days = Number(btn.dataset.days);
    $("range").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
    loadChart();
  });

  // ---------- Converter ----------
  let converterReady = false;
  function setupConverter() {
    const codes = [state.base, ...state.latest.map((r) => r.quote_currency)];
    const from = $("conv-from"), to = $("conv-to");
    const prevFrom = from.value, prevTo = to.value;
    const opts = codes.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    from.innerHTML = opts;
    to.innerHTML = opts;
    from.value = codes.includes(prevFrom) ? prevFrom : state.base;
    to.value = codes.includes(prevTo) ? prevTo : (codes.find((c) => c === "EUR") || codes[1] || state.base);
    if (!converterReady) {
      ["input", "change"].forEach((ev) => { $("conv-amount").addEventListener(ev, convert); from.addEventListener(ev, convert); to.addEventListener(ev, convert); });
      $("conv-swap").addEventListener("click", () => { const f = from.value; from.value = to.value; to.value = f; convert(); });
      converterReady = true;
    }
    convert();
  }

  function rateFor(code) {
    if (code === state.base) return 1;
    const r = state.latest.find((x) => x.quote_currency === code);
    return r ? r.rate : null;
  }

  function convert() {
    const amount = parseFloat($("conv-amount").value);
    const f = $("conv-from").value, t = $("conv-to").value;
    const rf = rateFor(f), rt = rateFor(t);
    if (!rf || !rt || Number.isNaN(amount)) { $("conv-result").textContent = "—"; $("conv-rate").textContent = ""; return; }
    const cross = rt / rf;
    $("conv-result").textContent = `${(amount * cross).toLocaleString(undefined, { maximumFractionDigits: 4 })} ${t}`;
    $("conv-rate").textContent = `1 ${f} = ${fmtRate(cross)} ${t}`;
  }

  // ---------- Runs ----------
  function checkIcon(c) {
    if (c.passed) return `<span class="ico ok">✓</span>`;
    return c.critical ? `<span class="ico bad">✕</span>` : `<span class="ico warn">!</span>`;
  }

  async function loadRuns() {
    const runs = await getJSON("/api/runs?limit=15");
    const body = $("runs-body");
    if (!runs.length) {
      body.innerHTML = `<tr><td colspan="6" class="muted">No runs recorded yet.</td></tr>`;
      return;
    }
    body.innerHTML = runs.map((r) => {
      const checks = (r.checks || []).map((c) => `<li>${checkIcon(c)}<span>${esc(c.name.replace(/_/g, " "))} <code>${esc(c.detail)}</code></span></li>`).join("");
      const err = r.error ? `<p class="run-error">${esc(r.error)}</p>` : "";
      const span = r.start_date ? `${fmtDate(r.start_date)} → ${fmtDate(r.end_date)}` : "—";
      return `<tr class="run-row" data-id="${r.id}" tabindex="0" aria-expanded="false">
          <td title="${esc(new Date(r.started_at).toLocaleString())}">${fmtDateTime(r.started_at)}</td>
          <td><span class="tag">${esc(r.trigger)}</span></td>
          <td>${span}</td>
          <td><span class="badge ${esc(r.status)}">${esc(r.status)}</span></td>
          <td class="num">${nf.format(r.rows_loaded)}</td>
          <td class="num">${r.duration_seconds == null ? "—" : r.duration_seconds.toFixed(2) + "s"}</td>
        </tr>
        <tr class="detail" data-for="${r.id}" hidden><td colspan="6">${checks ? `<ul class="checks">${checks}</ul>` : `<span class="muted small">No quality report for this run.</span>`}${err}</td></tr>`;
    }).join("");
    body.querySelectorAll(".run-row").forEach((row) => {
      const toggle = () => {
        const d = body.querySelector(`tr.detail[data-for="${row.dataset.id}"]`);
        d.hidden = !d.hidden;
        row.setAttribute("aria-expanded", String(!d.hidden));
      };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    });
  }

  // ---------- Boot ----------
  async function refresh() {
    const results = await Promise.allSettled([loadSummary(), loadLatest().then(loadChart), loadRuns()]);
    results.filter((r) => r.status === "rejected").forEach((r) => console.error(r.reason));
  }

  refresh();
  setInterval(refresh, 5 * 60 * 1000);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", loadChart);
})();
