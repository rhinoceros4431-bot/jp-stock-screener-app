const statusText = document.getElementById("status-text");
const subscribeBtn = document.getElementById("subscribe-btn");
const updatedAtEl = document.getElementById("updated-at");
const summaryEl = document.getElementById("summary");
const resultsEl = document.getElementById("results");
const viewTabs = document.querySelectorAll(".view-tab");
const chartModal = document.getElementById("chart-modal");
const chartModalBody = document.getElementById("chart-modal-body");
const chartModalBackdrop = document.getElementById("chart-modal-backdrop");
const chartModalClose = document.getElementById("chart-modal-close");
const pullIndicator = document.getElementById("pull-indicator");

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
const RESULTS_CACHE_KEY = "jpss_results_cache";

let lastData = null;
let currentView = "signal";
let priceChart = null;
let favoriteCodes = loadFavorites();

// アプリを開いた瞬間から「何も表示されない」状態にならないよう、前回取得できた結果を
// 端末に保存しておき、起動直後はまずそれを表示する(裏で最新データの取得は継続する)　
function loadCachedResults() {
  try {
    const raw = JSON.parse(localStorage.getItem(RESULTS_CACHE_KEY) || "null");
    return raw && Array.isArray(raw.results) ? raw : null;
  } catch (e) {
    return null;
  }
}

function saveCachedResults(data) {
  try {
    if (data && Array.isArray(data.results) && data.results.length > 0) {
      localStorage.setItem(RESULTS_CACHE_KEY, JSON.stringify(data));
    }
  } catch (e) {
    /* ignore (プライベートモード等でlocalStorageが使えない場合) */
  }
}

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

// 新しいバージョンのservice-worker.jsが有効化されたら、開いたままのタブでも
// 自動的にリロードして最新のapp.js/index.html/style.cssを反映する。
// (これが無いと「更新したはずなのに古い画面のまま」という状態が、タブを手動で
// 閉じ直すまで続いてしまう)
let _swRefreshing = false;
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (_swRefreshing) return;
    _swRefreshing = true;
    window.location.reload();
  });
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  const reg = await navigator.serviceWorker.register("/service-worker.js");
  // ページを開いたまま長時間放置されるケースもあるため、定期的に更新の有無を確認する
  setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);
  return reg;
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
  saveCachedResults(data);
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

// 起動直後、サーバーからの応答を待たずに前回結果をまず表示する
function showCachedResultsImmediately() {
  const cached = loadCachedResults();
  if (!cached) return;
  lastData = cached;
  updatedAtEl.textContent = cached.updated_at
    ? `最終更新: ${cached.updated_at.replace("T", " ")}(前回取得分。最新データを取得中...)`
    : "前回取得分を表示中(最新データを取得中...)";
  summaryEl.textContent = `該当銘柄: ${cached.results.length}件(前回取得分)`;
  renderCurrentView();
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
    <div id="pattern-match-section"></div>
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
    renderPatternMatch(data.pattern_match);
  } catch (e) {
    const loading = document.getElementById("chart-loading");
    if (loading) loading.textContent = "チャートの取得に失敗しました。";
  }
}

// 直近の値動きと似た過去局面、その後の値動きの参考情報を表示する
function renderPatternMatch(pm) {
  const el = document.getElementById("pattern-match-section");
  if (!el) return;
  if (!pm || !pm.available) {
    el.innerHTML = `
      <div class="pattern-match-box">
        <h3>過去の類似パターン</h3>
        <div class="section-hint">十分に似た過去の値動きが見つかりませんでした(上場から日が浅い、または最近の値動きに近い過去局面が少ない銘柄など)。</div>
      </div>
    `;
    return;
  }
  const sign = pm.avg_forward_return_pct > 0 ? "+" : "";
  const casesHtml = pm.cases
    .map((c) => {
      const csign = c.forward_return_pct > 0 ? "+" : "";
      return `<li>${c.date || "-"}頃(類似度${c.similarity_pct}%) → ${pm.forward_days}日後の騰落率 ${csign}${c.forward_return_pct}%</li>`;
    })
    .join("");
  el.innerHTML = `
    <div class="pattern-match-box">
      <h3>過去の類似パターン(直近${pm.window_days}日の値動きと比較)</h3>
      <div class="section-stats">類似局面 ${pm.sample_count}件(平均類似度${pm.avg_similarity_pct}%) → その後${pm.forward_days}日で上昇した割合 ${pm.win_rate_pct}%(平均騰落率 ${sign}${pm.avg_forward_return_pct}%)</div>
      <ul class="pattern-case-list">${casesHtml}</ul>
      <div class="section-hint">※直近${pm.window_days}日間の値動きの「形」が過去のどの局面に似ているかを機械的に計算しただけの参考情報です。将来の値動きを保証するものではありません。</div>
    </div>
  `;
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

let _refreshInProgress = false;

// 「今すぐ更新」ボタンの代わりに、画面を一番上までスクロールした状態から下に
// 引っ張る(プルリフレッシュ)と更新が始まるようにする。
async function triggerRefresh() {
  if (_refreshInProgress) return;
  _refreshInProgress = true;
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
  _refreshInProgress = false;
}

// --- プルリフレッシュ(下に引っ張って更新)---
const PULL_THRESHOLD = 70;
const PULL_MAX = 120;
let pullStartY = null;
let pullDist = 0;
let pullActive = false;

function resetPullIndicator() {
  pullIndicator.style.transform = "translateY(-100%)";
  pullIndicator.style.opacity = "0";
  pullDist = 0;
  pullActive = false;
}

document.addEventListener(
  "touchstart",
  (e) => {
    const modalOpen = chartModal && !chartModal.classList.contains("hidden");
    if (window.scrollY <= 0 && !_refreshInProgress && !modalOpen) {
      pullStartY = e.touches[0].clientY;
    } else {
      pullStartY = null;
    }
  },
  { passive: true }
);

document.addEventListener(
  "touchmove",
  (e) => {
    if (pullStartY === null) return;
    const dy = e.touches[0].clientY - pullStartY;
    if (dy > 0 && window.scrollY <= 0) {
      pullActive = true;
      pullDist = Math.min(dy, PULL_MAX);
      pullIndicator.style.transform = `translateY(${pullDist}px)`;
      pullIndicator.style.opacity = String(Math.min(1, pullDist / PULL_THRESHOLD));
      pullIndicator.textContent = pullDist > PULL_THRESHOLD ? "離すと更新します" : "↓ 引っ張って更新";
    }
  },
  { passive: true }
);

document.addEventListener("touchend", () => {
  if (pullActive) {
    if (pullDist > PULL_THRESHOLD) {
      pullIndicator.textContent = "更新中...";
      pullIndicator.style.transform = "translateY(0)";
      pullIndicator.style.opacity = "1";
      triggerRefresh().finally(() => {
        setTimeout(resetPullIndicator, 600);
      });
    } else {
      resetPullIndicator();
    }
  }
  pullStartY = null;
  pullActive = false;
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

showCachedResultsImmediately();
registerServiceWorker();
scheduleNextLoad(true);
