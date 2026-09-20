// Desktop shortcuts (browsers can't see hardware volume keys): space play/pause, ←/→ prev/next, +/- volume.
const KEYS = { " ": "/transport/toggle", ArrowRight: "/transport/next", ArrowLeft: "/transport/prev",
               "+": "/volume?delta=2", "=": "/volume?delta=2", "-": "/volume?delta=-2" };
document.addEventListener("keydown", e => {
  const url = KEYS[e.key];
  if (!url || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.target.closest("input, select, textarea") || (e.key === " " && e.target.closest("button, a"))) return;
  e.preventDefault();
  fetch(url, { method: "POST" }).then(() => htmx.trigger(document.body, "refresh"));
});
