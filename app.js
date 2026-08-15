const statusText = document.getElementById("status-text");
const subscribeBtn = document.getElementById("subscribe-btn");
const refreshBtn = document.getElementById("refresh-btn");
const updatedAtEl = document.getElementById("updated-at");
const summaryEl = document.getElementById("summary");
const resultsEl = document.getElementById("results");
const viewTabs = document.querySelectorAll(".view-tab");
const chartModal = document.getElementById("chart-modal");
const chartModalBody = document.getElementById("chart-modal-body");
const chartModalBackdrop = document.getElementById("chart-modal-backdrop");
const chartModalClose = document.getElementById("chart-modal-close");

// シグナル別ブロックの表示順・見出し・簡単な説明。
// バックエンド(screener_job.py)の CATEGORY_PRIORITY と対応させている。
const CATEGORY_META = {
  oversold: { title: "売られすぎ", hint: "反発が期待されやすい局面" },
  overbought: { title: "買われすぎ", hint: "過熱・反落に注意" },
  golden_cross: { title: "ゴールデンクロス", hint: "上昇トレンド転換のシグナル" },
  dead_cross: { title: "デッドクロス", hint: "下降トレンド転換のシグナル" },
  breakout: { title: "値幅ブレイク", hint: "直近レンジの高値・安値を更新" },
  volume_surge: { title: "出来高急増", hint: "" },
  other: { title: "その他", hint: "" },
};
const CATEGORY_ORDER = ["oversold", "overbought", "golden_cross", "dead_cross", "breakout", "volume_surge", "other"];

const FAVORITES_KEY = "jpss_favorites";

let lastData = null;
let currentView = "signal";
let priceChart = null;
let favoriteCodes = loadFavorites();

function loadFavorites() {
  try {
    const raw = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw : []);
  } catch (e) {
    return new Set();
  }
}

function saveFavorites() {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favoriteCodes]));
  } catch (e) {
    /* ignore (プライベートモード等でlocalStorageが使えない場合) */
  }
}

function toggleFavorite(code) {
  if (favoriteCodes.has(code)) {
    favoriteCodes.delete(code);
  } else {
    favoriteCodes.add(code);
  }
  saveFavorites();
  renderCurrentView();
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  return navigator.serviceWorker.register("/service-worker.js");
}

async function subscribeToPush() {
  if (!("Notification" in window) || !("PushManager" in window)) {
    statusText.textContent = "このブラウザはプッシュ通知に対応していません。";
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    statusText.textContent = "通知が許可されませんでした。";
    return;
  }
  const reg = await registerServiceWorker();
  const { publicKey } = await fetch("/api/vapid-public-key").then((r) => r.json());
  const subscription = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });
  await fetch("/api/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription),
  });
  statusText.textContent = "通知を有効にしました。";
  subscribeBtn.textContent = "通知は有効です";
  subscribeBtn.disabled = true;
}

function scoreOf(r) {
  return typeof r.score === "number" ? r.score : (r.hits ? r.hits.length : 0);
}

function hitsHtmlOf(r) {
  return (r.hits || [])
    .map((h) => `<li>${typeof h === "string" ? h : h.label}</li>`)
    .join("");
}

function emptyStateHtml(data) {
  return data.status === "running"
    ? '<div class="empty-state">スクリーニングを実行中です。しばらくすると該当銘柄が表示されます...</div>'
    : '<div class="empty-state">現在、条件に合致している銘柄はありません。</div>';
}

function buildCard(r, rank, newSet) {
  const card = document.createElement("div");
  card.className = "stock-card" + (newSet.has(r.code) ? " new" : "");
  card.dataset.code = r.code;
  card.dataset.name = r.name;
  const isNew = newSet.has(r.code) ? '<span class="badge-new">NEW</span>' : "";
  const isFav = favoriteCodes.has(r.code);
  card.innerHTML = `
    <div class="name-row">
      <span class="rank-badge">#${rank}</span>
      <button class="fav-star${isFav ? " active" : ""}" data-code="${r.code}" aria-label="お気に入り登録">${isFav ? "★" : "☆"}</button>
      <span class="name">${r.name}${isNew}</span>
      <span class="code">${r.code}</span>
    </div>
    <ul>${hitsHtmlOf(r)}</ul>
  `;
  return card;
}

// シグナル種別ごとの過去の的中率(直近のサーバー稼働中に記録された分のみの参考値)。
function statsHtmlOf(data, cat) {
  const stats = data.signal_stats && data.signal_stats[cat];
  if (!stats || !stats.total) return "";
  const sign = stats.avg_return_pct > 0 ? "+" : "";
  return `<div class="section-stats">参考: 過去の的中率 ${stats.win_rate}%(${stats.total}件、平均${sign}${stats.avg_return_pct}%) ※サーバー再起動でリセットされる簡易集計です</div>`;
}

function renderBySignal(data) {
  resultsEl.innerHTML = "";
  const groups = {};
  for (const r of data.results) {
    const cat = r.category || "other";
    (groups[cat] = groups[cat] || []).push(r);
  }
  const newSet = new Set(data.new_match_codes || []);
  let renderedAny = false;
  for (const cat of CATEGORY_ORDER) {
    const list = groups[cat];
    if (!list || list.length === 0) continue;
    renderedAny = true;
    list.sort((a, b) => scoreOf(b) - scoreOf(a));
    const meta = CATEGORY_META[cat] || CATEGORY_META.other;
    const section = document.createElement("section");
    section.className = "result-section cat-" + cat;
    section.innerHTML = `
      <h2 class="section-title"><span>${meta.title}</span><span class="section-count">${list.length}件</span></h2>
      ${meta.hint ? `<div class="section-hint">${meta.hint}</div>` : ""}
      ${statsHtmlOf(data, cat)}
    `;
    list.forEach((r, i) => section.appendChild(buildCard(r, i + 1, newSet)));
    resultsEl.appendChild(section);
  }
  if (!renderedAny) {
    resultsEl.innerHTML = emptyStateHtml(data);
  }
}

function renderHeatmap(data) {
  resultsEl.innerHTML = "";
  const groups = {};
  for (const r of data.results) {
    const theme = r.industry || "不明";
    const g = (groups[theme] = groups[theme] || { total: 0, bullish: 0, bearish: 0 });
    g.total += 1;
    if (r.category === "oversold" || r.category === "golden_cross") g.bullish += 1;
    if (r.category === "overbought" || r.category === "dead_cross") g.bearish += 1;
  }
  const themes = Object.keys(groups).sort((a, b) => groups[b].total - groups[a].total);
  if (themes.length === 0) {
    resultsEl.innerHTML = emptyStateHtml(data);
    return;
  }
  const note = document.createElement("div");
  note.className = "section-hint";
  note.textContent = "業種ごとの該当件数。緑=売られすぎ/ゴールデンクロスが優勢、赤=買われすぎ/デッドクロスが優勢、色が濃いほど件数が多い";
  resultsEl.appendChild(note);

  const maxTotal = Math.max(...themes.map((t) => groups[t].total));
  const grid = document.createElement("div");
  grid.className = "heatmap-grid";
  for (const theme of themes) {
    const g = groups[theme];
    const net = g.bullish - g.bearish;
    const intensity = maxTotal ? Math.min(1, g.total / maxTotal) : 0;
    const hue = net >= 0 ? 142 : 0;
    const alpha = 0.12 + intensity * 0.58;
    const cell = document.createElement("div");
    cell.className = "heatmap-cell";
    cell.style.background = `hsla(${hue}, 70%, 45%, ${alpha})`;
    cell.innerHTML = `
      <div class="heatmap-theme">${theme}</div>
      <div class="heatmap-count">${g.total}件</div>
      <div class="heatmap-detail">強気${g.bullish} / 弱気${g.bearish}</div>
    `;
    grid.appendChild(cell);
  }
  resultsEl.appendChild(grid);
}

function renderFavorites(data) {
  resultsEl.innerHTML = "";
  const list = data.results.filter((r) => favoriteCodes.has(r.code));
  if (list.length === 0) {
    resultsEl.innerHTML = '<div class="empty-state">まだお気に入りに追加した銘柄がありません。銘柄カードの☆をタップすると追加できます。</div>';
    return;
  }
  list.sort((a, b) => scoreOf(b) - scoreOf(a));
  const newSet = new Set(data.new_match_codes || []);
  const section = document.createElement("section");
  section.className = "result-section";
  section.innerHTML = `<h2 class="section-title"><span>お気に入り</span><span class="section-count">${list.length}件</span></h2>`;
  list.forEach((r, i) => section.appendChild(buildCard(r, i + 1, newSet)));
  resultsEl.appendChild(section);
}

function renderByTheme(data) {
  resultsEl.innerHTML = "";
  const groups = {};
  for (const r of data.results) {
    const theme = r.industry || "不明";
    (groups[theme] = groups[theme] || []).push(r);
  }
  const themes = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
  if (themes.length === 0) {
    resultsEl.innerHTML = emptyStateHtml(data);
    return;
  }
  const newSet = new Set(data.new_match_codes || []);
  for (const theme of themes) {
    const list = groups[theme].sort((a, b) => scoreOf(b) - scoreOf(a));
    const section = document.createElement("section");
    section.className = "result-section";
    section.innerHTML = `<h2 class="section-title"><span>${theme}</span><span class="section-count">${list.length}件</span></h2>`;
    list.forEach((r, i) => section.appendChild(buildCard(r, i + 1, newSet)));
    resultsEl.appendChild(section);
  }
}

function renderCurrentView() {
  if (!lastData) return;
  if (currentView === "theme") {
    renderByTheme(lastData);
  } else if (currentView === "heatmap") {
    renderHeatmap(lastData);
  } else if (currentView === "favorites") {
    renderFavorites(lastData);
  } else {
    renderBySignal(lastData);
  }
}

viewTabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    viewTabs.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentView = btn.dataset.view;
    renderCurrentView();
  });
});

async function loadResults() {
  const data = await fetch("/api/results").then((r) => r.json());
  lastData = data;
  const isRunning = data.status === "running";
  const progress = data.progress || {};

  if (isRunning) {
    const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
    updatedAtEl.textContent = `更新中... ${progress.done || 0}/${progress.total || "?"}銘柄処理済み (${pct}%)`;
  } else {
    updatedAtEl.textContent = data.updated_at ? `最終更新: ${data.updated_at.replace("T", " ")}` : "まだ実行されていません";
  }
  summaryEl.textContent = `該当銘柄: ${data.results.length}件` + (isRunning ? "(集計中、随時更新されます)" : "");

  renderCurrentView();
  return data.status;
}

// 銘柄カードのタップでチャートを表示(結果の再描画のたびにリスナーを付け直さなくて済むよう、
// resultsEl自体にイベント委任している)。
resultsEl.addEventListener("click", (e) => {
  const star = e.target.closest(".fav-star");
  if (star) {
    e.stopPropagation();
    toggleFavorite(star.dataset.code);
    return;
  }
  const card = e.target.closest(".stock-card");
  if (!card) return;
  openChartModal(card.dataset.code, card.dataset.name);
});

async function openChartModal(code, name) {
  chartModal.classList.remove("hidden");
  chartModalBody.innerHTML = `
    <h2 class="modal-title">${name} <span class="modal-code">${code}</span></h2>
    <div class="modal-links">
      <a href="https://kabutan.jp/stock/?code=${code}" target="_blank" rel="noopener">株探で見る ↗</a>
      <a href="https://finance.yahoo.co.jp/quote/${code}.T" target="_blank" rel="noopener">Yahoo!ファイナンスで見る ↗</a>
    </div>
    <div class="chart-wrap"><canvas id="price-chart" height="220"></canvas></div>
    <div class="empty-state" id="chart-loading">チャートを読み込み中...</div>
  `;
  try {
    const data = await fetch(`/api/chart/${encodeURIComponent(code)}`).then((r) => r.json());
    const loading = document.getElementById("chart-loading");
    if (data.error) {
      if (loading) loading.textContent = "チャートを取得できませんでした。";
      return;
    }
    if (loading) loading.remove();
    renderPriceChart(data);
  } catch (e) {
    const loading = document.getElementById("chart-loading");
    if (loading) loading.textContent = "チャートの取得に失敗しました。";
  }
}

function renderPriceChart(data) {
  const canvas = document.getElementById("price-chart");
  if (!canvas || typeof Chart === "undefined") return;
  if (priceChart) {
    priceChart.destroy();
    priceChart = null;
  }
  priceChart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: data.dates,
      datasets: [
        { label: "終値", data: data.close, borderColor: "#22c55e", backgroundColor: "transparent", borderWidth: 1.5, pointRadius: 0, tension: 0.15 },
        { label: "5日線", data: data.ma5, borderColor: "#60a5fa", backgroundColor: "transparent", borderWidth: 1, pointRadius: 0, tension: 0.15 },
        { label: "25日線", data: data.ma25, borderColor: "#f59e0b", backgroundColor: "transparent", borderWidth: 1, pointRadius: 0, tension: 0.15 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#9ca3af", maxTicksLimit: 6 }, grid: { color: "#263248" } },
        y: { ticks: { color: "#9ca3af" }, grid: { color: "#263248" } },
      },
      plugins: { legend: { labels: { color: "#e5e7eb", boxWidth: 12, font: { size: 11 } } } },
    },
  });
}

function closeChartModal() {
  chartModal.classList.add("hidden");
  if (priceChart) {
    priceChart.destroy();
    priceChart = null;
  }
}

chartModalBackdrop.addEventListener("click", closeChartModal);
chartModalClose.addEventListener("click", closeChartModal);

subscribeBtn.addEventListener("click", () => subscribeToPush().catch((e) => {
  statusText.textContent = "エラー: " + e.message;
}));

refreshBtn.addEventListener("click", async () => {
  refreshBtn.disabled = true;
  statusText.textContent = "スクリーニングを開始しました。数十秒〜数分で途中経過が表示され始めます...";
  try {
    const resp = await fetch("/api/run-now", { method: "POST" });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      statusText.textContent = "エラー: " + (data.error || resp.status);
    } else {
      // 実行が始まったら、すぐに短い間隔でのポーリングに切り替えて進捗を反映する
      scheduleNextLoad(true);
    }
  } catch (e) {
    statusText.textContent = "エラー: " + e.message;
  }
  refreshBtn.disabled = false;
});

let pollTimer = null;

async function scheduleNextLoad(immediate) {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  const run = async () => {
    let status;
    try {
      status = await loadResults();
    } catch (e) {
      status = null;
    }
    // 実行中は8秒ごと、完了していれば5分ごとに再取得(無料枠のリクエスト数節約のため)
    const delay = status === "running" ? 8000 : 300000;
    pollTimer = setTimeout(run, delay);
  };
  if (immediate) {
    await run();
  } else {
    pollTimer = setTimeout(run, 0);
  }
}

registerServiceWorker();
scheduleNextLoad(true);
