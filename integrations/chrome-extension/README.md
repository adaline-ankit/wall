# Save to Margin (Chrome)

Save the page in your current tab into a private Margin inbox. This is an unpacked Manifest V3
extension for personal use while the connector matures; it is intentionally dependency-free.

## Install

1. In Chrome, open `chrome://extensions` and turn on **Developer mode**.
2. Choose **Load unpacked** and select this `integrations/chrome-extension` folder.
3. Pin **Save to Margin**, then open its toolbar button on a normal web page.
4. Enter your Margin address (for example, `https://margin.example.com`) and its
   `WALL_CAPTURE_TOKEN`.
5. Approve the one-site permission prompt. The extension can now save the current page.

The token is stored in Chrome's local extension storage, not in this repository. The extension only
calls `POST /api/reading/captures/browser`. It cannot use the token to read your inbox, notes,
tasks, drafts, exports, or private dashboard.

## Get the token

For a local Docker install, set `WALL_CAPTURE_TOKEN` in `.env` before starting Margin. For the
Render Blueprint, a token is generated in the service environment; retrieve it from the Render
environment page and paste it here. Never use or paste `WALL_APP_PASSWORD` into this extension.

Use HTTPS for a hosted Margin. The connector permits `http://localhost` and `http://127.0.0.1`
only for a local development service. Change the capture token in the service environment if this
browser profile or device is no longer trusted.

## What it sends

When you press **Save this page**, the extension sends the current tab's title and URL, plus the
optional note and tags you enter. It does not scrape the page, inject a content script, read
cookies, or request access to every page you visit.
