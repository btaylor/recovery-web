// Behind a login proxy (e.g. Authelia), an expired session makes every htmx request fail: either a
// redirect to the login page that the browser blocks (sendError) or a 401. When that happens, or when
// the app comes back to the foreground, ask the server directly. If the proxy turns us away, reload
// so it can send us through its login and back here. Offline (the fetch throws) leaves the page alone.
let checking = false;

async function checkSession() {
  if (checking) return;
  checking = true;
  try {
    const r = await fetch("/healthz", { redirect: "manual", cache: "no-store" });
    if (r.type === "opaqueredirect" || r.status === 401) await reloadPastCache();
  } catch {
    // offline or the server is down: nothing to do until it's back
  } finally {
    checking = false;
  }
}

// The service worker answers "/" from its cache, which would just show this page again. Drop that
// copy first so the reload reaches the proxy.
async function reloadPastCache() {
  if (window.caches) {
    for (const name of await caches.keys()) await (await caches.open(name)).delete("/");
  }
  location.replace("/");
}

document.body.addEventListener("htmx:sendError", checkSession);
document.body.addEventListener("htmx:responseError", e => { if (e.detail.xhr.status === 401) checkSession(); });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") checkSession(); });
