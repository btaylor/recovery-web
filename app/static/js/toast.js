// When an htmx request fails, show the server's short message (plain text) as a toast.
// Anything else (an unexpected 500 page) gets a generic message instead of raw HTML.
const toast = document.getElementById("toast");
let hideTimer;
document.body.addEventListener("htmx:responseError", e => {
  const xhr = e.detail.xhr;
  if (xhr.status === 401) return;  // logged out: auth.js reloads into the login instead
  const plain = (xhr.getResponseHeader("Content-Type") || "").startsWith("text/plain");
  toast.textContent = (plain && xhr.responseText.trim()) || "Something went wrong.";
  toast.hidden = false;
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => { toast.hidden = true; }, 5000);
});
