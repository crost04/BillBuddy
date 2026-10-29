// Service worker: makes the app open instantly and even without a connection.
//
// Strategy "stale while revalidate" for the app files (HTML, CSS, JS, icons):
// answer from the cache right away, and load a fresh copy in the background for
// the next start. So the app appears immediately, even while the free server is
// still waking up. After an update, the new version shows from the next start on.
// API data (/api/...) is never cached, so balances are always up to date.

const CACHE = "billbuddy-v2";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  // Remove caches of older versions
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  event.respondWith(staleWhileRevalidate(event));
});

async function staleWhileRevalidate(event) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(event.request);
  // cache: "no-cache" – always ask the server, never take an old copy from the browser's HTTP cache
  const fresh = fetch(event.request, { cache: "no-cache" }).then((response) => {
    // Only keep real answers of the app, not error or waiting pages of the hosting provider
    if (response.ok && response.headers.has("X-BillBuddy")) {
      cache.put(event.request, response.clone());
    }
    return response;
  });

  if (cached) {
    event.waitUntil(fresh.catch(() => {}));
    return cached;
  }
  return fresh;
}
