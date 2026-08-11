const state = { entries: [], tasks: [], drafts: [], filter: "all", activeEntry: null };

const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => {
  const node = document.createElement("span");
  node.textContent = String(value ?? "");
  return node.innerHTML;
};
const relativeDate = (value) => {
  const date = new Date(value);
  const days = Math.round((Date.now() - date.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return `${days} days ago`;
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

function showNotice(message, error = false) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("is-error", error);
}

function emptyState(title, copy, actionLabel, action) {
  return `<div class="empty-state"><p class="empty-mark" aria-hidden="true">⌇</p><h3>${escapeHTML(title)}</h3><p>${escapeHTML(copy)}</p>${actionLabel ? `<button class="text-link" type="button" data-action="${action}">${escapeHTML(actionLabel)} <span aria-hidden="true">↗</span></button>` : ""}</div>`;
}

function entryCard(entry) {
  const tags = entry.tags.slice(0, 3).map((tag) => `<span>${escapeHTML(tag)}</span>`).join("");
  const domain = entry.url ? new URL(entry.url).hostname.replace(/^www\./, "") : entry.source;
  return `<article class="entry-card"><div class="entry-meta"><span>${escapeHTML(entry.origin)}</span><span>${escapeHTML(domain)}</span><span>${relativeDate(entry.updated_at)}</span></div><button class="entry-open" type="button" data-open-entry="${entry.id}"><h3>${escapeHTML(entry.title)}</h3><p>${escapeHTML(entry.summary || "No note yet — open this and leave a thought for future you.")}</p></button><div class="entry-footer"><div class="tag-list">${tags}</div><span class="status-dot status-${entry.status}">${escapeHTML(entry.status)}</span></div></article>`;
}

function renderFocus() {
  const current = state.entries.filter((entry) => entry.status !== "archived").slice(0, 3);
  $("#focus-list").innerHTML = current.length
    ? current.map((entry, index) => `<button class="focus-row" type="button" data-open-entry="${entry.id}"><span>0${index + 1}</span><strong>${escapeHTML(entry.title)}</strong><em>${escapeHTML(entry.source)}</em><i aria-hidden="true">↗</i></button>`).join("")
    : emptyState("Your margin is clear.", "Save one article, paper, or link you want to think with.", "Save your first thing", "capture");
}

function renderReview() {
  const openTasks = state.tasks.filter((task) => !task.done);
  const drafts = state.drafts.filter((draft) => draft.status === "draft");
  $("#review-count").textContent = `${openTasks.length + drafts.length} open loop${openTasks.length + drafts.length === 1 ? "" : "s"}`;
  const taskRows = openTasks.slice(0, 3).map((task) => `<label class="task-row"><input type="checkbox" data-task-id="${task.id}" /><span>${escapeHTML(task.title)}</span><small>${task.entry_id ? "from reading" : "standalone"}</small></label>`).join("");
  const draftRows = drafts.slice(0, 2).map((draft) => `<button class="draft-link" type="button" data-open-draft="${draft.id}"><span>Draft</span>${escapeHTML(draft.title)}<i aria-hidden="true">↗</i></button>`).join("");
  $("#review-list").innerHTML = taskRows || draftRows
    ? `${taskRows}${draftRows}`
    : emptyState("Nothing is tugging at you.", "When a saved thought becomes a task or draft, it will show up here.", "Start a draft", "draft");
}

function renderEntries() {
  const visible = state.filter === "all" ? state.entries : state.entries.filter((entry) => entry.status === state.filter);
  $("#entry-list").innerHTML = visible.length
    ? visible.map(entryCard).join("")
    : emptyState("No entries here yet.", "Your saved links, forwarded emails, and Wall discoveries will live here.", "Save something", "capture");
}

function renderDrafts() {
  $("#draft-list").innerHTML = state.drafts.length
    ? state.drafts.map((draft) => `<article class="draft-card"><div><p class="eyebrow">${draft.status === "published" ? "Published" : "In progress"}</p><h3>${escapeHTML(draft.title)}</h3><p>${escapeHTML(draft.body || "A blank page with its sources waiting.")}</p></div><div class="draft-card-footer"><span>${draft.status === "published" ? `<a href="/read/${encodeURIComponent(draft.slug)}" target="_blank" rel="noreferrer">Read post ↗</a>` : `${relativeDate(draft.updated_at)} · private`}</span><button class="text-link" type="button" data-open-draft="${draft.id}">Open studio <span aria-hidden="true">↗</span></button></div></article>`).join("")
    : emptyState("Your next post begins in the margin.", "Choose a saved source card and give the thought a title.", "Start a draft", "draft");
}

async function loadWorkspace() {
  try {
    [state.entries, state.tasks, state.drafts] = await Promise.all([
      request("/api/reading/entries"),
      request("/api/reading/tasks"),
      request("/api/reading/drafts"),
    ]);
    renderFocus();
    renderReview();
    renderEntries();
    renderDrafts();
  } catch (error) {
    showNotice(error.message, true);
  }
}

function openDialog(id) {
  $(id).showModal();
}

function closeDialog(id) {
  $(id).close();
}

async function openEntry(entryId) {
  try {
    state.activeEntry = await request(`/api/reading/entries/${entryId}`);
    const entry = state.activeEntry;
    const notes = entry.notes.length ? entry.notes.map((note) => `<blockquote>${escapeHTML(note.body)}</blockquote>`).join("") : "<p class='muted-copy'>No margin notes yet.</p>";
    const highlights = entry.highlights.length ? entry.highlights.map((highlight) => `<blockquote class='highlight'><p>“${escapeHTML(highlight.quote)}”</p>${highlight.note ? `<footer>${escapeHTML(highlight.note)}</footer>` : ""}</blockquote>`).join("") : "";
    const tasks = entry.tasks.length ? entry.tasks.map((task) => `<label class="task-row"><input type="checkbox" ${task.done ? "checked" : ""} data-task-id="${task.id}" /><span>${escapeHTML(task.title)}</span></label>`).join("") : "";
    $("#entry-detail").innerHTML = `<div class="entry-detail-head"><p class="entry-meta"><span>${escapeHTML(entry.origin)}</span><span>${escapeHTML(entry.source)}</span></p><h2 id="entry-dialog-title">${escapeHTML(entry.title)}</h2>${entry.url ? `<a class="source-url" href="${escapeHTML(entry.url)}" target="_blank" rel="noreferrer">Open original ↗</a>` : ""}<p>${escapeHTML(entry.summary || "Add why you saved this before the context fades.")}</p></div><div class="detail-actions"><button class="status-control ${entry.status === "kept" ? "is-active" : ""}" type="button" data-entry-status="kept">Keep</button><button class="status-control ${entry.status === "archived" ? "is-active" : ""}" type="button" data-entry-status="archived">Archive</button><button class="text-link" type="button" data-entry-draft="${entry.id}">Write from this ↗</button></div><section class="detail-section"><h3>Your margin</h3>${notes}${highlights}<form id="note-form"><label class="field"><span>Add a note</span><textarea name="body" required maxlength="50000" placeholder="What is the point worth keeping?"></textarea></label><button class="button button-secondary" type="submit">Add note</button></form></section><section class="detail-section"><h3>Next action</h3>${tasks}<form id="task-form" class="inline-form"><label class="sr-only" for="task-title">Task</label><input id="task-title" name="title" required maxlength="500" placeholder="Turn this into a next step" /><button class="button button-secondary" type="submit">Add task</button></form></section>`;
    openDialog("#entry-dialog");
  } catch (error) {
    showNotice(error.message, true);
  }
}

function renderSourcePicker(selected = []) {
  $("#draft-sources").innerHTML = state.entries.length
    ? state.entries.filter((entry) => entry.status !== "archived").map((entry) => `<label><input type="checkbox" value="${entry.id}" ${selected.includes(entry.id) ? "checked" : ""} /><span><strong>${escapeHTML(entry.title)}</strong><small>${escapeHTML(entry.source)}</small></span></label>`).join("")
    : "<p class='muted-copy'>Save a source first. It will be ready here when you start writing.</p>";
}

async function openDraft(draftId = null, sourceId = null) {
  let draft = null;
  try {
    if (draftId) draft = await request(`/api/reading/drafts/${draftId}`);
    $("#draft-id").value = draft?.id || "";
    $("#draft-title").value = draft?.title || "";
    $("#draft-body").value = draft?.body || "";
    renderSourcePicker(draft ? draft.sources.map((source) => source.id) : sourceId ? [sourceId] : []);
    $("#publish-draft").hidden = !draft || draft.status === "published";
    openDialog("#draft-dialog");
    $("#draft-title").focus();
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function saveCapture(event) {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  try {
    await request("/api/reading/entries", { method: "POST", body: JSON.stringify({ title: form.get("title"), url: form.get("url") || null, source: form.get("source") || "Saved link", summary: form.get("summary") || "", tags: String(form.get("tags") || "").split(",").map((tag) => tag.trim()).filter(Boolean), origin: "manual" }) });
    formElement.reset();
    $("#capture-source").value = "Saved link";
    closeDialog("#capture-dialog");
    await loadWorkspace();
    showNotice("Saved to your reading inbox.");
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function saveDraft(event) {
  event.preventDefault();
  const draftId = $("#draft-id").value;
  const entryIds = [...$("#draft-sources").querySelectorAll("input:checked")].map((input) => input.value);
  const body = { title: $("#draft-title").value, body: $("#draft-body").value, entry_ids: entryIds };
  try {
    await request(draftId ? `/api/reading/drafts/${draftId}` : "/api/reading/drafts", { method: draftId ? "PATCH" : "POST", body: JSON.stringify(body) });
    closeDialog("#draft-dialog");
    await loadWorkspace();
    showNotice("Draft saved. Its source cards stay attached.");
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function publishDraft() {
  const draftId = $("#draft-id").value;
  if (!draftId) return;
  try {
    const draft = await request(`/api/reading/drafts/${draftId}/publish`, { method: "POST" });
    $("#publish-draft").hidden = true;
    await loadWorkspace();
    showNotice(`Published privately controlled post: /read/${draft.slug}`);
    window.open(`/read/${encodeURIComponent(draft.slug)}`, "_blank", "noopener");
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function setTaskDone(taskId, done) {
  try {
    await request(`/api/reading/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify({ done }) });
    await loadWorkspace();
    if (state.activeEntry) await openEntry(state.activeEntry.id);
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function setEntryStatus(status) {
  if (!state.activeEntry) return;
  try {
    await request(`/api/reading/entries/${state.activeEntry.id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    await loadWorkspace();
    await openEntry(state.activeEntry.id);
    showNotice(status === "kept" ? "Kept for future you." : "Moved out of your active library.");
  } catch (error) {
    showNotice(error.message, true);
  }
}

$("#capture-button").addEventListener("click", () => openDialog("#capture-dialog"));
$("#hero-capture").addEventListener("click", () => openDialog("#capture-dialog"));
$("#capture-form").addEventListener("submit", saveCapture);
$("#new-draft").addEventListener("click", () => openDraft());
$("#draft-form").addEventListener("submit", saveDraft);
$("#publish-draft").addEventListener("click", publishDraft);
document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => closeDialog(`#${button.dataset.closeDialog}`)));
document.querySelectorAll("[data-scroll]").forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.scroll}`).scrollIntoView({ behavior: "smooth" })));
document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => { state.filter = button.dataset.status; document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("is-active", item === button)); renderEntries(); }));
document.body.addEventListener("click", (event) => {
  const target = event.target.closest("[data-open-entry], [data-open-draft], [data-action], [data-entry-status], [data-entry-draft]");
  if (!target) return;
  if (target.dataset.openEntry) openEntry(target.dataset.openEntry);
  if (target.dataset.openDraft) openDraft(target.dataset.openDraft);
  if (target.dataset.action === "capture") openDialog("#capture-dialog");
  if (target.dataset.action === "draft") openDraft();
  if (target.dataset.entryStatus) setEntryStatus(target.dataset.entryStatus);
  if (target.dataset.entryDraft) { closeDialog("#entry-dialog"); openDraft(null, target.dataset.entryDraft); }
});
document.body.addEventListener("change", (event) => { if (event.target.matches("input[data-task-id]")) setTaskDone(event.target.dataset.taskId, event.target.checked); });
$("#entry-dialog").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeEntry) return;
  const form = event.target;
  try {
    if (form.id === "note-form") await request(`/api/reading/entries/${state.activeEntry.id}/notes`, { method: "POST", body: JSON.stringify({ body: new FormData(form).get("body") }) });
    if (form.id === "task-form") await request("/api/reading/tasks", { method: "POST", body: JSON.stringify({ title: new FormData(form).get("title"), entry_id: state.activeEntry.id }) });
    await loadWorkspace();
    await openEntry(state.activeEntry.id);
  } catch (error) { showNotice(error.message, true); }
});

$("#date-line").textContent = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" }).format(new Date());
loadWorkspace();
