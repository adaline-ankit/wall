<div align="center">

# Wall

### RSS subscribes to sources. Wall subscribes to intent.

**A local-first, programmable information harness that continuously turns the web into your personal learning surface.**

[Quickstart](#quickstart) · [Margin workspace](#margin-a-private-reading-to-writing-home) · [WallSpec](#the-wallspec) · [Architecture](docs/architecture.md) · [Hosting](docs/hosting.md) · [Contributing](CONTRIBUTING.md)

</div>

---

News feeds optimize for engagement. Search starts from scratch. Bookmarks become a graveyard.
Wall starts with a durable description of what you want to understand, then discovers, clusters,
ranks, explains, and remembers on your behalf.

```text
your intent (wall.yaml)
        ↓
pluggable discovery → deduplication → intent ranking → optional LLM analysis
        ↓                                      ↕
personal daily diff                    local knowledge state
```

## Margin: a private reading-to-writing home

`wall serve` now opens **Margin**, the personal workspace built on Wall's local-first storage.
It is deliberately not another feed reader: save what matters, add a margin note or contextual task,
write from connected source cards, and publish only the finished draft.

- One private inbox for manual saves, browser-save webhooks, forwarded-email webhooks, and Wall/RSS discoveries.
- **Refresh sources** runs the selected Wall from Margin and imports only its newly selected items; it
  uses local ranking by default and does not trigger delivery targets.
- Notes, highlights, tasks, and drafts connected to the reading item that created them.
- A weekly review that surfaces unfinished tasks and private drafts.
- Source-linked drafts and a separate public-post route that never includes private working notes.
- Downloadable Markdown export of the reading library and drafts.
- **Ask your library**: local source retrieval by default, or concise provider-assisted answers tied
  to matching source cards when you opt into an LLM.
- **Source-backed starters**: turn selected cards and your stated angle into an editable draft
  shape, preview it, and choose whether to insert it into the editor.
- Optional single-password protection for a private hosted service via `WALL_APP_PASSWORD`.
- A narrow optional `WALL_CAPTURE_TOKEN` for browser and inbound-email connectors. It can only add
  a captured item; it cannot read the private library, notes, tasks, drafts, or exports.

Run locally with `wall serve wall.yaml`, or use the documented [private Docker deployment](docs/hosting.md).
The browser and email capture routes are intentionally narrow HTTP contracts. For a hosted service,
give a browser extension or inbound-email gateway `WALL_CAPTURE_TOKEN`, not the Margin password.

## What works today

- A versioned YAML **WallSpec** for goals, weighted topics, exclusions, sources, learning depth,
  ranking policy, providers, and delivery formats.
- RSS/Atom, Hacker News, GitHub search, OpenReview, and readable web-page discovery.
- URL deduplication plus content-aware clustering, with opt-in Ollama/OpenAI embeddings for
  semantically equivalent coverage.
- Transparent ranking using topical match, recency, source weight, and personal novelty.
- Local SQLite concept memory so follow-up coverage is less novel than a genuinely new subject.
- Optional analysis through OpenAI, Anthropic, or local Ollama; **no LLM or API key is required**.
- Markdown, JSON, and a polished static HTML wall you can open anywhere.
- Opt-in webhook and SMTP email delivery with credentials read from environment variables.
- Authenticated encrypted export/import for moving specs and knowledge state between machines.
- Source, analyzer, and embedder protocols designed for extension rather than a hard-coded crawler.

Wall is local-first and single-user by default. It does not recursively crawl entire sites, infer
preferences without explicit reader feedback, or provide shared multi-user accounts. Those are
deliberate boundaries, not hidden claims.

## Quickstart

Requires Python 3.11+.

```bash
git clone https://github.com/adaline-ankit/wall.git
cd wall
python -m venv .venv
source .venv/bin/activate
pip install -e .

wall init wall.yaml
wall validate wall.yaml
wall run wall.yaml
wall serve wall.yaml
```

Open `http://127.0.0.1:8765` in any browser. `wall run` also writes a portable static edition to
`.wall/output/index.html` by default.

The bundled config uses deterministic local ranking and requires no credentials. Try the second
example with `wall init wall.yaml --example distributed-systems`.

### Add an LLM (optional)

Edit `wall.yaml`:

```yaml
llm:
  provider: ollama       # none | ollama | openai | anthropic
  model: llama3.2
  base_url: http://localhost:11434
```

For hosted providers, copy `.env.example`, export the relevant key, and choose `openai` or
`anthropic`. Wall only sends already-selected titles and source excerpts to the provider.

Margin uses this same opt-in setting for **Ask your library**. With `provider: none`, it stays
entirely local and returns the saved sources, notes, and highlights matching a question. With a
provider configured, Margin sends only that selected material—not the whole SQLite library—and
asks for a concise answer with source-number citations. The source cards remain visible either way;
AI does not publish or overwrite your notes or drafts. The Writing Studio also has an opt-in
source-backed starter: it is previewed before you insert it and labels private margin as working
material that must be rewritten or removed before publishing.

### Add semantic clustering (optional)

Lexical content clustering is deterministic and enabled by default. To group differently worded
coverage using local embeddings, add:

```yaml
embeddings:
  provider: ollama       # none | ollama | openai
  model: embeddinggemma
  similarity_threshold: 0.86
```

Embedding is a pre-ranking step, so the configured embedding provider receives every discovered
title and a bounded excerpt. Use `ollama` to keep that data local. The analyzer remains independent
and still receives only selected items.

## The WallSpec

```yaml
version: 1
name: frontier-ai
goal: Understand meaningful changes in frontier model architecture and agent systems.

topics:
  - name: model architecture
    weight: 2.0
    keywords: [mixture of experts, sparse attention, mamba, inference]
  - name: agent engineering
    weight: 1.5
    keywords: [tool use, evaluations, long horizon]

exclude: [funding round, beginner tutorial]

sources:
  - type: rss
    name: arXiv AI
    url: https://export.arxiv.org/rss/cs.AI
    tags: [research]

ranking:
  minimum_score: 0.28
  max_items: 12
  recency_half_life_hours: 72
  novelty_weight: 0.25

learning:
  depth: deep-dive
  assumed_knowledge: [transformers, attention]
  explain_terms: true

delivery:
  formats: [markdown, html, json]
  output_dir: .wall/output
  targets: [] # Optional webhook or email targets; see below.

llm:
  provider: none

embeddings:
  provider: none
```

See the complete [frontier AI](examples/frontier-ai.yaml) and
[distributed systems](examples/distributed-systems.yaml) walls.

## Commands

```text
wall init [PATH] [--example NAME]  Create an editable example
wall validate WALL.YAML            Validate without touching the network
wall run WALL.YAML [--no-llm]      Build one edition
wall run WALL.YAML --dry-run       Discover and rank without rendering
wall serve WALL.YAML               Open the interactive local dashboard
wall serve ./walls                 Open a workspace containing multiple WallSpecs
wall sync export ./walls backup.wall-sync
wall sync import backup.wall-sync ./restored
```

The dashboard runs on `127.0.0.1:8765` by default. Point it at one YAML file or a directory of
WallSpecs; the workspace switcher keeps each latest edition separate while sharing local knowledge.
It can build editions, edit and validate each WallSpec, filter the daily signal, and record `save`,
`hide`, `already know`, or `more like this` feedback. Feedback stays in the local SQLite knowledge
database and changes future ranking.

The dashboard has no user accounts because it is a local tool. Binding it to a network interface
therefore requires an explicit `--allow-network` acknowledgement. Set `WALL_APP_PASSWORD` for the
built-in private access boundary and put a TLS reverse proxy in front of it before sharing it. See
[hosting.md](docs/hosting.md) for the supported Docker deployment.

### Delivery targets

```yaml
delivery:
  formats: [markdown, html]
  output_dir: .wall/output
  targets:
    - type: webhook
      url: https://hooks.example.com/wall
    - type: email
      to: reader@example.com
      from_address: wall@example.com
      smtp_host: smtp.example.com
      username_env: WALL_SMTP_USER
      password_env: WALL_SMTP_PASSWORD
```

Delivery is disabled by default. Failures are recorded as receipts without discarding the locally
built edition. WallSpec contains environment-variable names, never SMTP credentials.

Optional analyzer or embedding outages are also recorded as processing warnings. Wall falls back
to the deterministic local edition instead of throwing away discovered and ranked results.

### Encrypted sync bundles

`wall sync export` bundles the workspace WallSpecs and a consistent SQLite knowledge snapshot. It
derives a key from `WALL_SYNC_PASSPHRASE` (or a hidden interactive prompt) with scrypt and encrypts
the bundle with AES-256-GCM authenticated encryption. `wall sync import` validates every path and
WallSpec before writing and refuses to replace existing Wall data unless you pass `--force`.

This is portable, provider-neutral sync: place the encrypted `.wall-sync` file in any transport you
trust. The passphrase and plaintext never leave the local command.

Run Wall from cron, launchd, systemd, or GitHub Actions. The `delivery.schedule` field is
documentary in v0.4; Wall intentionally does not install background jobs on your machine.

## Philosophy

1. **Intent is the subscription.** Sources are replaceable evidence channels.
2. **Local first is a product property.** Specs, history, and rendered walls live on your machine.
3. **LLMs interpret; they do not secretly choose.** Selection has visible deterministic signals.
4. **Novelty is personal.** “Important” includes what advances *your* knowledge state.
5. **A quiet wall is healthy.** If nothing clears the threshold, Wall says so.
6. **Configuration should be forkable.** A good WallSpec is knowledge infrastructure others can share.

## Extending Wall

Implement the small `Source` protocol and expose it through the `wall.sources` Python entry-point
group, or implement the `Analyzer`/`Embedder` protocols and pass them to the pipeline. See
[architecture.md](docs/architecture.md) for boundaries and a plugin example. Contributions for
additional primary-source systems, semantic retrieval, and delivery adapters are especially welcome.

## Development

```bash
pip install -e '.[dev]'
ruff check .
mypy wall_harness
pytest --cov=wall_harness
```

Wall is MIT licensed. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[roadmap](docs/roadmap.md) before proposing a large feature.
