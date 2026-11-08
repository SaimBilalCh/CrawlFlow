/* CrawlFlow control panel — vanilla JS, hash-routed, no build step. */
"use strict";

/* ---------- tiny DOM helper ---------- */
const h = (tag, attrs = {}, ...children) => {
  attrs = attrs || {}; // call sites pass null for "no attributes"
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "html") el.innerHTML = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(child));
  }
  return el;
};

/* ---------- API ---------- */
async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data = {};
  try { data = await response.json(); } catch { /* ignore non-JSON */ }
  if (!response.ok) {
    const detail = data.detail || `Request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}
const postJSON = (path, body) => api(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/* ---------- toasts & modal ---------- */
function toast(message, type = "info") {
  const box = h("div", { class: `toast ${type}` },
    h("span", { class: "toast-msg", text: message }),
    h("button", { class: "close", "aria-label": "Dismiss", text: "✕", onclick: () => box.remove() }));
  document.getElementById("toasts").append(box);
  setTimeout(() => box.remove(), 7000);
}

function confirmDialog({ title, bodyNode, confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const overlay = h("div", { class: "modal-overlay" });
    const close = (result) => { overlay.remove(); resolve(result); };
    overlay.append(h("div", { class: "modal", role: "dialog", "aria-modal": "true" },
      h("h3", { text: title }),
      h("div", { class: "body" }, bodyNode),
      h("div", { class: "actions" },
        h("button", { class: "btn secondary", text: "Cancel", onclick: () => close(false) }),
        h("button", { class: `btn ${danger ? "danger" : ""}`, text: confirmLabel, onclick: () => close(true) }))));
    overlay.addEventListener("click", (event) => { if (event.target === overlay) close(false); });
    document.getElementById("modal-root").append(overlay);
  });
}

/* ---------- small widgets ---------- */
const URL_PATTERN = /^https?:\/\/[^\s"'<>()]+\.[^\s"'<>()]+$/i;
const fmtBytes = (bytes) => {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes, i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
};
const fmtTime = (iso) => { try { return new Date(iso).toLocaleString(); } catch { return iso || "—"; } };

function statusBadge(status) {
  return h("span", { class: `badge ${status}`, text: { pending: "Pending", processing: "Processing", completed: "Completed", failed: "Failed", cancelled: "Cancelled" }[status] || status });
}
function errorBanner(message) {
  return h("div", { class: "error-banner" }, h("span", { html: "⚠️" }), h("span", { text: message }));
}
function successBanner(...children) {
  return h("div", { class: "success-banner" }, h("span", { html: "✅" }), h("span", null, ...children));
}
function emptyState(iconHtml, title, note) {
  return h("div", { class: "empty" },
    h("div", { class: "icon", html: iconHtml }),
    h("div", { class: "title", text: title }),
    h("div", { text: note }));
}
function pageHead(title, sub) {
  return h("div", { class: "page-head" },
    h("h1", { text: title }), h("p", { class: "sub", text: sub }));
}

/* ---------- polling ---------- */
let pollTimer = null;
function poll(fn, ms) { stopPoll(); pollTimer = setInterval(fn, ms); }
function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

/* ---------- state ---------- */
let setupState = null;
let categoriesCache = null;
let currentStore = { stats: {} };
const STATUS_LABELS = { real: "Real video", fake: "AI generated (fake)" };

async function loadCategories() {
  if (!categoriesCache) {
    try { categoriesCache = await api("/api/categories"); }
    catch { categoriesCache = { real: [], fake: [] }; }
  }
  return categoriesCache;
}

/* ---------- sidebar ---------- */
const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "uploads", label: "Upload Links" },
  { id: "drive", label: "Recent Drive Uploads" },
  { id: "history", label: "Activity History" },
  { id: "settings", label: "Settings" },
];

function renderNav(activeId) {
  const nav = document.getElementById("nav");
  nav.textContent = "";
  const stats = currentStore.stats || {};
  const nPending = (stats.pending || 0) + (stats.processing || 0);
  for (const item of NAV_ITEMS) {
    nav.append(h("button", {
      class: `nav-item ${item.id === activeId ? "active" : ""}`,
      onclick: () => { location.hash = `#/${item.id}`; closeSidebar(); },
    }, h("span", { text: item.label }),
      item.id === "uploads" && nPending ? h("span", { class: "nav-badge", text: String(nPending) }) : null));
  }
}

function updateSideStatus(state) {
  const drive = state && state.folder_id_set && state.token_present;
  const queueActive = (currentStore.stats?.processing || 0) > 0;
  document.getElementById("side-status").innerHTML = queueActive
    ? `<span class="dot warn"></span><b>Processing</b>`
    : `<span class="dot ${drive ? "ok" : "bad"}"></span><b>${drive ? "Ready" : "Not configured"}</b> <br><span style="opacity:.75;">${drive ? "Drive · connected" : "Setup incomplete"}</span>`;
}

function closeSidebar() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebar-backdrop").classList.remove("show");
}

/* ---------- shared input-in-label ---------- */
function field(labelText, inputEl, required) {
  return h("div", { class: "field" },
    h("label", null, labelText, required ? h("span", { class: "req", text: " *" }) : null), inputEl);
}

/* =================================================================== */
/* Router                                                               */
/* =================================================================== */
const routes = { dashboard: viewDashboard, uploads: viewUploads, drive: viewDrive, history: viewHistory, settings: viewSettings, setup: viewSetup };

async function navigate() {
  stopPoll();
  const view = document.getElementById("view");
  view.textContent = "";
  try { setupState = await api("/api/setup/state"); }
  catch (error) {
    view.append(errorBanner(`Cannot reach the CrawlFlow backend at this address: ${error.message}`));
    return;
  }
  let route = location.hash.replace("#/", "").split("?")[0] || "dashboard";
  if (!routes[route]) route = "dashboard";
  if (!setupState.complete && route !== "setup") route = "setup";
  if (setupState.complete && route === "setup") route = "dashboard";

  if (route === "uploads" || route === "history") {
    try { currentStore = await api("/api/queue/status"); } catch { /* keep last */ }
  }
  renderNav(route);
  updateSideStatus(setupState);
  try { await routes[route](); }
  catch (error) { view.append(errorBanner(error.message)); }
}

/* =================================================================== */
/* Dashboard                                                            */
/* =================================================================== */
async function viewDashboard() {
  const view = document.getElementById("view");
  view.append(pageHead("Dashboard", "Current state of your CrawlFlow collector."));

  const statsRow = h("div", { class: "stats" });
  for (let i = 0; i < 6; i++) statsRow.append(h("div", { class: "stat" }, h("div", { class: "skeleton" })));

  const quick = h("div", { class: "stats", style: "grid-template-columns:repeat(auto-fill,minmax(180px,1fr));margin-top:16px;" },
    h("button", { class: "btn", text: "＋ Upload a single link", onclick: () => { sessionStorage.setItem("cf-open-single", "1"); location.hash = "#/uploads"; } }),
    h("button", { class: "btn secondary", text: "⇪ Bulk upload links", onclick: () => { location.hash = "#/uploads"; } }),
    h("button", { class: "btn secondary", text: "☁ Recent Drive uploads", onclick: () => { location.hash = "#/drive"; } }),
    h("button", { class: "btn secondary", text: "⚙ Open settings", onclick: () => { location.hash = "#/settings"; } }));

  const recentCard = h("div", { class: "card", style: "margin-top:16px;" },
    h("div", { class: "card-head" },
      h("div", null, h("h2", { text: "Recent processing activity" }), h("p", { class: "hint", text: "The latest processed links" })),
      h("button", { class: "btn secondary small", text: "Full history", onclick: () => { location.hash = "#/history"; } })),
    h("div", { class: "skeleton table-skel" }));
  view.append(statsRow, quick, recentCard);

  function fill(data) {
    const s = data.stats || {};
    const drive = data.drive || {};
    const total = Object.values(s).reduce((a, b) => a + b, 0);
    statsRow.textContent = "";
    statTile(statsRow, "Total links processed", String(total), "all time", "");
    statTile(statsRow, "Successful", String(s.completed || 0), "uploaded to Drive", "ok");
    statTile(statsRow, "Failed", String(s.failed || 0), "can be retried", "bad");
    statTile(statsRow, "In queue", String((s.pending || 0) + (s.processing || 0)), "pending + processing", "warn");
    statTile(statsRow, "Drive videos", String(drive.videos ?? 0), drive.error ? "Drive not connected" : `${drive.used_gb ?? "?"} / ${drive.total_gb ?? "?"} GB used`, "");
    statTile(statsRow, "Drive folders", String(drive.folders ?? 0), "Real / Fake / Metadata", "");

    const holder = recentCard.children[1];
    holder.textContent = "";
    if (!data.recent?.length) holder.append(emptyState("📥", "No activity yet", "Upload links to start processing."));
    else holder.append(h("table", null,
      h("thead", null, h("tr", null, h("th", { text: "Link" }), h("th", { text: "Status" }), h("th", { text: "Finished" }), h("th", { text: "Drive" }))),
      h("tbody", null, data.recent.map((job) => h("tr", null,
        h("td", null, h("a", { class: "cell-url", href: job.url, target: "_blank", rel: "noopener noreferrer", text: job.url })),
        h("td", null, statusBadge(job.status)),
        h("td", { text: fmtTime(job.finished_at) }),
        h("td", null, job.drive_link
          ? h("a", { class: "badge file", href: job.drive_link, target: "_blank", rel: "noopener noreferrer", text: "Open" })
          : h("span", { class: "muted", text: "—" })))))));
  }

  try { fill(await api("/api/dashboard")); }
  catch (error) { view.append(errorBanner(error.message)); }
  poll(async () => {
    try { fill(await api("/api/dashboard")); } catch { /* transient */ }
  }, 5000);
}

function statTile(row, label, value, foot, cls) {
  row.append(h("div", { class: `stat ${cls}` },
    h("div", { class: "label", text: label }),
    h("div", { class: "value", text: value }),
    h("div", { class: "foot", text: foot })));
}

/* =================================================================== */
/* Upload Links — two tabs using one engine                            */
/* =================================================================== */
async function viewUploads() {
  const categories = await loadCategories();
  const view = document.getElementById("view");
  const openSingle = sessionStorage.getItem("cf-open-single") === "1";
  sessionStorage.removeItem("cf-open-single");
  view.append(pageHead("Upload Links", "Send video links to the CrawlFlow engine — download, then upload to Google Drive with label and metadata."));

  let activeTab = openSingle ? "single" : "bulk";
  const tabBar = h("div", { class: "tabs" });
  const content = h("div", null);
  const tabs = {
    bulk: h("button", { class: "tab", text: "Bulk Link Upload" }),
    single: h("button", { class: "tab", text: "Single Link Upload" }),
  };
  for (const [id, button] of Object.entries(tabs)) {
    button.addEventListener("click", () => {
      activeTab = id;
      stopPoll();
      content.textContent = "";
      content.append(id === "bulk" ? bulkPanel(categories) : singlePanel(categories));
      Object.entries(tabs).forEach(([key, b]) => b.classList.toggle("active", key === activeTab));
      currentStore = { stats: {} };
    });
  }
  tabBar.append(tabs.bulk, tabs.single);
  const initial = activeTab === "bulk" ? bulkPanel(categories) : singlePanel(categories);
  content.append(initial);
  tabs[activeTab].classList.add("active");
  view.append(tabBar, content);
}

function labelCategoryFields(categories) {
  const labelSel = h("select", { "aria-label": "Dataset label" },
    h("option", { value: "real", text: STATUS_LABELS.real }),
    h("option", { value: "fake", text: STATUS_LABELS.fake }));
  const categorySel = h("select", { "aria-label": "Category" });
  const fill = () => {
    categorySel.textContent = "";
    (categories[labelSel.value] || []).forEach((cat) =>
      categorySel.append(h("option", { value: cat, text: cat.replaceAll("_", " ") })));
  };
  fill();
  labelSel.addEventListener("change", fill);
  return { labelSel, categorySel };
}

/* ---------- Bulk panel ---------- */
function bulkPanel(categories) {
  let items = [];              // {url, valid, duplicate, reason}
  let submittedIds = null;     // IDs from the last submission
  let usedFileUpload = null;   // FormData file (falls back to JSON POST)

  const container = h("div", null);
  const formBox = h("div", { class: "card card-pad" });
  const { labelSel, categorySel } = labelCategoryFields(categories);

  const textarea = h("textarea", {
    rows: "9",
    placeholder: "https://youtube.com/watch?v=…\nhttps://www.tiktok.com/@user/video/…\n\nOne link per line. Lines starting with # are ignored.",
    oninput: () => parseTextarea(),
  });
  const fileInput = h("input", { type: "file", accept: ".txt,text/plain", style: "display:none;", onchange: (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 1024 * 1024) return toast("File too large (max 1 MB).", "error");
    const reader = new FileReader();
    reader.onload = () => { usedFileUpload = file; textarea.value = String(reader.result || ""); parseTextarea(); toast("Links loaded from file — review below, then start.", "success"); };
    reader.onerror = () => toast("Could not read that file.", "error");
    reader.readAsText(file);
    event.target.value = "";
  } });

  const summaryLine = h("div", { class: "muted", style: "margin-top:10px;" });
  const reviewBox = h("div", { class: "review-list", style: "display:none; margin-top:10px;" });
  const startBtn = h("button", { class: "btn", text: "Start processing", disabled: true, onclick: startBulk });
  const clearBtn = h("button", { class: "btn secondary", text: "Clear all", onclick: async () => {
    if (!items.length) return;
    const ok = await confirmDialog({ title: "Clear all links?", bodyNode: h("p", null, `${items.length} draft line will be removed.`), confirmLabel: "Clear all", danger: true });
    if (!ok) return;
    textarea.value = "";
    usedFileUpload = null;
    items = [];
    renderReview();
  } });
  const actionsRow = h("div", { class: "row", style: "margin-top:14px;" }, startBtn,
    h("button", { class: "btn secondary", text: "Load .txt file", onclick: () => fileInput.click() }),
    clearBtn, h("span", { class: "grow" }), fileInput);

  formBox.append(
    h("div", { class: "form-row" },
      field("Dataset label", labelSel, true),
      field("Category", categorySel, true),
      h("p", { class: "muted", style: "flex-basis:100%;", text: CHOICE_HINT() })),
    field("Video links — one per line", textarea, true),
    summaryLine, reviewBox, actionsRow);
  container.append(formBox);

  function parseTextarea() {
    const lines = textarea.value.replace(/\uFEFF/g, "").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));
    const seen = new Set();
    items = lines.map((url) => {
      if (!URL_PATTERN.test(url)) return { url, valid: false, duplicate: false, reason: "Not a valid http(s) URL" };
      const key = url.toLowerCase();
      if (seen.has(key)) return { url, valid: false, duplicate: true, reason: "Duplicate in this batch" };
      seen.add(key);
      return { url, valid: true, duplicate: false, reason: null };
    });
    renderReview();
  }

  const validItems = () => items.filter((i) => i.valid);
  function renderReview() {
    const valid = validItems().length;
    const invalid = items.length - valid;
    summaryLine.textContent = items.length
      ? `${valid} valid link${valid === 1 ? "" : "s"} · ${invalid} invalid / duplicate`
      : "Paste links or load a .txt file, then review before starting.";
    reviewBox.style.display = items.length ? "block" : "none";
    reviewBox.textContent = "";
    items.forEach((item, index) => {
      reviewBox.append(h("div", { class: `review-item ${item.valid ? "" : item.duplicate ? "duplicate" : "invalid"}` },
        h("span", { class: "n", text: `${index + 1}.` }),
        h("span", { class: "url", text: item.url }),
        item.reason ? h("span", { class: "muted" }, item.reason) : null,
        h("button", { class: "remove-btn", "aria-label": `Remove ${item.url}`, text: "✕", onclick: () => {
          items.splice(index, 1);
          textarea.value = items.map((i) => i.url).join("\n");
          usedFileUpload = items.length ? usedFileUpload : null;
          renderReview();
        } })));
    });
    startBtn.disabled = !valid;
    startBtn.textContent = valid ? `Start processing (${valid} links)` : "Start processing";
  }

  async function startBulk() {
    const links = validItems().map((i) => i.url);
    if (!links.length || startBtn.disabled) return;
    const ok = await confirmDialog({
      title: "Start bulk processing?",
      bodyNode: h("div", null,
        h("p", null, ` ${String(links.length)} link${links.length === 1 ? "" : "s"} will be downloaded and uploaded to Google Drive as “${STATUS_LABELS[labelSel.value]}” in the “${categorySel.value.replaceAll("_", " ")}” category.`),
        h("p", { class: "muted", style: "margin-top:6px;", text: "Processing runs in the background on this machine and continues while you browse other pages." })),
      confirmLabel: "Start processing",
    });
    if (!ok) return;
    try {
      let result;
      if (usedFileUpload) {
        const body = new FormData();
        body.append("file", usedFileUpload);
        result = await api(`/api/jobs/upload?label=${labelSel.value}&category=${encodeURIComponent(categorySel.value)}`, { method: "POST", body });
      } else {
        result = await postJSON("/api/jobs", { urls: links, label: labelSel.value, category: categorySel.value });
      }
      submittedIds = result.accepted.map((a) => a.id);
      renderRunView(result);
      poll(refreshRun, 2000);
      if (result.rejected.length) {
        toast(`${result.rejected.length} link(s) skipped (invalid or already queued).`, "error");
      }
    } catch (error) {
      toast(error.message, "error");
      renderReview();
    }
  }

  function renderRunView(result) {
    const summary = h("div", { class: "success-banner" },
      h("div", null,
        h("p", null, ` ${result.accepted.length} link${result.accepted.length === 1 ? "" : "s"} submitted for processing.`),
        result.rejected.length
          ? h("div", { class: "muted", style: "margin-top:4px;" }, "Skipped: ", result.rejected.map((r) => `${r.url} — ${r.reason}`).join("; "))
          : null));
    const card = h("div", { class: "card", style: "margin-top:16px;" },
      h("div", { class: "card-head" },
        h("div", null, h("h2", { text: "Processing progress" }), h("p", { class: "hint", text: "Live updates — the queue lives on the server, so this survives a page refresh." })),
        h("button", { class: "btn secondary small", text: "Upload more links", onclick: () => { submittedIds = null; container.textContent = ""; container.append(formBox); renderReview(); textarea.focus(); } })),
      h("div", { id: "bulk-run", style: "min-height:60px;" }, " ", h("div", { class: "skeleton table-skel" })));
    container.textContent = "";
    container.append(summary, card);
    refreshRun();
  }

  async function refreshRun() {
    const wrap = document.getElementById("bulk-run");
    if (!wrap || submittedIds == null) return stopPoll();
    let store;
    try { store = await api("/api/queue/status"); } catch { return; }
    currentStore = store;
    const wanted = new Set(submittedIds);
    const jobs = store.jobs.filter((j) => wanted.has(j.id));
    const counts = { completed: 0, failed: 0, pending: 0, processing: 0, cancelled: 0 };
    jobs.forEach((j) => { counts[j.status] = (counts[j.status] || 0) + 1; });
    wrap.textContent = "";
    wrap.append(h("div", { class: "row", style: "padding:14px 16px 4px;" },
      h("span", { class: "badge completed", text: `Completed ${counts.completed}` }),
      h("span", { class: "badge processing", text: `Processing ${counts.processing}` }),
      h("span", { class: "badge pending", text: `Pending ${counts.pending}` }),
      h("span", { class: "badge failed", text: `Failed ${counts.failed}` }),
      counts.cancelled ? h("span", { class: "badge cancelled", text: `Cancelled ${counts.cancelled}` }) : null));
    if (!jobs.length) { wrap.append(emptyState("⏳", "Waiting for updates…", "")); return; }
    wrap.append(h("div", { class: "table-wrap" }, h("table", null,
      h("thead", null, h("tr", null, h("th", { text: "Link" }), h("th", { text: "Status" }), h("th", { text: "Details" }), h("th", { text: "Drive" }), h("th", { text: "" }))),
      h("tbody", null, jobs.map((job) => h("tr", null,
        h("td", null, h("a", { class: "cell-url", href: job.url, target: "_blank", rel: "noopener noreferrer", text: job.url })),
        h("td", null, statusBadge(job.status)),
        h("td", { class: "cell-details" }, job.status === "failed"
          ? h("span", { class: "muted", style: "color:var(--red);", text: job.error || "No error details." })
          : h("span", { class: "muted", text: job.finished_at ? fmtTime(job.finished_at) : "Running…" })),
        h("td", null, job.drive_link
          ? h("a", { class: "badge file", href: job.drive_link, target: "_blank", rel: "noopener noreferrer", text: "Open" })
          : h("span", { class: "muted", text: "—" })),
        h("td", null, job.status === "failed"
          ? retryButton(job)
          : null)))))));
    const anyActive = jobs.some((j) => j.status === "pending" || j.status === "processing");
    if (!anyActive) stopPoll();
  }
  return container;
}

function retryButton(job) {
  const button = h("button", { class: "btn secondary small", text: "Retry", onclick: async () => {
    button.disabled = true;
    try {
      await api(`/api/jobs/${job.id}/retry`, { method: "POST" });
      toast("Link re-queued for processing.", "success");
    } catch (error) { toast(error.message, "error"); button.disabled = false; }
  } });
  return button;
}

/* ---------- Single panel ---------- */
function singlePanel(categories) {
  let currentJobId = null;
  const { labelSel, categorySel } = labelCategoryFields(categories);
  const container = h("div", { class: "card card-pad" });
  const urlInput = h("input", { type: "url", inputmode: "url", placeholder: "https://youtube.com/watch?v=…", autocomplete: "off" });
  const submitBtn = h("button", { class: "btn", text: "Upload / Process", onclick: submitSingle });
  const feedback = h("div", { style: "margin-top:14px;" });

  container.append(
    h("div", { class: "form-row" },
      field("Dataset label", labelSel, true),
      field("Category", categorySel, true),
      h("p", { class: "muted", style: "flex-basis:100%;", text: CHOICE_HINT() })),
    field("Video URL", urlInput, true),
    h("div", { class: "row", style: "margin-top:14px;" }, submitBtn),
    feedback);

  async function submitSingle() {
    const url = urlInput.value.trim();
    if (!URL_PATTERN.test(url)) { toast("Enter a valid http(s) URL.", "error"); return; }
    if (submitBtn.classList.contains("is-busy")) return; // no double submits
    submitBtn.classList.add("is-busy");
    feedback.textContent = "";
    try {
      const result = await postJSON("/api/jobs", { urls: [url], label: labelSel.value, category: categorySel.value });
      if (!result.accepted.length) throw new Error(result.rejected[0]?.reason || "Link rejected.");
      currentJobId = result.accepted[0].id;
      feedback.append(h("div", { class: "card", id: "single-result", style: "margin-top:2px;" },
        h("div", { class: "card-pad row" }, h("div", { class: "spinner dark" }), h("span", { text: "Submitting…" }))));
      poll(refreshSingle, 2000);
      refreshSingle();
    } catch (error) {
      feedback.append(errorBanner(`${error.message}`));
    } finally {
      submitBtn.classList.remove("is-busy");
      submitBtn.disabled = false;
      submitBtn.textContent = "Upload / Process";
    }
  }

  async function refreshSingle() {
    const card = document.getElementById("single-result");
    if (!card || currentJobId == null) return stopPoll();
    let store;
    try { store = await api("/api/queue/status"); } catch { return; }
    currentStore = store;
    const job = store.jobs.find((j) => j.id === currentJobId);
    if (!job) return;
    const pad = card.querySelector(".card-pad");
    pad.textContent = "";
    if (job.status === "pending" || job.status === "processing") {
      pad.append(h("div", { class: "spinner dark" }), h("span", { text: job.status === "pending" ? "Waiting in queue…" : "Downloading and uploading…" }));
      pad.classList.add("row");
      return;
    }
    stopPoll();
    pad.classList.remove("row");
    if (job.status === "completed") {
      pad.append(successBanner(
        h("span", null,
          "Uploaded to Google Drive: ",
          h("strong", { text: job.drive_name || "file" }), " — ",
          h("a", { href: job.drive_link, target: "_blank", rel: "noopener noreferrer", text: "Open in Drive" })),
        h("div", { class: "muted", style: "margin-top:6px; width:100%;" },
          `Took ${job.duration_s ?? "?"} s · ${STATUS_LABELS[job.label]} · ${job.category.replaceAll("_", " ")}`)));
    } else {
      pad.append(h("div", { class: "error-banner" }, h("span", { html: "❌" }),
        h("span", { text: job.error || "Processing failed." }),
        retryButton(job)));
    }
  }
  return container;
}

const CHOICE_HINT = () =>
  "Label and category are used to organise the upload inside Google Drive (Real_Videos / Fake_Videos + filenames).";

/* =================================================================== */
/* Recent Drive uploads                                                 */
/* =================================================================== */
async function viewDrive() {
  const view = document.getElementById("view");
  view.append(pageHead("Recent Drive Uploads", "Newest files and folders uploaded by CrawlFlow to the configured Google Drive location."));
  const body = h("div", null);
  view.append(body);

  let search = "";
  const PAGE = 30;
  let items = [];
  let shown = 0;

  let searchDebounce = null;
  const searchInput = h("input", { type: "text", placeholder: "Search by name or source URL…", style: "max-width:300px;", oninput: () => {
    search = searchInput.value.trim().toLowerCase();
    shown = 0;
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(load, 350);
  } });
  const refreshBtn = h("button", { class: "btn secondary", text: "↻ Refresh", onclick: load });
  const bar = h("div", { class: "row", style: "margin-bottom:16px;" }, searchInput, refreshBtn);
  body.append(bar);

  const listWrap = h("div", { class: "card" }, h("div", { style: "padding:24px;" }, h("div", { class: "skeleton table-skel" })));
  body.append(listWrap);

  async function load() {
    refreshBtn.disabled = true;
    listWrap.textContent = "";
    listWrap.append(h("div", { style: "padding:24px;" }, h("div", { class: "skeleton table-skel" })));
    try {
      const data = await api(`/api/drive/uploads${search ? `?search=${encodeURIComponent(search)}` : ""}`);
      items = data.items || [];
      shown = 0;
      render();
    } catch (error) {
      listWrap.textContent = "";
      listWrap.append(errorBanner(`Could not list Drive uploads: ${error.message}`));
    } finally {
      refreshBtn.disabled = false;
    }
  }

  function render() {
    listWrap.textContent = "";
    listWrap.append(h("div", { class: "card-head" },
      h("div", null, h("h2", { text: "Newest first" }), h("p", { class: "hint", text: `${items.length} item${items.length === 1 ? "" : "s"}${search ? ` matching “${search}”` : ""}` }))));
    if (!items.length) {
      listWrap.append(emptyState("🈳", search ? "Nothing matches that search" : "No uploads yet", search ? "Try a different search." : "Processed links will show up here after they upload to Drive."));
      return;
    }
    listWrap.append(h("div", { class: "table-wrap" }, h("table", null,
      h("thead", null, h("tr", null,
        h("th", { text: "Name" }), h("th", { text: "Type" }), h("th", { text: "Location" }), h("th", { text: "Uploaded" }), h("th", { text: "Source URL" }), h("th", { text: "Size" }), h("th", { text: "Drive" }))),
      h("tbody", null, items.slice(0, shown + PAGE).map((item) => h("tr", null,
        h("td", null, h("span", { html: item.kind === "folder" ? icon.folder : icon.file }), " ", h("span", { title: item.name, text: item.name })),
        h("td", null, h("span", { class: `badge ${item.kind === "folder" ? "folder" : "file"}`, text: item.kind === "folder" ? "Folder" : item.name.toLowerCase().endsWith(".mp4") ? "Video" : "File" })),
        h("td", { text: item.folder || "—" }),
        h("td", { text: fmtTime(item.modified_time) }),
        h("td", null, item.source_url
          ? h("a", { class: "cell-url", href: item.source_url, target: "_blank", rel: "noopener noreferrer", text: item.source_url })
          : h("span", { class: "muted", text: "—" })),
        h("td", { text: item.kind === "folder" ? "—" : fmtBytes(item.size_bytes) }),
        h("td", null, item.drive_link ? h("a", { href: item.drive_link, target: "_blank", rel: "noopener noreferrer", text: "Open in Drive ↗" }) : null)))))));
    shown = Math.min(shown + PAGE, items.length);
    if (items.length > shown) {
      listWrap.append(h("div", { style: "padding:14px; text-align:center;" },
        h("button", { class: "btn secondary", text: `Load more (${items.length - shown} remaining)`, onclick: render })));
    }
  }

  await load();
}

/* =================================================================== */
/* Activity history                                                     */
/* =================================================================== */
async function viewHistory() {
  const view = document.getElementById("view");
  view.append(pageHead("Activity History", "Every link processed through CrawlFlow, with results and errors. Stored on disk, so it survives restarts."));
  const chips = h("div", { class: "chips", style: "margin-bottom:16px;" });
  const FILTERS = [
    { id: "all", label: "All" },
    { id: "completed", label: "Successful" },
    { id: "failed", label: "Failed" },
    { id: "active", label: "Pending / Processing" },
  ];
  let filter = "all";
  for (const f of FILTERS) {
    const chip = h("button", { class: `chip ${f.id === "all" ? "active" : ""}`, text: f.label, onclick: () => {
      filter = f.id;
      chips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      renderList();
    } });
    chips.append(chip);
  }
  const listCard = h("div", { class: "card" });
  view.append(chips, listCard);

  let store = null;
  try { store = await api("/api/queue/status"); currentStore = store; }
  catch (error) { listCard.append(errorBanner(error.message)); }

  function renderList() {
    const card = listCard;
    card.textContent = "";
    const jobs = (store?.jobs || []).filter((job) => {
      if (filter === "all") return job.status !== "cancelled";
      if (filter === "active") return job.status === "pending" || job.status === "processing";
      return job.status === filter;
    });
    card.append(h("div", { class: "card-head" },
      h("div", null, h("h2", { text: FILTERS.find((f) => f.id === filter).label }),
        h("p", { class: "hint", text: `${jobs.length} entr${jobs.length === 1 ? "y" : "ies"}` }))));
    if (!jobs.length) {
      card.append(emptyState("📜", "Nothing here", filter === "all" ? "Upload links to build history." : "No entries match this filter."));
      return;
    }
    card.append(h("div", { class: "table-wrap" }, h("table", null,
      h("thead", null, h("tr", null,
        h("th", { text: "Link" }), h("th", { text: "Status" }), h("th", { text: "When" }), h("th", { text: "Duration" }),
        h("th", { text: "Label / Category" }), h("th", { text: "Result" }), h("th", { text: "Error" }), h("th", { text: "" }))),
      h("tbody", null, jobs.map((job) => h("tr", null,
        h("td", null, h("a", { class: "cell-url", href: job.url, target: "_blank", rel: "noopener noreferrer", text: job.url })),
        h("td", null, statusBadge(job.status)),
        h("td", { class: "muted", text: fmtTime(job.started_at || job.queued_at) }),
        h("td", { class: "muted", text: job.duration_s != null ? `${job.duration_s} s` : "—" }),
        h("td", null, h("span", { class: "badge platform", text: `${job.label} · ${job.category?.replaceAll("_", " ")}` })),
        h("td", null, job.drive_link
          ? h("a", { class: "badge file", href: job.drive_link, target: "_blank", rel: "noopener noreferrer", text: "Open" })
          : h("span", { class: "muted", text: "—" })),
        h("td", { class: "muted", text: job.error || "" }),
        h("td", null, job.status === "failed" ? retryButton(job) : null)))))));
  }
  renderList();
}

/* =================================================================== */
/* Settings                                                             */
/* =================================================================== */
async function viewSettings() {
  const view = document.getElementById("view");
  view.append(pageHead("Settings", "Manage CrawlFlow integrations and behaviour. Values persist in .env and are validated before use."));

  let settings;
  try { settings = await api("/api/settings"); }
  catch (error) { view.append(errorBanner(error.message)); return; }

  /* ---------- A. Drive ---------- */
  const driveBox = h("div", { class: "card" });
  driveBox.append(h("div", { class: "card-head" }, h("div", null,
    h("h2", { text: "Google Drive" }),
    h("p", { class: "hint", text: "Where processed videos are uploaded. Stored in CrawlFlow-bot/.env as DRIVE_FOLDER_ID." }))));

  const drivePad = h("div", { class: "card-pad" });
  driveBox.append(drivePad);
  checkRow(drivePad, "OAuth client file (credentials.json)", settings.drive.credentials_present,
    "credentials/credentials.json is part of the Google Cloud OAuth setup. Replace it from the setup wizard if wrong.");
  checkRow(drivePad, "Drive authorization (token.json)", settings.drive.token_present,
    settings.drive.auth_state === "pending" ? "Google sign-in is open — approve the window on this machine." :
    settings.drive.token_present ? "Previously authorized. If uploads fail, re-authorize below." : "Not authorized yet — click Connect below.");
  checkRow(drivePad, "Destination folder ID set", !!settings.drive.folder_id, "The Drive folder where Real_Videos / Fake_Videos / Metadata sub-folders live.");

  const folderInput = h("input", { type: "text", class: "input-secure", value: settings.drive.folder_id || "", placeholder: "e.g. 1AbCdE…folder ID from the Drive URL", spellcheck: "false" });
  const saveDriveBtn = h("button", { class: "btn", text: "Save folder ID", onclick: saveFolder });
  const testBtn = h("button", { class: "btn secondary", text: "Test connection", onclick: testDrive });
  const testResult = h("div", { style: "margin-top:10px;" });
  drivePad.append(
    field("Drive folder ID", folderInput, true),
    h("div", { class: "row", style: "margin-top:12px;" }, saveDriveBtn, testBtn),
    testResult);

  // OAuth connect row
  const authRow = h("div", { class: "row", style: "margin-top:14px;" });
  const connectBtn = h("button", { class: "btn secondary", onclick: startOAuth });
  const authBox = h("div", { class: "row" }, connectBtn);
  authRow.append(authBox);
  drivePad.append(h("div", { class: "muted", style: "margin-top:16px;", text: "Authorization" }), authRow);
  updateConnectButton();

  async function saveFolder() {
    saveDriveBtn.disabled = true;
    try {
      await postJSON("/api/settings", { folder_id: folderInput.value.trim() });
      toast("Drive folder saved.", "success");
      testDrive();
    } catch (error) { toast(`Save failed: ${error.message}`, "error"); }
    saveDriveBtn.disabled = false;
  }
  async function testDrive() {
    testBtn.disabled = true;
    testResult.textContent = "";
    testResult.append(h("div", { class: "row muted" }, h("div", { class: "spinner dark" }), h("span", { text: "Contacting Google Drive…" })));
    try {
      const result = await api("/api/drive/test");
      testResult.textContent = "";
      testResult.append(result.ok
        ? successBanner(h("span", { text: result.detail }))
        : errorBanner(result.detail || "Connection failed."));
    } catch (error) { testResult.textContent = ""; testResult.append(errorBanner(`${error.message}`)); }
    testBtn.disabled = false;
    updateConnectButton();
  }
  function updateConnectButton() {
    connectBtn.textContent = settings.drive.auth_state === "pending"
      ? "Waiting for Google sign-in…"
      : (settings.drive.token_present ? "Re-authorize Google (new browser window)" : "Connect Google Drive (opens browser)");
    connectBtn.disabled = settings.drive.auth_state === "pending";
  }
  async function startOAuth() {
    if (settings.drive.auth_state === "pending") return;
    try {
      await api("/api/drive/auth", { method: "POST" });
      toast("A Google sign-in window should open on this machine. Approve it there.", "info");
      settings.drive.auth_state = "pending";
      updateConnectButton();
      pollCheck();
    } catch (error) { toast(error.message, "error"); }
  }
  let authPollTimer = null;
  function pollCheck() {
    if (authPollTimer) clearInterval(authPollTimer);
    authPollTimer = setInterval(async () => {
      try {
        const state = await api("/api/drive/auth");
        if (state.state === "done") {
          clearInterval(authPollTimer); authPollTimer = null;
          connectBtn.disabled = false;
          connectBtn.textContent = "Re-authorize Google (new browser window)";
          toast("Google Drive authorized.", "success");
          testDrive();
        } else if (state.state === "failed") {
          clearInterval(authPollTimer); authPollTimer = null;
          connectBtn.disabled = false;
          connectBtn.textContent = "Connect Google Drive (opens browser)";
          toast(`Authorization failed: ${state.error || "unknown error"}`, "error");
        }
      } catch { /* keep polling through restarts */ }
    }, 2000);
  }
  view.append(driveBox);

  /* ---------- B. Crawler ---------- */
  const crawlBox = h("div", { class: "card" });
  crawlBox.append(h("div", { class: "card-head" }, h("div", null,
    h("h2", { text: "CrawlFlow engine" }),
    h("p", { class: "hint", text: "Processing targets and batch size. Persisted as CRAWLFLOW_* keys in .env." }))));
  const batchSize = h("input", { type: "number", min: "1", max: "100", value: String(settings.crawler.batch_size) });
  const targetReal = h("input", { type: "number", min: "1", value: String(settings.crawler.target_real) });
  const targetFake = h("input", { type: "number", min: "1", value: String(settings.crawler.target_fake) });
  const saveCrawlBtn = h("button", { class: "btn", text: "Save engine settings", onclick: async () => {
    saveCrawlBtn.disabled = true;
    try {
      await postJSON("/api/settings", {
        batch_size: Number(batchSize.value), target_real: Number(targetReal.value), target_fake: Number(targetFake.value),
      });
      toast("Engine settings saved.", "success");
    } catch (error) { toast(`Save failed: ${error.message}`, "error"); }
    saveCrawlBtn.disabled = false;
  } });
  crawlBox.append(h("div", { class: "card-pad" },
    h("div", { class: "form-row" },
      field("Batch size (videos per scheduled run)", batchSize, true),
      field("Target: real videos", targetReal, true),
      field("Target: fake videos", targetFake, true)),
    h("div", { class: "muted", text: "Platforms in use: " + Object.entries(settings.platforms).map(([name, cfg]) => `${name} (${cfg.enabled ? "enabled" : "disabled"})`).join(", ") + ". Cookies are read from the cookies/ folder." }),
    h("div", { class: "row", style: "margin-top:14px;" }, saveCrawlBtn)));

  view.append(crawlBox);

  /* ---------- C. System status ---------- */
  const sysBox = h("div", { class: "card" });
  sysBox.append(h("div", { class: "card-head" }, h("div", null,
    h("h2", { text: "System status" }),
    h("p", { class: "hint", text: "Live checks — nothing is cached." }))));
  const sysPad = h("div", { class: "card-pad" });
  checkRow(sysPad, "First-time setup", setupState.complete, setupState.complete ? "Configuration has completed and been validated at least once." : "Not finished — finish the setup wizard.");
  checkRow(sysPad, "Drive credentials present", settings.drive.credentials_present, "Google OAuth client file.");
  checkRow(sysPad, "Drive token present", settings.drive.token_present, "Authorization from a previous sign-in.");
  checkRow(sysPad, "Drive folder ID configured", !!settings.drive.folder_id, "Destination folder for uploads.");
  const checkSetupBtn = h("button", { class: "btn secondary", text: "Re-validate setup", onclick: async () => {
    checkSetupBtn.disabled = true;
    try {
      const result = await api("/api/setup/complete", { method: "POST" });
      toast("Setup re-validated successfully.", "success");
    } catch (error) {
      toast(`Setup validation failed: ${error.message}`, "error");
    }
    checkSetupBtn.disabled = false;
  } });
  const resetSetupBtn = h("button", { class: "btn danger", text: "Reset first-time setup…", onclick: async () => {
    const ok = await confirmDialog({ title: "Show setup wizard again on next load?",
      bodyNode: h("p", null, "Existing settings and stored links are kept. The setup wizard will appear on the next page load."),
      confirmLabel: "Reset setup", danger: true });
    if (!ok) return;
    try { await api("/api/setup/reset", { method: "POST" }); location.hash = "#/setup"; }
    catch (error) { toast(error.message, "error"); }
  } });
  sysPad.append(h("div", { class: "row", style: "margin-top:14px;" }, checkSetupBtn, resetSetupBtn));
  sysBox.append(sysPad);
  view.append(sysBox);
}

function checkRow(parent, label, ok, note) {
  parent.append(h("div", { class: "check-row" },
    h("span", { class: `check-mark ${ok ? "ok" : "bad"}`, text: ok ? "✓" : "!" }),
    h("div", null, h("p", { class: "text", style: "font-weight:560;", text: label }),
      h("p", { class: "muted", style: "margin-top:2px;", text: note }))));
}

/* =================================================================== */
/* First-time setup wizard                                              */
/* =================================================================== */
async function viewSetup() {
  const view = document.getElementById("view");
  const categories = await loadCategories();

  let state;
  try { state = await api("/api/setup/state"); }
  catch (error) { view.append(errorBanner(error.message)); return; }

  let step = 1;
  const wrap = h("div", { class: "wizard-wrap" });
  const dots = h("div", { class: "wizard-progress" });
  const stepBox = h("div", { class: "card card-pad", style: "min-height:280px;" });
  const navRow = h("div", { class: "wizard-nav" },
    h("button", { class: "btn secondary", text: "← Back", onclick: () => { if (step > 1) { step--; render(); } } }),
    h("button", { class: "btn", id: "wiz-next", text: "Continue →" }));

  wrap.append(pageHead("Welcome to CrawlFlow", "First-time setup — connect Google Drive and the processing engine before you start collecting."));
  wrap.append(dots, stepBox, navRow);
  view.append(wrap);

  const nextBtn = navRow.querySelector("#wiz-next");
  nextBtn.addEventListener("click", () => {
    if (step === 1 && canContinue1()) { step = 2; render(); }
    else if (step === 2 && canContinue2()) { step = 3; render(); }
    else if (step === 3) finishSetup();
  });

  function refreshStateGate() {
    dots.textContent = "";
    [1, 2, 3].forEach((s) => dots.append(h("span", { class: `step-dot ${s <= step ? "done" : ""}` })));
    nextBtn.disabled = (step === 1 && !canContinue1()) || (step === 2 && !canContinue2());
    if (step === 3) nextBtn.textContent = "Finish setup ✓";
    else if (step === 2) nextBtn.textContent = "Continue →";
    else nextBtn.textContent = "Continue →";
  }

  function canContinue1() {
    return state.credentials_present && state.token_present;
  }
  function canContinue2() {
    return !!state.folder_id_set;
  }

  function render() {
    stepBox.textContent = "";
    refreshStateGate();
    if (step === 1) renderStep1(); else if (step === 2) renderStep2(); else renderStep3();
    navRow.querySelector(".btn.secondary").style.visibility = step === 1 ? "hidden" : "visible";
  }

  function renderStep1() {
    stepBox.append(h("h2", { style: "margin-bottom:6px;", text: "Step 1 · Google credentials" }),
      h("p", { class: "muted", text: "CrawlFlow uploads accepted videos to your Google Drive. It needs (a) an OAuth client file and (b) your authorisation. Nothing is sent anywhere else — everything runs on this machine." }));
    if (state.credentials_present) {
      stepBox.append(successBanner(h("span", null, "OAuth client file found (credentials/credentials.json).")));
    } else {
      const credFile = h("input", { type: "file", accept: ".json", style: "display:none;", onchange: async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        const body = new FormData();
        body.append("file", file);
        try {
          await api("/api/setup/credentials", { method: "POST", body });
          toast("OAuth client saved.", "success");
          state = await api("/api/setup/state");
          render();
        } catch (error) { toast(error.message, "error"); }
      } });
      stepBox.append(errorBanner("credentials/credentials.json is missing — it comes from your Google Cloud Console (OAuth client of type “Desktop app”)."),
        h("div", { class: "row", style: "margin-top:12px;" },
          h("button", { class: "btn", text: "Upload credentials.json", onclick: () => credFile.click() }), credFile));
    }
    if (state.token_present) {
      stepBox.append(h("div", { class: "muted", style: "margin-top:12px;", text: "✓ Already authorized on this machine. You can continue — use “Re-authorize” in step 2 if uploads ever fail." }));
    } else {
      stepBox.append(h("div", { class: "muted", style: "margin-top:12px;", text: "You'll authorize Google in step 2 — click the Connect button there." }));
    }
    refreshStateGate();
  }

  function renderStep2() {
    stepBox.append(h("h2", { style: "margin-bottom:6px;", text: "Step 2 · Authorize Google & choose your folder" }));
    if (!state.token_present) {
      const connect = h("button", { class: "btn", text: "Connect Google Drive (opens browser)", onclick: async () => {
        try {
          await api("/api/drive/auth", { method: "POST" });
          toast("Approve the Google window that opened on this machine.", "info");
          connect.textContent = "Waiting for Google sign-in…";
          connect.disabled = true;
          const timer = setInterval(async () => {
            try {
              const authState = await api("/api/drive/auth");
              if (authState.state === "done") { clearInterval(timer); state = await api("/api/setup/state"); render(); toast("Google Drive authorized.", "success"); }
              else if (authState.state === "failed") { clearInterval(timer); state = await api("/api/setup/state"); render(); toast(`Authorization failed: ${authState.error || ""}`, "error"); }
            } catch { /* retry */ }
          }, 2000);
        } catch (error) { toast(error.message, "error"); }
      } });
      stepBox.append(h("p", { class: "muted", text: "Click below — a Google window opens on this machine. Nothing happens until you approve it there." }),
        h("div", { class: "row", style: "margin-top:12px;" }, connect));
    } else {
      stepBox.append(successBanner(h("span", null, "Google Drive is authorized.")));
    }

    if (state.folder_id_set) {
      const check = h("div", { class: "row", style: "margin-top:16px;" },
        h("button", { class: "btn secondary", text: "Test connection", onclick: async () => {
          try { const r = await api("/api/drive/test"); r.ok ? toast(r.detail, "success") : toast(r.detail, "error"); }
          catch (error) { toast(error.message, "error"); }
        } }));
      stepBox.append(successBanner(h("span", null, "Destination folder ID is set.")), check);
    } else {
      const folderInput = h("input", { type: "text", placeholder: "Paste the folder ID (e.g. 1AbCdE…)", class: "input-secure" });
      stepBox.append(
        h("p", { class: "muted", style: "margin-top:16px;", text: "Create (or pick) the Google Drive folder that will hold Real_Videos / Fake_Videos / Metadata. Copy its ID from the URL: drive.google.com/drive/folders/<THAT_ID>." }),
        field("Drive folder ID", folderInput, true),
        h("div", { class: "row", style: "margin-top:12px;" },
          h("button", { class: "btn", text: "Save & test folder", onclick: async () => {
            try {
              await postJSON("/api/settings", { folder_id: folderInput.value.trim() });
              const test = await api("/api/drive/test");
              state = await api("/api/setup/state");
              if (test.ok) { toast("Folder connected: " + test.detail, "success"); render(); }
              else toast("Folder saved, but test failed: " + test.detail, "error");
            } catch (error) { toast(error.message, "error"); }
          } })));
    }
    refreshStateGate();
  }

  function renderStep3() {
    stepBox.append(h("h2", { style: "margin-bottom:6px;", text: "Step 3 · Ready to collect" }));
    checkRow(stepBox, "OAuth client file present", state.credentials_present, "credentials/credentials.json");
    checkRow(stepBox, "Google Drive authorized", state.token_present, "credentials/token.json");
    checkRow(stepBox, "Destination folder set & reachable", state.folder_id_set, "Validated with a live Drive API call on finish.");
    stepBox.append(h("p", { class: "muted", style: "margin-top:14px;", text: "Click “Finish setup”. The wizard will not appear again on future visits — everything is editable later in Settings." }));
    refreshStateGate();
  }

  async function finishSetup() {
    nextBtn.disabled = true;
    nextBtn.textContent = "Validating…";
    try {
      await api("/api/setup/complete", { method: "POST" });
      setupState = await api("/api/setup/state");
      toast("Setup complete — welcome to CrawlFlow!", "success");
      location.hash = "#/dashboard";
    } catch (error) {
      stepBox.append(errorBanner(`Setup could not be completed: ${error.message}`));
      toast("Setup incomplete — fix the highlighted items and retry.", "error");
      nextBtn.textContent = "Finish setup ✓";
      nextBtn.disabled = false;
    }
  }

  render();
}

/* ---------- boot ---------- */
document.getElementById("hamburger").addEventListener("click", () => {
  document.getElementById("sidebar").classList.add("open");
  document.getElementById("sidebar-backdrop").classList.add("show");
});
document.getElementById("sidebar-backdrop").addEventListener("click", closeSidebar);
window.addEventListener("hashchange", navigate);
navigate();
