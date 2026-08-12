const capturePath = "/api/reading/captures/browser";
const savedConnectionKeys = ["endpoint", "token"];

const elements = {
  capture: document.querySelector("#capture"),
  captureButton: document.querySelector("#capture-page"),
  editConnection: document.querySelector("#edit-connection"),
  endpoint: document.querySelector("#endpoint"),
  note: document.querySelector("#note"),
  pageTitle: document.querySelector("#page-title"),
  pageUrl: document.querySelector("#page-url"),
  saveConnection: document.querySelector("#save-connection"),
  setup: document.querySelector("#setup"),
  status: document.querySelector("#status"),
  tags: document.querySelector("#tags"),
  token: document.querySelector("#token")
};

let page;

function showStatus(message, kind = "") {
  elements.status.textContent = message;
  elements.status.className = `status ${kind}`;
}

function normalizedEndpoint(value) {
  const url = new URL(value.trim());
  const localHttp = url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname);
  if (url.protocol !== "https:" && !localHttp) {
    throw new Error("Use HTTPS, except for local Margin at localhost or 127.0.0.1.");
  }
  if (
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("Use only your Margin site address, without credentials or a path query.");
  }
  return url.origin;
}

function permissionFor(endpoint) {
  const url = new URL(endpoint);
  return `${url.protocol}//${url.hostname}/*`;
}

async function activePage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url || !tab?.title || !/^https?:/.test(tab.url)) {
    throw new Error("Open a normal web page before saving to Margin.");
  }
  return { title: tab.title, url: tab.url };
}

function displayCapture(connection) {
  elements.setup.hidden = true;
  elements.capture.hidden = false;
  elements.endpoint.value = connection.endpoint;
  elements.token.value = connection.token;
  elements.pageTitle.textContent = page?.title || "No page selected";
  elements.pageUrl.textContent = page?.url || "";
}

async function load() {
  const connection = await chrome.storage.local.get(savedConnectionKeys);
  try {
    page = await activePage();
  } catch (error) {
    showStatus(error.message, "error");
  }
  if (connection.endpoint && connection.token) {
    displayCapture(connection);
  }
}

async function saveConnection() {
  try {
    const endpoint = normalizedEndpoint(elements.endpoint.value);
    const token = elements.token.value.trim();
    if (!token) {
      throw new Error("Enter the capture token from your Margin service.");
    }
    const permissionGranted = await chrome.permissions.request({
      origins: [permissionFor(endpoint)]
    });
    if (!permissionGranted) {
      throw new Error("Margin permission is required to save pages.");
    }
    await chrome.storage.local.set({ endpoint, token });
    displayCapture({ endpoint, token });
    showStatus("Connection saved on this browser.", "success");
  } catch (error) {
    showStatus(error.message, "error");
  }
}

async function capturePage() {
  if (!page) {
    showStatus("Open a normal web page before saving to Margin.", "error");
    return;
  }
  const connection = await chrome.storage.local.get(savedConnectionKeys);
  if (!connection.endpoint || !connection.token) {
    elements.setup.hidden = false;
    elements.capture.hidden = true;
    showStatus("Add a Margin connection first.", "error");
    return;
  }
  elements.captureButton.disabled = true;
  showStatus("Saving to your inbox…");
  try {
    const response = await fetch(`${connection.endpoint}${capturePath}`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${connection.token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        title: page.title,
        url: page.url,
        source: "Browser",
        summary: elements.note.value.trim(),
        tags: elements.tags.value.split(",").map((tag) => tag.trim()).filter(Boolean)
      })
    });
    if (response.status === 401) {
      throw new Error("Margin rejected the capture token. Check it and save the connection again.");
    }
    if (!response.ok) {
      throw new Error(`Margin could not save this page (${response.status}).`);
    }
    elements.note.value = "";
    elements.tags.value = "";
    showStatus("Saved to your Margin inbox.", "success");
  } catch (error) {
    showStatus(error.message || "Could not reach Margin.", "error");
  } finally {
    elements.captureButton.disabled = false;
  }
}

elements.saveConnection.addEventListener("click", saveConnection);
elements.captureButton.addEventListener("click", capturePage);
elements.editConnection.addEventListener("click", () => {
  elements.setup.hidden = false;
  elements.capture.hidden = true;
  elements.endpoint.focus();
});

void load();
