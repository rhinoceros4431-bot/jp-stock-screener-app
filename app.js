const statusText = document.getElementById("status-text");
const subscribeBtn = document.getElementById("subscribe-btn");
const refreshBtn = document.getElementById("refresh-btn");
const updatedAtEl = document.getElementById("updated-at");
const summaryEl = document.getElementById("summary");
const resultsEl = document.getElementById("results");

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

async function loadResults() {
  const data = await fetch("/api/results").then((r) => r.json());
  const isRunning = data.status === "running";
  const progress = data.progress || {};

  if (isRunning) {
    const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
    updatedAtEl.textContent = `更新中... ${progress.done || 0}/${progress.total || "?"}銘柄処理済み (${pct}%)`;
  } else {
    updatedAtEl.textContent = data.updated_at ? `最終更新: ${data.updated_at.replace("T", " ")}` : "まだ実行されていません";
  }
  summaryEl.textContent = `該当銘柄: ${data.results.length}件` + (isRunning ? "(集計中、随時更新されます)" : "");

  resultsEl.innerHTML = "";
  if (data.results.length === 0) {
    resultsEl.innerHTML = isRunning
      ? '<div class="empty-state">スクリーニングを実行中です。しばらくすると該当銘柄が表示されます...</div>'
      : '<div class="empty-state">現在、条件に合致している銘柄はありません。</div>';
    return data.status;
  }
  const newSet = new Set(data.new_match_codes || []);
  for (const r of data.results) {
    const card = document.createElement("div");
    card.className = "stock-card" + (newSet.has(r.code) ? " new" : "");
    const isNew = newSet.has(r.code) ? '<span class="badge-new">NEW</span>' : "";
    card.innerHTML = `
      <div class="name-row">
        <span class="name">${r.name}${isNew}</span>
        <span class="code">${r.code}</span>
      </div>
      <ul>${r.hits.map((h) => `<li>${h}</li>`).join("")}</ul>
    `;
    resultsEl.appendChild(card);
  }
  return data.status;
}

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
