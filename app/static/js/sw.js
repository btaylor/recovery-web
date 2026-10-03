// Lets the app open from the Home Screen without waiting on the network. The static files and the
// home page come from the last copy straight away and refresh in the background, so the next launch
// picks up changes. Covers and the speaker state are never cached: they are always live.
const CACHE = "play-shell-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  const shell = url.pathname.startsWith("/static/") || (e.request.mode === "navigate" && url.pathname === "/");
  if (shell) e.respondWith(staleWhileRevalidate(e.request, e));
});

async function staleWhileRevalidate(request, e) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const fresh = fetch(request).then(r => {
    if (r.ok) cache.put(request, r.clone());
    return r;
  });
  if (!cached) return fresh;
  e.waitUntil(fresh.catch(() => {}));  // offline: keep showing the cached copy
  return cached;
}
