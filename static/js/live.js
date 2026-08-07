// Connects to the Flask-SocketIO server (same origin, same port as the
// Flask app) and keeps the current page's content in sync with events
// broadcast by the backend — no manual refresh needed.
(function () {
  const body = document.body;
  const livePage = body.dataset.livePage || "none";
  const liveId = body.dataset.liveId || "";

  const socket = io();
  let toastTimer = null;

  function showToast(text) {
    const toast = document.getElementById("live-toast");
    if (!toast) return;
    toast.textContent = text;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2500);
  }

  async function refreshPageContent() {
    try {
      const res = await fetch(window.location.pathname + window.location.search, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!res.ok) return;
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const fresh = doc.getElementById("page-content");
      const current = document.getElementById("page-content");
      if (fresh && current) current.innerHTML = fresh.innerHTML;
    } catch (err) {
      // Live updates are a nicety, not critical — fail quietly and let the
      // user refresh manually if the network hiccups.
      console.warn("Live refresh failed:", err);
    }
  }

  function isRelevant(jobId) {
    if (livePage === "jobs") return true;
    if (livePage === "job-detail") return jobId === liveId;
    return false;
  }

  socket.on("job:new", (job) => {
    if (livePage !== "jobs") return;
    showToast("New dispatch posted");
    refreshPageContent();
  });

  socket.on("job:closed", (data) => {
    if (!isRelevant(data.id)) return;
    showToast("A dispatch just closed");
    refreshPageContent();
  });

  socket.on("application:new", (data) => {
    if (livePage !== "job-detail" || data.job_id !== liveId) return;
    showToast("New applicant");
    refreshPageContent();
  });

  socket.on("application:accepted", (data) => {
    if (livePage !== "job-detail" || data.job_id !== liveId) return;
    showToast("An applicant was accepted");
    refreshPageContent();
  });
})();
