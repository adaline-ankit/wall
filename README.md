<div align="center">

# Wall

### RSS subscribes to sources. Wall subscribes to intent.

**A local-first, programmable information harness that continuously turns the web into your personal learning surface.**

[Quickstart](#quickstart) · [WallSpec](#the-wallspec) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md)

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

## What works today

- A versioned YAML **WallSpec** for goals, weighted topics, exclusions, sources, learning depth,
  ranking policy, providers, and delivery formats.
- RSS/Atom, Hacker News, GitHub search, OpenReview, and readable web-page discovery.
- URL deduplication plus content-aware clustering for differently worded coverage.
- Transparent ranking using topical match, recency, source weight, and personal novelty.
- Local SQLite concept memory so follow-up coverage is less novel than a genuinely new subject.
- Optional analysis through OpenAI, Anthropic, or local Ollama; **no LLM or API key is required**.
- Markdown, JSON, and a polished static HTML wall you can open anywhere.
- Source and analyzer protocols designed for plugins rather than a hard-coded crawler.

Wall is an early MVP. It does not yet crawl arbitrary pages, learn implicit preferences, deliver
email, or provide multi-user sync. Those are deliberate next layers, not hidden claims.

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
open .wall/output/index.html
```

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

llm:
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
```

The dashboard runs on `127.0.0.1:8765` by default. It can build editions, edit and validate the
WallSpec, filter the daily signal, and record `save`, `hide`, `already know`, or `more like this`
feedback. Feedback stays in the local SQLite knowledge database and changes future ranking.

Run Wall from cron, launchd, systemd, or GitHub Actions. The `delivery.schedule` field is
documentary in v0.1; Wall intentionally does not install background jobs on your machine.

## Philosophy

1. **Intent is the subscription.** Sources are replaceable evidence channels.
2. **Local first is a product property.** Specs, history, and rendered walls live on your machine.
3. **LLMs interpret; they do not secretly choose.** Selection has visible deterministic signals.
4. **Novelty is personal.** “Important” includes what advances *your* knowledge state.
5. **A quiet wall is healthy.** If nothing clears the threshold, Wall says so.
6. **Configuration should be forkable.** A good WallSpec is knowledge infrastructure others can share.

## Extending Wall

Implement the small `Source` protocol and expose it through the `wall.sources` Python entry-point
group, or implement the `Analyzer` protocol and pass it to the pipeline. See
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
