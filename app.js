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
  updatedAtEl.textContent = data.updated_at ? `最終更新: ${data.updated_at.replace("T", " ")}` : "まだ実行されていません";
  summaryEl.textContent = `該当銘柄: ${data.results.length}件`;

  resultsEl.innerHTML = "";
  if (data.results.length === 0) {
    resultsEl.innerHTML = '<div class="empty-state">現在、条件に合致している銘柄はありません。</div>';
    return;
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
}

subscribeBtn.addEventListener("click", () => subscribeToPush().catch((e) => {
  statusText.textContent = "エラー: " + e.message;
}));

refreshBtn.addEventListener("click", async () => {
  refreshBtn.disabled = true;
  statusText.textContent = "スクリーニングを開始しました(数分かかります)...";
  try {
    const resp = await fetch("/api/run-now", { method: "POST" });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      statusText.textContent = "エラー: " + (data.error || resp.status);
    }
  } catch (e) {
    statusText.textContent = "エラー: " + e.message;
  }
  refreshBtn.disabled = false;
});

registerServiceWorker();
loadResults();
setInterval(loadResults, 300000); // 5分ごとに画面上の結果を再取得(無料枠のリクエスト数節約のため)
