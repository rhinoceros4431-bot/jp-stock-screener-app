const CACHE_NAME = "stock-screener-v1";
const APP_SHELL = ["/", "/index.html", "/style.css", "/app.js", "/manifest.json", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// オフライン時は簡易的にキャッシュから返す(APIリクエストはネットワーク優先)
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) return; // APIはキャッシュしない
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});

// プッシュ通知受信
self.addEventListener("push", (event) => {
  let data = { title: "株スクリーニング通知", body: "新しい該当銘柄があります", url: "/" };
  try {
    data = event.data.json();
  } catch (e) {
    /* ignore */
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: data.url || "/" },
    })
  );
});

// 通知タップでアプリを開く
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    clients.matchAll({ type: "window" }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(url) && "focus" in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
