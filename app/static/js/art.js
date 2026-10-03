// Tap album art in the album detail or now-playing panel to see it full screen; tap anywhere to close.
// Delegated from document because the now-playing panel's art is swapped every few seconds by htmx.
const full = document.getElementById("art-full");
document.addEventListener("click", e => {
  const art = e.target.closest(".panel__art img, .np__art > img");
  if (!art) return;
  full.querySelector("img").src = art.src.replace(/size=\d+/, "size=1000");
  full.classList.add("open");
});
full.addEventListener("click", () => full.classList.remove("open"));
