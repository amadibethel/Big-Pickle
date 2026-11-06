/* ============================================================
   Counter — dashboard logic
   ============================================================ */

(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const PALETTE = ["#a9d63f", "#5b8fd6", "#e0a63a", "#8d7bd8", "#d97f9f", "#5fb69a", "#c0855c"];

  const state = {
    view: "overview",
    preset: "30d",
    start: "",
    end: "",
    channel: "",
    category: "",
    q: "",
    currency: localStorage.getItem("counter-currency") || "USD",
    page: 1,
    pageSize: 15,
    meta: null,
    summary: null,
    sales: [],
    importRows: [],
    importSkipped: 0,
    editingId: null,
    confirmAction: null,
  };

  const els = {
    startDate: $("#startDate"),
    endDate: $("#endDate"),
    channelFilter: $("#channelFilter"),
    categoryFilter: $("#categoryFilter"),
    currency: $("#currency"),
    presetList: $("#presetList"),
    searchInput: $("#searchInput"),
    demoBanner: $("#demoBanner"),
    emptyState: $("#emptyState"),
    emptyTitle: $("#emptyTitle"),
    emptyText: $("#emptyText"),
    emptyAdd: $("#emptyAdd"),
    emptySample: $("#emptySample"),
    overviewContent: $("#overviewContent"),
    kpiGrid: $("#kpiGrid"),
    revenueChart: $("#revenueChart"),
    chartTip: $("#chartTip"),
    chartCaption: $("#chartCaption"),
    rangeBadge: $("#rangeBadge"),
    donutChart: $("#donutChart"),
    donutLegend: $("#donutLegend"),
    topProducts: $("#topProducts"),
    recentSales: $("#recentSales"),
    salesBody: $("#salesBody"),
    salesTable: $(".sales-table"),
    tableEmpty: $("#tableEmpty"),
    resultCount: $("#resultCount"),
    pageInfo: $("#pageInfo"),
    pageLabel: $("#pageLabel"),
    prevPage: $("#prevPage"),
    nextPage: $("#nextPage"),
    dataCount: $("#dataCount"),
    dataPath: $("#dataPath"),
    dataUpdated: $("#dataUpdated"),
    dataBlurb: $("#dataBlurb"),
    dbChipLabel: $("#dbChipLabel"),
    dbState: $("#dbState"),
    dbDetail: $("#dbDetail"),
    statusDot: $("#statusDot"),
    viewEyebrow: $("#viewEyebrow"),
    viewTitle: $("#viewTitle"),
    viewSubtitle: $("#viewSubtitle"),
    footRange: $("#footRange"),
    sampleBtn: $("#sampleBtn"),
    saleModal: $("#saleModal"),
    saleForm: $("#saleForm"),
    saleModalTitle: $("#saleModalTitle"),
    saleModalEyebrow: $("#saleModalEyebrow"),
    saleDate: $("#saleDate"),
    saleProduct: $("#saleProduct"),
    saleCategory: $("#saleCategory"),
    saleChannel: $("#saleChannel"),
    saleUnits: $("#saleUnits"),
    salePrice: $("#salePrice"),
    saleCustomer: $("#saleCustomer"),
    saleNotes: $("#saleNotes"),
    saleTotalPreview: $("#saleTotalPreview"),
    saleError: $("#saleError"),
    saveSale: $("#saveSale"),
    priceSymbol: $("#priceSymbol"),
    confirmModal: $("#confirmModal"),
    confirmTitle: $("#confirmTitle"),
    confirmMessage: $("#confirmMessage"),
    confirmClose: $("#confirmClose"),
    confirmOk: $("#confirmOk"),
    confirmCancel: $("#confirmCancel"),
    toastStack: $("#toastStack"),
    dropzone: $("#dropzone"),
    fileInput: $("#fileInput"),
    importPreview: $("#importPreview"),
    importResult: $("#importResult"),
    previewTitle: $("#previewTitle"),
    previewNote: $("#previewNote"),
    previewTable: $("#previewTable"),
    confirmImport: $("#confirmImport"),
    categoryOptions: $("#categoryOptions"),
    channelOptions: $("#channelOptions"),
    productOptions: $("#productOptions"),
  };

  /* ------------------------------------------------------------ helpers */

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function isoDate(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, "0");
    const d = String(dateObj.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function parseISO(value) {
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  function addDays(dateObj, days) {
    const copy = new Date(dateObj);
    copy.setDate(copy.getDate() + days);
    return copy;
  }

  function daysBetween(start, end) {
    return Math.round((parseISO(end) - parseISO(start)) / 86400000) + 1;
  }

  const moneyCache = new Map();

  function fmtMoney(value, compact = false) {
    const currency = state.currency;
    const key = `${currency}:${compact ? "compact" : "full"}`;
    if (!moneyCache.has(key)) {
      const options = {
        style: "currency",
        currency,
        notation: compact ? "compact" : "standard",
        maximumFractionDigits: compact ? 1 : ["JPY", "KRW", "VND"].includes(currency) ? 0 : 2,
      };
      if (!compact) options.minimumFractionDigits = options.maximumFractionDigits;
      moneyCache.set(key, new Intl.NumberFormat(undefined, options));
    }
    return moneyCache.get(key).format(Number(value) || 0);
  }

  function currencySymbol() {
    try {
      const parts = new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: state.currency,
        currencyDisplay: "narrowSymbol",
      }).formatToParts(0);
      return (parts.find((p) => p.type === "currency") || {}).value || state.currency;
    } catch {
      return state.currency;
    }
  }

  function fmtDay(value) {
    if (!value) return "—";
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(parseISO(value));
  }

  function fmtFullDay(value) {
    if (!value) return "—";
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(parseISO(value));
  }

  function fmtBucket(value, granularity) {
    const dateObj = parseISO(value);
    if (granularity === "month") {
      return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(dateObj);
    }
    if (granularity === "week") {
      return `Week of ${new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(dateObj)}`;
    }
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(dateObj);
  }

  function rangeLabel() {
    const { start, end } = state;
    if (!start && !end) return "All time";
    if (start && !end) return `Since ${fmtFullDay(start)}`;
    if (!start && end) return `Through ${fmtFullDay(end)}`;
    if (start === end) return fmtFullDay(start);
    const startObj = parseISO(start);
    const endObj = parseISO(end);
    const sameYear = startObj.getFullYear() === endObj.getFullYear();
    const left = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      ...(sameYear ? {} : { year: "numeric" }),
    }).format(startObj);
    const right = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(endObj);
    return `${left} – ${right}`;
  }

  function timeAgo(iso) {
    if (!iso) return "—";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "—";
    const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
    if (seconds < 45) return "Just now";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} hr${hours === 1 ? "" : "s"} ago`;
    const days = Math.round(hours / 24);
    if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
    return fmtFullDay(iso.slice(0, 10));
  }

  function channelClass(channel) {
    const slug = String(channel).toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "");
    return ["online", "in-store", "wholesale", "marketplace"].includes(slug)
      ? `channel-${slug}`
      : "channel-other";
  }

  function debounce(fn, wait) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  function setBusy(isBusy) {
    document.body.classList.toggle("is-busy", isBusy);
  }

  function toast(message, type = "success") {
    const node = document.createElement("div");
    node.className = `toast${type === "error" ? " is-error" : ""}`;
    node.innerHTML = `
      <span class="toast-icon"><svg><use href="#${type === "error" ? "i-close" : "i-check"}"/></svg></span>
      <span>${esc(message)}</span>`;
    els.toastStack.appendChild(node);
    setTimeout(() => {
      node.classList.add("is-leaving");
      setTimeout(() => node.remove(), 220);
    }, 3800);
  }

  /* Local and cloud builds both call /api?route=…  — Vercel maps that to a
     single serverless function, and server.py understands the same form. */
  function apiURL(path) {
    const url = new URL(path, window.location.origin);
    if (url.pathname === "/api" || url.pathname === "/api/") {
      return url.pathname + url.search;
    }
    const route = url.pathname.replace(/^\/api\/?/, "");
    const params = new URLSearchParams(url.search);
    params.set("route", route);
    return `/api?${params.toString()}`;
  }

  async function api(path, options = {}) {
    const response = await fetch(apiURL(path), {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    if (!response.ok) {
      const details = Array.isArray(data?.details) ? data.details.join(" · ") : "";
      throw new Error(details || data?.error || `Request failed (${response.status})`);
    }
    return data;
  }

  function filterParams(includeSearch = false) {
    const params = new URLSearchParams();
    if (state.start) params.set("start", state.start);
    if (state.end) params.set("end", state.end);
    if (state.channel) params.set("channel", state.channel);
    if (includeSearch && state.q) params.set("q", state.q);
    if (includeSearch && state.category) params.set("category", state.category);
    return params;
  }

  /* ------------------------------------------------------------ data loading */

  let refreshToken = 0;

  async function refresh() {
    const token = ++refreshToken;
    setBusy(true);
    const summaryParams = filterParams(false).toString();
    const salesParams = filterParams(true).toString();
    try {
      const [meta, summary, sales] = await Promise.all([
        api("/api/meta"),
        api(`/api/summary?${summaryParams}`),
        api(`/api/sales?${salesParams}`),
      ]);
      if (token !== refreshToken) return;
      state.meta = meta;
      state.summary = summary;
      state.sales = sales.items || [];
      renderAll();
    } catch (error) {
      if (token !== refreshToken) return;
      els.dbState.textContent = "Can't reach the server";
      els.dbDetail.textContent = "Start server.py and refresh";
      els.statusDot.classList.add("is-error");
      toast(error.message, "error");
    } finally {
      if (token === refreshToken) setBusy(false);
    }
  }

  let salesToken = 0;

  async function refreshSales() {
    const token = ++salesToken;
    try {
      const data = await api(`/api/sales?${filterParams(true).toString()}`);
      if (token !== salesToken) return;
      state.sales = data.items || [];
      renderTransactions();
      updateHeading();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  /* ------------------------------------------------------------ date presets */

  function applyPreset(preset, reload = true) {
    state.preset = preset;
    const today = new Date();
    if (preset === "all") {
      state.start = "";
      state.end = "";
    } else if (preset === "ytd") {
      state.start = isoDate(new Date(today.getFullYear(), 0, 1));
      state.end = isoDate(today);
    } else {
      const days = { "7d": 7, "30d": 30, "90d": 90 }[preset] || 30;
      state.start = isoDate(addDays(today, -(days - 1)));
      state.end = isoDate(today);
    }
    syncDateInputs();
    updatePresetButtons();
    if (reload) {
      state.page = 1;
      refresh();
    }
  }

  function syncDateInputs() {
    els.startDate.value = state.start;
    els.endDate.value = state.end;
  }

  function updatePresetButtons() {
    $$("#presetList button").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.preset === state.preset);
    });
  }

  function onCustomDateChange(source) {
    let start = els.startDate.value;
    let end = els.endDate.value;
    if (start && end && start > end) {
      // Move the other end of the range instead of silently swapping the dates.
      if (source === "start") end = start;
      else start = end;
      els.startDate.value = start;
      els.endDate.value = end;
    }
    state.start = start;
    state.end = end;
    state.preset = "custom";
    updatePresetButtons();
    state.page = 1;
    refresh();
  }

  /* ------------------------------------------------------------ meta / options */

  function syncMetaOptions() {
    const meta = state.meta;
    if (!meta) return;

    const channels = meta.channels || [];
    if (state.channel && !channels.includes(state.channel)) state.channel = "";
    els.channelFilter.innerHTML =
      `<option value="">All channels</option>` +
      channels.map((channel) => `<option value="${esc(channel)}">${esc(channel)}</option>`).join("");
    els.channelFilter.value = state.channel;

    const categories = meta.categories || [];
    if (state.category && !categories.includes(state.category)) state.category = "";
    els.categoryFilter.innerHTML =
      `<option value="">All categories</option>` +
      categories.map((category) => `<option value="${esc(category)}">${esc(category)}</option>`).join("");
    els.categoryFilter.value = state.category;

    els.categoryOptions.innerHTML = categories
      .map((category) => `<option value="${esc(category)}"></option>`)
      .join("");

    const knownChannels = Array.from(new Set(["Online", "In-store", "Wholesale", "Marketplace", ...channels]));
    els.channelOptions.innerHTML = knownChannels
      .map((channel) => `<option value="${esc(channel)}"></option>`)
      .join("");

    const products = Array.from(
      new Set([...(meta.products || []), ...(state.sales || []).map((sale) => sale.product)])
    ).sort((a, b) => a.localeCompare(b));
    els.productOptions.innerHTML = products
      .slice(0, 400)
      .map((product) => `<option value="${esc(product)}"></option>`)
      .join("");

    els.dataCount.textContent = `${meta.total} sale${meta.total === 1 ? "" : "s"}`;
    els.dataPath.textContent = meta.db_path || "sales.db";
    els.dataUpdated.textContent = timeAgo(meta.updated_at);
    els.dataBlurb.textContent = meta.cloud
      ? "A hosted Postgres database, available wherever you sign in."
      : "A single SQLite file on this computer.";
    els.dbChipLabel.textContent = meta.cloud ? "Cloud" : "Local";
    els.sampleBtn.disabled = meta.total > 0;
    els.sampleBtn.title = meta.total > 0
      ? "Sample data can only be loaded when the database is empty."
      : "Load 320 realistic demo sales to explore the dashboard.";
    $("#clearAllBtn").disabled = meta.total === 0;
    els.dbState.textContent = "Connected";
    els.dbDetail.textContent = `${meta.total} sale${meta.total === 1 ? "" : "s"} stored ${meta.cloud ? "in the cloud" : "locally"}`;
    els.statusDot.classList.remove("is-error");

    renderDemoBanner();
  }

  function renderDemoBanner() {
    const show =
      state.meta &&
      state.meta.demo &&
      state.meta.total > 0 &&
      localStorage.getItem("counter-demo-dismissed") !== "1";
    els.demoBanner.classList.toggle("hidden", !show);
  }

  /* ------------------------------------------------------------ rendering */

  function renderAll() {
    renderOverview();
    renderTransactions();
    updateHeading();
    syncMetaOptions();
  }

  function updateHeading() {
    const meta = {
      overview: { eyebrow: "Dashboard", title: "Sales overview" },
      transactions: { eyebrow: "Sales", title: "Transactions" },
      import: { eyebrow: "Data", title: "Import & data" },
    }[state.view];

    els.viewEyebrow.textContent = meta.eyebrow;
    els.viewTitle.textContent = meta.title;

    let subtitle = "";
    if (state.view === "overview" && state.summary) {
      const totals = state.summary.totals;
      subtitle = `${rangeLabel()} · ${totals.sales} sale${totals.sales === 1 ? "" : "s"} · ${fmtMoney(totals.revenue)} revenue`;
    } else if (state.view === "transactions") {
      const revenue = state.sales.reduce((sum, sale) => sum + sale.total, 0);
      subtitle = `${state.sales.length} sale${state.sales.length === 1 ? "" : "s"} · ${fmtMoney(revenue)} · ${rangeLabel()}`;
    } else {
      subtitle = "Bring your sales in, or take them out.";
    }
    els.viewSubtitle.textContent = subtitle;
    els.footRange.textContent = `${rangeLabel()}${state.channel ? ` · ${state.channel}` : ""}`;
  }

  function deltaHTML(change) {
    if (change === null || change === undefined) {
      return `<span class="delta flat">—</span><span>no prior data</span>`;
    }
    const rounded = Math.abs(change);
    const dir = change > 0 ? "up" : change < 0 ? "down" : "flat";
    const arrow = change === 0 ? "" : `<svg><use href="#i-arrow-up"/></svg>`;
    return `<span class="delta ${dir}">${arrow}${rounded.toFixed(1)}%</span><span>vs previous period</span>`;
  }

  function renderOverview() {
    const summary = state.summary;
    const meta = state.meta;
    if (!summary || !meta) return;

    const globalEmpty = meta.total === 0;
    const periodEmpty = !globalEmpty && summary.totals.sales === 0;

    if (globalEmpty || periodEmpty) {
      els.emptyState.classList.remove("hidden");
      els.overviewContent.classList.add("hidden");
      if (globalEmpty) {
        els.emptyTitle.textContent = "No sales yet";
        els.emptyText.textContent =
          "Add your first sale, import a CSV, or load sample data to see how Counter works.";
        els.emptySample.textContent = "Load sample data";
      } else {
        els.emptyTitle.textContent = "No sales in this period";
        els.emptyText.textContent =
          "There are no sales in the selected dates or channel. Try a longer range or clear the channel filter.";
        els.emptySample.textContent = "Show all time";
      }
      return;
    }

    els.emptyState.classList.add("hidden");
    els.overviewContent.classList.remove("hidden");

    const totals = summary.totals;
    const changes = summary.changes;

    els.kpiGrid.innerHTML = `
      <article class="kpi">
        <div class="kpi-top">
          <span class="kpi-label">Revenue</span>
          <span class="kpi-icon"><svg><use href="#i-arrow-up"/></svg></span>
        </div>
        <div class="kpi-value">${fmtMoney(totals.revenue)}</div>
        <div class="kpi-foot">${deltaHTML(changes.revenue)}</div>
      </article>
      <article class="kpi">
        <div class="kpi-top">
          <span class="kpi-label">Sales</span>
          <span class="kpi-icon"><svg><use href="#i-receipt"/></svg></span>
        </div>
        <div class="kpi-value">${totals.sales.toLocaleString()}</div>
        <div class="kpi-foot">${deltaHTML(changes.sales)}</div>
      </article>
      <article class="kpi">
        <div class="kpi-top">
          <span class="kpi-label">Units sold</span>
          <span class="kpi-icon"><svg><use href="#i-overview"/></svg></span>
        </div>
        <div class="kpi-value">${totals.units.toLocaleString()}</div>
        <div class="kpi-foot">${deltaHTML(changes.units)}</div>
      </article>
      <article class="kpi">
        <div class="kpi-top">
          <span class="kpi-label">Avg. sale</span>
          <span class="kpi-icon"><svg><use href="#i-sparkle"/></svg></span>
        </div>
        <div class="kpi-value">${fmtMoney(totals.avg)}</div>
        <div class="kpi-foot">${deltaHTML(changes.avg)}</div>
      </article>`;

    const granularity = summary.series.granularity;
    const granLabel = { day: "Daily", week: "Weekly", month: "Monthly" }[granularity] || "Daily";
    const best = summary.best_day;
    els.chartCaption.textContent = best
      ? `${granLabel} revenue · best day ${fmtDay(best.date)} (${fmtMoney(best.revenue, true)})`
      : `${granLabel} revenue for the selected period`;

    if (state.start && state.end) {
      const count = daysBetween(state.start, state.end);
      els.rangeBadge.textContent = `${count} day${count === 1 ? "" : "s"}`;
    } else {
      els.rangeBadge.textContent = "All time";
    }

    renderChart();
    renderDonut();
    renderTopProducts();
    renderRecent();
  }

  function renderTopProducts() {
    const products = state.summary.products.slice(0, 5);
    if (!products.length) {
      els.topProducts.innerHTML = `<div class="list-empty">No product data in this period.</div>`;
      return;
    }
    const max = Math.max(...products.map((product) => product.revenue), 1);
    els.topProducts.innerHTML = products
      .map(
        (product, index) => `
        <div class="product-row">
          <span class="rank">${index + 1}</span>
          <div class="product-main">
            <div class="product-name">${esc(product.name)}</div>
            <div class="product-meta">${product.units.toLocaleString()} unit${product.units === 1 ? "" : "s"} · ${product.sales} sale${product.sales === 1 ? "" : "s"}</div>
          </div>
          <div class="product-amount">
            <strong>${fmtMoney(product.revenue)}</strong>
            <div class="bar"><span style="width:${clamp((product.revenue / max) * 100, 4, 100)}%"></span></div>
          </div>
        </div>`
      )
      .join("");
  }

  function renderRecent() {
    const recent = state.summary.recent.slice(0, 6);
    if (!recent.length) {
      els.recentSales.innerHTML = `<div class="list-empty">No sales in this period.</div>`;
      return;
    }
    els.recentSales.innerHTML = recent
      .map(
        (sale) => `
        <div class="recent-row">
          <div class="recent-main">
            <div class="recent-name">${esc(sale.product)}</div>
            <div class="recent-meta">${fmtDay(sale.date)} · ${esc(sale.channel)} · ${sale.units} unit${sale.units === 1 ? "" : "s"}</div>
          </div>
          <div class="recent-amount">${fmtMoney(sale.total)}</div>
        </div>`
      )
      .join("");
  }

  /* ------------------------------------------------------------ chart */

  function niceMax(value) {
    if (!Number.isFinite(value) || value <= 0) return 1;
    const exponent = Math.floor(Math.log10(value));
    const base = Math.pow(10, exponent);
    const normalized = value / base;
    let multiple;
    if (normalized <= 1) multiple = 1;
    else if (normalized <= 2) multiple = 2;
    else if (normalized <= 2.5) multiple = 2.5;
    else if (normalized <= 5) multiple = 5;
    else multiple = 10;
    return multiple * base;
  }

  function smoothPath(points, top, bottom) {
    if (!points.length) return "";
    if (points.length === 1) return `M ${points[0][0]},${points[0][1]}`;
    let path = `M ${points[0][0]},${points[0][1]}`;
    for (let i = 0; i < points.length - 1; i += 1) {
      const p0 = points[i - 1] || points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = clamp(p1[1] + (p2[1] - p0[1]) / 6, top, bottom);
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = clamp(p2[1] - (p3[1] - p1[1]) / 6, top, bottom);
      path += ` C ${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`;
    }
    return path;
  }

  function renderChart() {
    const wrap = els.revenueChart;
    const summary = state.summary;
    if (!wrap || !summary) return;

    const points = summary.series.points || [];
    const granularity = summary.series.granularity;

    function ensureTip() {
      let tip = wrap.querySelector("#chartTip");
      if (!tip) {
        tip = document.createElement("div");
        tip.id = "chartTip";
        tip.className = "chart-tip";
        wrap.appendChild(tip);
      }
      els.chartTip = tip;
      return tip;
    }

    if (!points.length || summary.totals.sales === 0) {
      wrap.innerHTML = `<div class="chart-empty">No revenue in this period</div>`;
      ensureTip();
      return;
    }

    const width = wrap.clientWidth || 680;
    const height = wrap.clientHeight || 272;
    const pad = { left: 58, right: 16, top: 16, bottom: 34 };
    const innerW = Math.max(10, width - pad.left - pad.right);
    const innerH = Math.max(10, height - pad.top - pad.bottom);
    const bottom = pad.top + innerH;
    const values = points.map((point) => point.revenue);
    const yMax = niceMax(Math.max(...values, 1));

    const xFor = (index) =>
      points.length === 1 ? pad.left + innerW / 2 : pad.left + (index * innerW) / (points.length - 1);
    const yFor = (value) => pad.top + innerH - (value / yMax) * innerH;

    const coords = points.map((point, index) => [xFor(index), yFor(point.revenue)]);
    const linePath = smoothPath(coords, pad.top, bottom);
    const areaPath =
      points.length === 1
        ? ""
        : `${linePath} L ${coords[coords.length - 1][0]},${bottom} L ${coords[0][0]},${bottom} Z`;

    let grid = "";
    for (let i = 0; i <= 4; i += 1) {
      const y = pad.top + (innerH * i) / 4;
      const value = yMax * (1 - i / 4);
      grid += `<line x1="${pad.left}" y1="${y}" x2="${pad.left + innerW}" y2="${y}" stroke="#eff0e8" stroke-width="1"${i === 4 ? ' stroke-opacity="1"' : ""}/>`;
      grid += `<text class="chart-y-label" x="${pad.left - 9}" y="${y + 3}" text-anchor="end">${esc(fmtMoney(value, true))}</text>`;
    }

    const maxLabels = clamp(Math.floor(innerW / 92), 2, 7);
    const labelIndices = new Set();
    if (points.length <= maxLabels) {
      points.forEach((_, index) => labelIndices.add(index));
    } else {
      for (let i = 0; i < maxLabels; i += 1) {
        labelIndices.add(Math.round((i * (points.length - 1)) / (maxLabels - 1)));
      }
    }

    let xLabels = "";
    labelIndices.forEach((index) => {
      const x = xFor(index);
      let anchor = "middle";
      if (index === 0 && points.length > 2) anchor = "start";
      if (index === points.length - 1 && points.length > 2) anchor = "end";
      xLabels += `<text class="chart-x-label" x="${x}" y="${height - 10}" text-anchor="${anchor}">${esc(
        granularity === "month" ? fmtBucket(points[index].date, granularity).split(" ")[0] : fmtDay(points[index].date)
      )}</text>`;
    });

    wrap.innerHTML = `
      <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Revenue over time">
        <defs>
          <linearGradient id="revenue-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#bfe94f" stop-opacity="0.42"/>
            <stop offset="70%" stop-color="#c8f45c" stop-opacity="0.1"/>
            <stop offset="100%" stop-color="#c8f45c" stop-opacity="0"/>
          </linearGradient>
        </defs>
        ${grid}
        ${areaPath ? `<path d="${areaPath}" fill="url(#revenue-fill)"/>` : ""}
        <path d="${linePath}" fill="none" stroke="#709c22" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
        ${points.length === 1
        ? `<circle cx="${coords[0][0]}" cy="${coords[0][1]}" r="4" fill="#709c22"/>`
        : ""
      }
        <g class="hover-layer" style="opacity:0">
          <line x1="0" y1="${pad.top}" x2="0" y2="${bottom}" stroke="#b9c69a" stroke-width="1" stroke-dasharray="3 4"/>
          <circle cx="0" cy="0" r="4.5" fill="#ffffff" stroke="#709c22" stroke-width="2.4"/>
        </g>
        ${xLabels}
        <rect class="chart-overlay" x="${pad.left}" y="${pad.top}" width="${innerW}" height="${innerH}" fill="transparent"/>
      </svg>`;

    const svg = wrap.querySelector("svg");
    const overlay = wrap.querySelector(".chart-overlay");
    const hover = wrap.querySelector(".hover-layer");
    const line = hover.querySelector("line");
    const dot = hover.querySelector("circle");
    const tip = ensureTip();

    overlay.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      const pointerX = event.clientX - rect.left;
      const ratio = clamp((pointerX - pad.left) / innerW, 0, 1);
      const index = Math.round(ratio * (points.length - 1));
      const point = points[index];
      const px = xFor(index);
      const py = yFor(point.revenue);

      hover.style.opacity = "1";
      line.setAttribute("x1", px);
      line.setAttribute("x2", px);
      dot.setAttribute("cx", px);
      dot.setAttribute("cy", py);

      tip.innerHTML = `
        <div class="tip-date">${esc(fmtBucket(point.date, granularity))}</div>
        <div class="tip-value">${fmtMoney(point.revenue)}</div>
        <div class="tip-meta">${point.sales} sale${point.sales === 1 ? "" : "s"} · ${point.units} unit${point.units === 1 ? "" : "s"}</div>`;
      tip.style.left = `${clamp(px, 78, width - 78)}px`;
      tip.style.top = `${clamp(py - 14, 48, height - 10)}px`;
      tip.classList.add("is-visible");
    });

    overlay.addEventListener("mouseleave", () => {
      hover.style.opacity = "0";
      tip.classList.remove("is-visible");
    });
  }

  /* ------------------------------------------------------------ donut */

  function renderDonut() {
    const categories = state.summary.categories;
    const total = categories.reduce((sum, category) => sum + category.revenue, 0);

    if (!categories.length || total <= 0) {
      els.donutChart.innerHTML = `<div class="donut-empty">No category data</div>`;
      els.donutLegend.innerHTML = "";
      return;
    }

    const top = categories.slice(0, 5).map((category) => ({ ...category }));
    const rest = categories.slice(5);
    if (rest.length) {
      top.push({
        name: "Other",
        revenue: rest.reduce((sum, category) => sum + category.revenue, 0),
        sales: rest.reduce((sum, category) => sum + category.sales, 0),
      });
    }

    let cursor = 0;
    const segments = top.map((category, index) => {
      const pct = (category.revenue / total) * 100;
      const dash = Math.max(pct - 1.1, 0.5);
      const circle = `
        <circle cx="84" cy="84" r="63" fill="none"
          stroke="${PALETTE[index % PALETTE.length]}" stroke-width="21"
          pathLength="100" stroke-dasharray="${dash} ${100 - dash}"
          stroke-dashoffset="${-(cursor + 0.55)}" transform="rotate(-90 84 84)">
          <title>${esc(category.name)}: ${fmtMoney(category.revenue)}</title>
        </circle>`;
      cursor += pct;
      return circle;
    });

    els.donutChart.innerHTML = `
      <svg viewBox="0 0 168 168" role="img" aria-label="Revenue by category">
        <circle cx="84" cy="84" r="63" fill="none" stroke="#f1f2e9" stroke-width="21"/>
        ${segments.join("")}
        <text class="donut-center-value" x="84" y="82" text-anchor="middle">${esc(fmtMoney(total, true))}</text>
        <text class="donut-center-label" x="84" y="97" text-anchor="middle">REVENUE</text>
      </svg>`;

    els.donutLegend.innerHTML = top
      .map(
        (category, index) => `
        <div class="legend-row">
          <span class="legend-dot" style="background:${PALETTE[index % PALETTE.length]}"></span>
          <span class="legend-name">${esc(category.name)}</span>
          <span class="legend-pct">${Math.round((category.revenue / total) * 100)}%</span>
          <span class="legend-value">${fmtMoney(category.revenue)}</span>
        </div>`
      )
      .join("");
  }

  /* ------------------------------------------------------------ table */

  function renderTransactions() {
    const items = state.sales;
    els.resultCount.textContent = `${items.length} sale${items.length === 1 ? "" : "s"}`;
    const totalPages = Math.max(1, Math.ceil(items.length / state.pageSize));
    state.page = clamp(state.page, 1, totalPages);
    const startIndex = (state.page - 1) * state.pageSize;
    const pageItems = items.slice(startIndex, startIndex + state.pageSize);

    els.salesTable.classList.toggle("hidden", items.length === 0);
    els.tableEmpty.classList.toggle("hidden", items.length > 0);

    els.salesBody.innerHTML = pageItems
      .map(
        (sale) => `
        <tr>
          <td class="cell-date">
            <strong>${fmtDay(sale.date)}</strong>
            <div class="cell-sub">${parseISO(sale.date).getFullYear()}</div>
          </td>
          <td>
            <div class="cell-main">${esc(sale.product)}</div>
            <div class="cell-sub">${esc(sale.category)}${sale.customer ? ` · ${esc(sale.customer)}` : ""}</div>
          </td>
          <td><span class="pill ${channelClass(sale.channel)}">${esc(sale.channel)}</span></td>
          <td class="num">${sale.units.toLocaleString()}</td>
          <td class="num">${fmtMoney(sale.unit_price)}</td>
          <td class="num cell-total">${fmtMoney(sale.total)}</td>
          <td class="cell-actions">
            <button class="icon-btn" type="button" data-edit="${sale.id}" aria-label="Edit ${esc(sale.product)}">
              <svg><use href="#i-edit"/></svg>
            </button>
            <button class="icon-btn danger" type="button" data-delete="${sale.id}" aria-label="Delete ${esc(sale.product)}">
              <svg><use href="#i-trash"/></svg>
            </button>
          </td>
        </tr>`
      )
      .join("");

    if (items.length) {
      const endIndex = Math.min(startIndex + state.pageSize, items.length);
      els.pageInfo.textContent = `Showing ${startIndex + 1}–${endIndex} of ${items.length}`;
    } else {
      els.pageInfo.textContent = "No matching sales";
    }
    els.pageLabel.textContent = `${state.page} / ${totalPages}`;
    els.prevPage.disabled = state.page <= 1;
    els.nextPage.disabled = state.page >= totalPages;
  }

  /* ------------------------------------------------------------ modal */

  function openSaleModal(sale = null) {
    state.editingId = sale ? sale.id : null;
    els.saleForm.reset();
    els.saleDate.value = sale?.date || isoDate(new Date());
    els.saleProduct.value = sale?.product || "";
    els.saleCategory.value = sale?.category || "";
    els.saleChannel.value = sale?.channel || state.channel || "Online";
    els.saleUnits.value = sale?.units ?? 1;
    els.salePrice.value = (sale?.unit_price ?? 0).toFixed(2);
    els.saleCustomer.value = sale?.customer || "";
    els.saleNotes.value = sale?.notes || "";
    els.priceSymbol.textContent = currencySymbol();
    els.saleModalEyebrow.textContent = sale ? "Edit transaction" : "New transaction";
    els.saleModalTitle.textContent = sale ? "Edit sale" : "Add a sale";
    els.saveSale.textContent = sale ? "Save changes" : "Save sale";
    els.saleError.classList.add("hidden");
    updateSaleTotal();
    els.saleModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    setTimeout(() => els.saleProduct.focus(), 40);
  }

  function closeSaleModal() {
    els.saleModal.classList.add("hidden");
    document.body.style.overflow = "";
    state.editingId = null;
    els.saleError.classList.add("hidden");
  }

  function updateSaleTotal() {
    const units = Math.max(0, Number(els.saleUnits.value) || 0);
    const price = Math.max(0, Number(els.salePrice.value) || 0);
    els.saleTotalPreview.textContent = fmtMoney(units * price);
  }

  function showFormError(message) {
    els.saleError.textContent = message;
    els.saleError.classList.remove("hidden");
  }

  async function saveSale(event) {
    event.preventDefault();
    const wasEditing = Boolean(state.editingId);
    const date = els.saleDate.value;
    const product = els.saleProduct.value.trim();
    const units = Number(els.saleUnits.value);
    const price = Number(els.salePrice.value);

    if (!date) return showFormError("Choose a date for this sale.");
    if (!product) return showFormError("Add a product name.");
    if (!Number.isInteger(units) || units < 1) return showFormError("Units must be a whole number of at least 1.");
    if (!Number.isFinite(price) || price < 0) return showFormError("Unit price must be 0 or more.");

    const payload = {
      date,
      product,
      category: els.saleCategory.value.trim(),
      channel: els.saleChannel.value.trim(),
      units,
      unit_price: price,
      customer: els.saleCustomer.value.trim(),
      notes: els.saleNotes.value.trim(),
    };

    els.saveSale.disabled = true;
    els.saveSale.textContent = "Saving…";
    try {
      if (wasEditing) {
        await api(`/api/sales/${state.editingId}`, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        await api("/api/sales", { method: "POST", body: JSON.stringify(payload) });
      }
      closeSaleModal();
      toast(wasEditing ? "Sale updated" : "Sale added");
      state.page = 1;
      await refresh();
    } catch (error) {
      showFormError(error.message);
      els.saveSale.disabled = false;
      els.saveSale.textContent = wasEditing ? "Save changes" : "Save sale";
    }
  }

  function askConfirm({ title, message, okLabel = "Confirm", onOk }) {
    els.confirmTitle.textContent = title;
    els.confirmMessage.textContent = message;
    els.confirmOk.textContent = okLabel;
    state.confirmAction = onOk;
    els.confirmModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    setTimeout(() => els.confirmCancel.focus(), 40);
  }

  function closeConfirm() {
    els.confirmModal.classList.add("hidden");
    document.body.style.overflow = "";
    state.confirmAction = null;
  }

  function deleteSale(sale) {
    askConfirm({
      title: "Delete this sale?",
      message: `${sale.product} · ${sale.units} unit${sale.units === 1 ? "" : "s"} · ${fmtMoney(sale.total)} on ${fmtFullDay(sale.date)}. This can't be undone.`,
      okLabel: "Delete sale",
      onOk: async () => {
        try {
          await api(`/api/sales/${sale.id}`, { method: "DELETE" });
          toast("Sale deleted");
          await refresh();
        } catch (error) {
          toast(error.message, "error");
        }
      },
    });
  }

  function clearAllSales() {
    const count = state.meta?.total || 0;
    if (!count) {
      toast("There are no sales to delete.", "error");
      return;
    }
    askConfirm({
      title: "Delete all sales?",
      message: `This permanently removes all ${count} sale${count === 1 ? "" : "s"} from your local database. Export a CSV first if you want a backup.`,
      okLabel: "Delete everything",
      onOk: async () => {
        try {
          const result = await api("/api/sales/all", { method: "DELETE" });
          toast(`Deleted ${result.deleted} sale${result.deleted === 1 ? "" : "s"}`);
          state.page = 1;
          await refresh();
        } catch (error) {
          toast(error.message, "error");
        }
      },
    });
  }

  async function loadSampleData() {
    try {
      const result = await api("/api/seed", { method: "POST", body: "{}" });
      if (!result.inserted) {
        toast("Clear existing sales first to load the sample data.", "error");
        return;
      }
      localStorage.removeItem("counter-demo-dismissed");
      toast(`Loaded ${result.inserted} sample sales`);
      state.page = 1;
      await refresh();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  /* ------------------------------------------------------------ CSV import */

  function parseCSV(text) {
    const clean = text.replace(/^\uFEFF/, "");
    const firstLine = clean.split(/\r?\n/, 1)[0] || "";
    const counts = {
      ",": (firstLine.match(/,/g) || []).length,
      ";": (firstLine.match(/;/g) || []).length,
      "\t": (firstLine.match(/\t/g) || []).length,
    };
    const delimiter = Object.keys(counts).reduce((a, b) => (counts[b] > counts[a] ? b : a), ",");

    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;

    for (let i = 0; i < clean.length; i += 1) {
      const char = clean[i];
      if (inQuotes) {
        if (char === '"') {
          if (clean[i + 1] === '"') {
            field += '"';
            i += 1;
          } else {
            inQuotes = false;
          }
        } else {
          field += char;
        }
      } else if (char === '"') {
        inQuotes = true;
      } else if (char === delimiter) {
        row.push(field);
        field = "";
      } else if (char === "\n") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
      } else if (char !== "\r") {
        field += char;
      }
    }
    if (field.length || row.length) {
      row.push(field);
      rows.push(row);
    }
    return rows.filter((cells) => cells.some((cell) => String(cell).trim() !== ""));
  }

  function normalizeHeader(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ");
  }

  const HEADER_ALIASES = {
    date: ["date", "sale date", "sold at", "sold on", "day", "transaction date"],
    product: ["product", "item", "product name", "item name", "name", "description"],
    category: ["category", "type", "product category"],
    channel: ["channel", "source", "sales channel", "platform"],
    units: ["units", "quantity", "qty", "count", "items"],
    unit_price: ["unit price", "price", "sale price", "amount", "unit cost"],
    customer: ["customer", "customer name", "client", "buyer"],
    notes: ["notes", "note", "memo", "comment"],
  };

  function normaliseDate(value) {
    const raw = String(value || "").trim();
    if (!raw) return null;

    let match = raw.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/);
    if (match) {
      const [, y, m, d] = match;
      const dateObj = new Date(Number(y), Number(m) - 1, Number(d));
      if (
        dateObj.getFullYear() === Number(y) &&
        dateObj.getMonth() === Number(m) - 1 &&
        dateObj.getDate() === Number(d)
      ) {
        return isoDate(dateObj);
      }
    }

    match = raw.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$/);
    if (match) {
      let [, a, b, y] = match;
      let year = Number(y);
      if (year < 100) year += 2000;
      const first = Number(a);
      const second = Number(b);
      const month = first > 12 ? second : first;
      const day = first > 12 ? first : second;
      const dateObj = new Date(year, month - 1, day);
      if (dateObj.getMonth() === month - 1 && dateObj.getDate() === day) {
        return isoDate(dateObj);
      }
    }

    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) return isoDate(parsed);
    return null;
  }

  function parseNumber(value, fallback = 0) {
    const cleaned = String(value || "").replace(/[^0-9.\-]/g, "");
    const number = Number(cleaned);
    return Number.isFinite(number) ? number : fallback;
  }

  function mapCSV(rows) {
    if (rows.length < 2) {
      throw new Error("The file needs a header row and at least one sale.");
    }
    const headers = rows[0].map(normalizeHeader);
    const indexes = {};
    Object.entries(HEADER_ALIASES).forEach(([field, aliases]) => {
      indexes[field] = headers.findIndex((header) => aliases.includes(header));
    });

    if (indexes.date === -1 || indexes.product === -1) {
      throw new Error("Couldn't find date and product columns. Use the CSV template as a guide.");
    }

    const mapped = [];
    let skipped = 0;

    rows.slice(1).forEach((cells) => {
      const get = (field) => (indexes[field] >= 0 ? cells[indexes[field]] : "");
      const date = normaliseDate(get("date"));
      const product = String(get("product") || "").trim();
      if (!date || !product) {
        skipped += 1;
        return;
      }
      const unitsRaw = Math.round(parseNumber(get("units"), 1));
      const priceRaw = parseNumber(get("unit_price"), 0);
      mapped.push({
        date,
        product: product.slice(0, 120),
        category: String(get("category") || "").trim().slice(0, 60) || "General",
        channel: String(get("channel") || "").trim().slice(0, 40) || "Online",
        units: unitsRaw >= 1 ? unitsRaw : 1,
        unit_price: Math.max(0, Math.round(priceRaw * 100) / 100),
        customer: String(get("customer") || "").trim().slice(0, 120),
        notes: String(get("notes") || "").trim().slice(0, 500),
      });
    });

    return { rows: mapped, skipped };
  }

  function handleCSVFile(file) {
    if (!file) return;
    if (!/\.(csv|tsv|txt)$/i.test(file.name) && !/^(text\/|application\/vnd\.ms-excel)/.test(file.type)) {
      toast("Choose a CSV or TSV file.", "error");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = parseCSV(String(reader.result || ""));
        const { rows, skipped } = mapCSV(parsed);
        if (!rows.length) {
          throw new Error("No valid rows found. Each row needs a date and a product.");
        }
        state.importRows = rows;
        state.importSkipped = skipped;
        renderImportPreview();
        els.importResult.classList.add("hidden");
      } catch (error) {
        els.importPreview.classList.add("hidden");
        toast(error.message, "error");
      }
      els.fileInput.value = "";
    };
    reader.onerror = () => toast("Couldn't read that file.", "error");
    reader.readAsText(file);
  }

  function renderImportPreview() {
    const rows = state.importRows;
    els.previewTitle.textContent = `Ready to import ${rows.length} sale${rows.length === 1 ? "" : "s"}`;
    els.previewNote.textContent = state.importSkipped
      ? `${state.importSkipped} row${state.importSkipped === 1 ? "" : "s"} skipped (missing date or product)`
      : "All rows look good.";
    els.previewTable.innerHTML = `
      <thead><tr><th>Date</th><th>Product</th><th>Category</th><th>Channel</th><th class="num">Units</th><th class="num">Price</th></tr></thead>
      <tbody>${rows
        .slice(0, 5)
        .map(
          (row) => `<tr>
            <td>${esc(row.date)}</td>
            <td>${esc(row.product)}</td>
            <td>${esc(row.category)}</td>
            <td>${esc(row.channel)}</td>
            <td class="num">${row.units}</td>
            <td class="num">${fmtMoney(row.unit_price)}</td>
          </tr>`
        )
        .join("")}</tbody>`;
    els.importPreview.classList.remove("hidden");
  }

  async function confirmImport() {
    if (!state.importRows.length) return;
    els.confirmImport.disabled = true;
    els.confirmImport.textContent = "Importing…";
    try {
      const result = await api("/api/import", {
        method: "POST",
        body: JSON.stringify({ rows: state.importRows }),
      });
      els.importPreview.classList.add("hidden");
      state.importRows = [];
      const errorList = result.errors?.length
        ? `<ul>${result.errors
          .map((entry) => `<li>Row ${entry.row}: ${esc(entry.message)}</li>`)
          .join("")}</ul>`
        : "";
      els.importResult.className = "import-result";
      els.importResult.innerHTML = `<strong>Imported ${result.inserted} sale${result.inserted === 1 ? "" : "s"}.</strong>${result.skipped ? ` ${result.skipped} skipped.` : ""
        }${errorList}`;
      toast(`Imported ${result.inserted} sale${result.inserted === 1 ? "" : "s"}`);
      state.page = 1;
      await refresh();
    } catch (error) {
      els.importResult.className = "import-result is-error";
      els.importResult.innerHTML = `<strong>Import failed.</strong> ${esc(error.message)}`;
      els.importResult.classList.remove("hidden");
      toast(error.message, "error");
    } finally {
      els.confirmImport.disabled = false;
      els.confirmImport.textContent = "Import rows";
    }
  }

  function downloadBlob(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadTemplate() {
    const today = isoDate(new Date());
    const csv = [
      "date,product,category,channel,units,unit_price,customer,notes",
      `${today},Aurora Wireless Earbuds,Electronics,Online,1,89.00,Maya Chen,`,
      `${today},Terra Ceramic Mug Set,Home,In-store,2,28.00,,Gift wrap`,
      `${today},Merino Crew Socks,Apparel,Wholesale,12,18.00,Northside Studio,`,
    ].join("\n");
    downloadBlob(`\uFEFF${csv}`, "counter-import-template.csv", "text/csv;charset=utf-8");
  }

  function exportCSV() {
    const params = filterParams(true);
    const query = params.toString();
    window.location.href = apiURL(`/api/export.csv${query ? `?${query}` : ""}`);
  }

  /* ------------------------------------------------------------ navigation */

  function setView(view) {
    state.view = view;
    $$(".view").forEach((section) => section.classList.add("hidden"));
    const target = $(`#view-${view}`);
    if (target) target.classList.remove("hidden");
    $$(".nav-item").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.view === view);
    });
    updateHeading();
    if (view === "overview") {
      requestAnimationFrame(() => renderChart());
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* ------------------------------------------------------------ events */

  function bindEvents() {
    $$(".nav-item").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.view));
    });

    $$("[data-goto]").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.goto));
    });

    els.presetList.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-preset]");
      if (button) applyPreset(button.dataset.preset);
    });

    els.startDate.addEventListener("change", () => onCustomDateChange("start"));
    els.endDate.addEventListener("change", () => onCustomDateChange("end"));

    els.channelFilter.addEventListener("change", () => {
      state.channel = els.channelFilter.value;
      state.page = 1;
      refresh();
    });

    els.categoryFilter.addEventListener("change", () => {
      state.category = els.categoryFilter.value;
      state.page = 1;
      refreshSales();
    });

    els.currency.value = state.currency;
    els.currency.addEventListener("change", () => {
      state.currency = els.currency.value;
      localStorage.setItem("counter-currency", state.currency);
      moneyCache.clear();
      els.priceSymbol.textContent = currencySymbol();
      renderAll();
    });

    $("#addBtn").addEventListener("click", () => openSaleModal());
    els.emptyAdd.addEventListener("click", () => openSaleModal());
    $("#closeSaleModal").addEventListener("click", closeSaleModal);
    $("#cancelSale").addEventListener("click", closeSaleModal);
    els.saleModal.addEventListener("mousedown", (event) => {
      if (event.target === els.saleModal) closeSaleModal();
    });
    els.saleForm.addEventListener("submit", saveSale);
    ["input", "change"].forEach((eventName) => {
      els.saleUnits.addEventListener(eventName, updateSaleTotal);
      els.salePrice.addEventListener(eventName, updateSaleTotal);
    });

    els.salesBody.addEventListener("click", (event) => {
      const editButton = event.target.closest("[data-edit]");
      const deleteButton = event.target.closest("[data-delete]");
      if (editButton) {
        const sale = state.sales.find((item) => item.id === Number(editButton.dataset.edit));
        if (sale) openSaleModal(sale);
      }
      if (deleteButton) {
        const sale = state.sales.find((item) => item.id === Number(deleteButton.dataset.delete));
        if (sale) deleteSale(sale);
      }
    });

    const runSearch = debounce(() => {
      state.q = els.searchInput.value.trim();
      state.page = 1;
      refreshSales();
    }, 240);
    els.searchInput.addEventListener("input", runSearch);

    els.prevPage.addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      renderTransactions();
    });
    els.nextPage.addEventListener("click", () => {
      state.page += 1;
      renderTransactions();
    });

    $("#tableClearFilters").addEventListener("click", () => {
      state.q = "";
      state.category = "";
      state.channel = "";
      els.searchInput.value = "";
      els.categoryFilter.value = "";
      els.channelFilter.value = "";
      state.page = 1;
      refresh();
    });

    $("#exportBtn").addEventListener("click", exportCSV);

    els.confirmClose.addEventListener("click", closeConfirm);
    $("#confirmCancel").addEventListener("click", closeConfirm);
    els.confirmModal.addEventListener("mousedown", (event) => {
      if (event.target === els.confirmModal) closeConfirm();
    });
    els.confirmOk.addEventListener("click", () => {
      const action = state.confirmAction;
      closeConfirm();
      if (typeof action === "function") action();
    });

    $("#bannerDismiss").addEventListener("click", () => {
      localStorage.setItem("counter-demo-dismissed", "1");
      renderDemoBanner();
    });
    $("#bannerClear").addEventListener("click", clearAllSales);
    $("#clearAllBtn").addEventListener("click", clearAllSales);
    els.sampleBtn.addEventListener("click", loadSampleData);

    els.emptySample.addEventListener("click", () => {
      if (state.meta && state.meta.total > 0) applyPreset("all");
      else loadSampleData();
    });

    $("#browseBtn").addEventListener("click", (event) => {
      event.stopPropagation();
      els.fileInput.click();
    });
    els.dropzone.addEventListener("click", (event) => {
      if (!event.target.closest("#browseBtn")) els.fileInput.click();
    });
    els.dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        els.fileInput.click();
      }
    });
    els.fileInput.addEventListener("change", () => handleCSVFile(els.fileInput.files[0]));

    ["dragenter", "dragover"].forEach((type) => {
      els.dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        els.dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach((type) => {
      els.dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        els.dropzone.classList.remove("is-dragover");
      });
    });
    els.dropzone.addEventListener("drop", (event) => {
      handleCSVFile(event.dataTransfer.files[0]);
    });

    $("#cancelImport").addEventListener("click", () => {
      state.importRows = [];
      els.importPreview.classList.add("hidden");
      els.fileInput.value = "";
    });
    els.confirmImport.addEventListener("click", confirmImport);
    $("#templateBtn").addEventListener("click", downloadTemplate);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!els.saleModal.classList.contains("hidden")) closeSaleModal();
        else if (!els.confirmModal.classList.contains("hidden")) closeConfirm();
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (state.view !== "transactions") setView("transactions");
        setTimeout(() => els.searchInput.focus(), 60);
      }
    });

    window.addEventListener(
      "resize",
      debounce(() => {
        if (state.view === "overview" && state.summary) {
          renderChart();
        }
      }, 160)
    );

    if ("ResizeObserver" in window) {
      let chartFrame = 0;
      const chartObserver = new ResizeObserver(() => {
        if (state.view !== "overview" || !state.summary) return;
        cancelAnimationFrame(chartFrame);
        chartFrame = requestAnimationFrame(() => renderChart());
      });
      chartObserver.observe(els.revenueChart);
    }
  }

  /* ------------------------------------------------------------ boot */

  function boot() {
    applyPreset("30d", false);
    bindEvents();
    els.currency.value = state.currency;
    els.priceSymbol.textContent = currencySymbol();
    refresh();
  }

  boot();
})();
