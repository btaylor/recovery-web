// Long-press a cover to see its title (the wall has no labels).
const wall = document.getElementById("wall");
let timer, peeked;
const clear = () => { clearTimeout(timer); document.querySelectorAll(".tile.peeking").forEach(t => t.classList.remove("peeking")); };
wall.addEventListener("pointerdown", e => {
  const tile = e.target.closest(".tile");
  if (tile) timer = setTimeout(() => { tile.classList.add("peeking"); peeked = true; }, 450);
});
["pointerup", "pointerleave", "pointercancel"].forEach(t => wall.addEventListener(t, clear));
wall.addEventListener("contextmenu", e => e.target.closest(".tile") && e.preventDefault());
wall.addEventListener("click", e => { if (peeked) { e.preventDefault(); peeked = false; } });
