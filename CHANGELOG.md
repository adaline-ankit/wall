# Changelog

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
