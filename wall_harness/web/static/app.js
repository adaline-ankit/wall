const state = { walls: [], activeWall: null, spec: null, edition: null, feedback: new Map(), filter: "all" };

const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => {
  const node = document.createElement("span");
  node.textContent = String(value ?? "");
  return node.innerHTML;
};
const excerpt = (value, limit = 640) => {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit).replace(/\s+\S*$/, "")}…` : text;
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((entry) => entry.msg || String(entry)).join("; ")
      : payload.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return null;
  return response.json();
}

function showNotice(message, isError = false) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("is-error", isError);
}

function renderSpec() {
  const spec = state.spec;
  $("#wall-name").textContent = spec.name;
  $("#wall-goal").textContent = spec.goal;
  $("#topic-count").textContent = spec.topics.length;
  $("#source-count").textContent = spec.sources.length;
  $("#learning-depth").textContent = spec.learning.depth.replace("-", " ");
  $("#topic-list").innerHTML = spec.topics
    .map((topic) => `<div class="topic"><strong>${escapeHTML(topic.name)}</strong><span>×${topic.weight.toFixed(1)}</span></div>`)
    .join("");
  $("#source-list").innerHTML = spec.sources
    .map((source, index) => `<div class="source-row"><span>${String(index + 1).padStart(2, "0")}</span><b>${escapeHTML(source.name || new URL(source.url).hostname)}</b><span>${escapeHTML(source.type)}</span></div>`)
    .join("");
}

function wallQuery() {
  return state.activeWall ? `?wall=${encodeURIComponent(state.activeWall)}` : "";
}

function renderWallPicker() {
  const picker = $("#wall-picker");
  picker.hidden = state.walls.length < 2;
  const options = state.walls.map((wall) => new Option(wall.name, wall.name, false, wall.name === state.activeWall));
  $("#wall-switch").replaceChildren(...options);
}

function storyMarkup(result) {
  const item = result.item;
  const feedback = state.feedback.get(item.id);
  const actions = [
    ["save", "Save"],
    ["more_like_this", "More like this"],
    ["known", "Already know"],
    ["hide", "Hide"],
  ];
  return `<article class="story" data-id="${escapeHTML(item.id)}" data-novelty="${result.novelty}" data-saved="${feedback === "save"}">
    <div class="story-score">${Math.round(result.score * 100)}<small>intent score</small></div>
    <div>
      <p class="meta">${escapeHTML(item.source)} · ${new Date(item.published_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</p>
      <h3><a href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(item.title)}</a></h3>
      <p class="story-copy">${escapeHTML(excerpt(result.analysis || item.summary || "No source summary available."))}</p>
      <p class="why">Why here — ${escapeHTML(result.reasons.join(" · "))}</p>
    </div>
    <div class="story-actions" aria-label="Tune this result">
      ${actions.map(([action, label]) => `<button class="feedback ${feedback === action ? "is-selected" : ""}" type="button" data-action="${action}">${label}</button>`).join("")}
    </div>
  </article>`;
}

function renderEdition() {
  const edition = state.edition;
  if (!edition) return;
  $("#edition-date").textContent = new Date(edition.generated_at).toLocaleString(undefined, {
    weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit",
  });
  const items = edition.items.filter((result) => {
    if (state.filter === "new") return result.novelty > 0;
    if (state.filter === "saved") return state.feedback.get(result.item.id) === "save";
    return state.feedback.get(result.item.id) !== "hide";
  });
  if (!items.length) {
    $("#edition-content").innerHTML = `<div class="empty-state"><p class="empty-mark">⌁</p><h3>No signal in this view.</h3><p>Try another filter or tune your intent.</p></div>`;
    return;
  }
  $("#edition-content").innerHTML = items.map(storyMarkup).join("");
}

async function buildWall() {
  const button = $("#run-wall");
  button.disabled = true;
  button.querySelector("span").textContent = "Discovering signal…";
  showNotice("Reading sources, clustering coverage, and checking what is new to you.");
  try {
    state.edition = await request("/api/run", { method: "POST", body: JSON.stringify({ use_llm: true, wall: state.activeWall }) });
    renderEdition();
    const sourceWarnings = state.edition.source_failures.length;
    const processingWarnings = state.edition.processing_warnings.length;
    const warnings = sourceWarnings + processingWarnings;
    showNotice(`Built ${state.edition.items.length} items from ${state.edition.discovered_count} discoveries${warnings ? ` · ${warnings} warning${warnings > 1 ? "s" : ""}` : ""}.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Build today’s wall";
  }
}

async function sendFeedback(button) {
  const story = button.closest(".story");
  const result = state.edition.items.find((entry) => entry.item.id === story.dataset.id);
  const action = button.dataset.action;
  try {
    await request("/api/feedback", { method: "POST", body: JSON.stringify({ item: result.item, action, wall: state.activeWall }) });
    state.feedback.set(result.item.id, action);
    renderEdition();
    showNotice(action === "hide" ? "Hidden. Future editions will leave this out." : "Preference saved for future editions.");
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function openEditor() {
  const spec = await request(`/api/spec${wallQuery()}`);
  const yaml = await request(`/api/spec/source${wallQuery()}`).catch(() => null);
  $("#spec-editor").value = yaml?.content || JSON.stringify(spec, null, 2);
  $("#editor-error").textContent = "";
  $("#spec-dialog").showModal();
  $("#spec-editor").focus();
}

async function saveEditor() {
  try {
    state.spec = await request(`/api/spec${wallQuery()}`, { method: "PUT", body: JSON.stringify({ yaml: $("#spec-editor").value }) });
    state.activeWall = state.spec.name;
    state.walls = await request("/api/walls");
    state.feedback = new Map(Object.entries(await request(`/api/feedback${wallQuery()}`)));
    renderWallPicker();
    renderSpec();
    $("#spec-dialog").close();
    showNotice("WallSpec saved. Build again to apply the new intent.");
  } catch (error) {
    $("#editor-error").textContent = error.message;
  }
}

async function loadWall(name) {
  state.activeWall = name;
  state.spec = await request(`/api/spec${wallQuery()}`);
  state.feedback = new Map(Object.entries(await request(`/api/feedback${wallQuery()}`)));
  renderSpec();
  renderWallPicker();
  state.edition = await request(`/api/edition${wallQuery()}`);
  if (state.edition) renderEdition();
  else {
    $("#edition-date").textContent = "Not built yet";
    $("#edition-content").innerHTML = `<div class="empty-state"><p class="empty-mark">⌁</p><h3>Nothing noisy. Nothing generic.</h3><p>Build your first edition and Wall will surface only what clears your intent threshold.</p></div>`;
  }
}

async function start() {
  try {
    state.walls = await request("/api/walls");
    await loadWall(state.walls[0].name);
  } catch (error) {
    showNotice(error.message, true);
  }
}

$("#run-wall").addEventListener("click", buildWall);
$("#edition-content").addEventListener("click", (event) => {
  const button = event.target.closest(".feedback");
  if (button) sendFeedback(button);
});
document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".filter").forEach((candidate) => candidate.classList.remove("is-active"));
  button.classList.add("is-active");
  state.filter = button.dataset.filter;
  renderEdition();
}));
$("#edit-intent").addEventListener("click", openEditor);
$("#save-spec").addEventListener("click", saveEditor);
$("#wall-switch").addEventListener("change", (event) => loadWall(event.target.value).catch((error) => showNotice(error.message, true)));
$(".theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "" : "dark";
  document.documentElement.dataset.theme = next;
});

start();
