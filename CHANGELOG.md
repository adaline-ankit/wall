# Changelog

## 0.17.0 — 2026-08-12

- Add an optional per-source `min_request_interval_seconds` WallSpec setting. It spaces live
  requests to the same origin even while source discovery runs concurrently, and it also protects
  retry attempts. Cached responses remain immediate.

## 0.16.0 — 2026-08-12

- Add a local response cache for every built-in source. Each WallSpec source now has a
  `cache_ttl_minutes` setting (30 minutes by default; `0` disables caching), reducing repeated
  downloads during routine refreshes.
- Keep cache records local and bounded: successful response bodies of at most 5 MB are keyed by a
  SHA-256 URL digest, written atomically, and hosted Margin keeps them on its mounted data path.

## 0.15.0 — 2026-08-12

- Persist the latest health result for every configured source: success/failure, selected source
  type, item count, and a sanitized failure class. Source identities are hashed locally; query
  strings and credentials are not written to the health record.
- Add an owner-only source-health API and Margin status line. A refresh now says whether all
  sources responded or identifies the evidence channel that needs attention.

## 0.14.0 — 2026-08-12

- Retry temporary source fetch failures consistently across RSS/Atom, JSON APIs, and web pages.
  Wall makes at most three GET attempts for transport failures, 408/429, and selected 5xx errors;
  it fails permanent client errors immediately.
- Respect numeric or date-based `Retry-After` responses while bounding each wait to 30 seconds,
  so a source can ask Wall to slow down without stalling a whole scheduled run indefinitely.

## 0.13.0 — 2026-08-12

- Add **Today's Wall** to Margin: the latest local Wall edition now appears as a compact daily
  brief with its selected items, relevance reason, analysis, and original sources.
- Reuse the existing owner-only edition data and scheduled/manual refresh flow; viewing the brief
  never invokes an LLM or sends new data to a provider.

## 0.12.0 — 2026-08-12

- Surface Margin's existing read state: filter finished material, mark an entry as read, and keep
  finished reading out of the active focus queue without removing it from the writing source set.
- Expose the selected reading state with visible labels and pressed-state semantics.

## 0.11.1 — 2026-08-12

- Repair repository formatting so the dashboard release passes the enforced CI quality gate.

## 0.11.0 — 2026-08-12

- Show the last scheduled refresh, its completion state, selected items, and new inbox additions in
  the private Margin dashboard.
- Keep this operational view owner-only; the narrow scheduler token may still read only the status
  of a job whose ID it already holds.
- Correct the writing-studio empty-state contrast so it meets the same accessible visual baseline.

## 0.10.0 — 2026-08-12

- Cache lexical representations during duplicate clustering, avoiding repeated tokenization for every
  pair of discovered items and making large real-world Wall refreshes practical for daily use.

## 0.9.1 — 2026-08-12

- Ensure accepted asynchronous refreshes carry their background task into the live response, so
  queued job records reliably execute outside the request lifecycle.

## 0.9.0 — 2026-08-12

- Add durable asynchronous refresh jobs so schedulers can submit a Wall build immediately and poll
  completion without holding an HTTP connection through all source fetches.
- Limit refresh-token callers to submitting and reading only refresh-job status; they still cannot
  list the inbox, read notes, or invoke LLM providers.

## 0.8.0 — 2026-08-12

- Add a fail-closed Telegram Bot webhook adapter for capturing links and message context into the
  private Margin inbox.
- Require a separate Telegram webhook secret, support an optional allowed-chat boundary, and keep
  Telegram unable to read the library or use the dashboard credential.

## 0.7.2 — 2026-08-12

- Bound the hosted scheduler's total retry window so a failing daily refresh reports clearly rather
  than consuming the entire job timeout.

## 0.7.1 — 2026-08-12

- Replace an invalid GitHub Actions secret condition with a successful, explicit configuration gate.

## 0.7.0 — 2026-08-12

- Add an opt-in GitHub Actions daily refresh workflow for hosted Margin instances.
- Keep the job inert until its scoped URL variable and refresh-token secret are configured; it uses
  retries for free-tier cold starts and never receives the Margin password.

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
