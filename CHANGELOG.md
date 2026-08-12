# Changelog

## 0.6.0 — 2026-08-12

- Add `WALL_REFRESH_TOKEN`, a narrow scheduler credential that can refresh the selected Wall and
  import its new items without exposing the private workspace.
- Fail closed when the token is configured and prevent refresh-token callers from initiating LLM
  analysis, so an unattended schedule cannot create surprise provider spend.

## 0.5.0 — 2026-08-12

- Ship **Save to Margin**, a dependency-free Manifest V3 Chrome connector that saves the current
  page, an optional reason, and tags into the private inbox.
- Store the connector configuration only in local extension storage, require an explicit one-site
  permission, and accept HTTPS hosts (or loopback HTTP for local development) only.
- Keep the connector write-only: it uses `WALL_CAPTURE_TOKEN` for the browser capture route and
  never asks for or sends `WALL_APP_PASSWORD`.

## 0.4.0 — 2026-08-12

- Add `WALL_CAPTURE_TOKEN`: a scoped Bearer credential for browser extensions and inbound-email
  gateways that can only create captured inbox items.
- Keep the private Margin workspace behind `WALL_APP_PASSWORD`; a capture credential cannot list or
  read entries, notes, tasks, drafts, exports, or Wall configuration.
- Configure the scoped token automatically for Render Blueprints and document secure connector
  setup, rotation, and the owner Basic-auth fallback.

## 0.3.0 — 2026-08-12

- Add **Refresh sources** to Margin: build the selected Wall, retain the latest edition, and import
  only new selected items into the private reading inbox.
- Fetch independent sources concurrently with a bounded worker pool while preserving WallSpec order
  in the resulting edition, so slow sources do not serially delay the full refresh.
- Keep refresh local by default: provider analysis is opt-in and a reading refresh never triggers
  configured delivery targets.

## 0.2.0 — 2026-08-11

- Add an interactive, responsive local dashboard with live builds and validated WallSpec editing.
- Add explicit reading feedback and concept-level novelty learning.
- Add multi-wall workspaces with isolated latest editions.
- Add Hacker News, GitHub search, OpenReview, and readable web-page sources.
- Add automatic `wall.sources` entry-point plugin discovery.
- Add webhook and SMTP delivery receipts.
- Add authenticated encrypted workspace export/import.
- Add optional semantic clustering through local Ollama or OpenAI embeddings.
- Bound feed network requests and expose partial source failures.
- Add browser-facing security headers, safe network-binding acknowledgement, and dependency auditing.

## 0.1.0 — 2026-08-11

- Initial local-first CLI, WallSpec, RSS discovery, ranking, SQLite state, LLM provider abstraction,
  and Markdown/HTML/JSON rendering.
