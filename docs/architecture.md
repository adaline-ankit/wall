# Architecture

Wall's core is a synchronous pipeline with narrow boundaries. That is intentional: the MVP is
easy to run, test, and embed. Async fetching and job orchestration can arrive without changing the
data contracts.

```text
WallSpec ──► source plugins ──► Item[] ──► lexical/semantic cluster ──► deterministic rank
                                                              │
                                  KnowledgeState ◄─────────────┤
                                                              ▼
                                            optional Analyzer provider
                                                              │
                                                              ▼
                                               WallEdition ──► renderers
                                                              └──► local web API + dashboard
```

## Contracts

- `WallSpec` is the user-owned, versioned declaration. Pydantic validates it at the edge.
- `Source.fetch(SourceSpec) -> list[Item]` is the discovery plugin interface.
- `Analyzer.analyze(Item, WallSpec) -> str` is the LLM boundary.
- `Embedder.embed(list[str]) -> list[list[float]]` is an optional pre-ranking semantic-clustering
  boundary. It is disabled by default and independently configurable from analysis.
- `KnowledgeState` owns exact and concept-level novelty plus explicit feedback. Its SQLite schema is
  private to that adapter and migrates older local databases in place.
- `WallEdition` is the stable output passed to Markdown, HTML, and JSON renderers.
- `delivery` owns opt-in side effects. It returns per-target receipts so a webhook or SMTP outage
  never turns a successfully built local edition into an invisible failure.
- `web.app` exposes the same application contracts through a localhost-only FastAPI service. The
  dashboard never reimplements ranking or writes an invalid spec.
- `ReadingStore` is a separate local SQLite adapter for Margin's saved material, notes, highlights,
  contextual tasks, drafts, and source links. Its public-post renderer receives drafts and source
  cards only; it never receives reading notes.
- `LibraryAssistant` is a second optional LLM boundary for Margin. Local retrieval selects matching
  material first, then a configured provider may answer from that finite source set with required
  source-number citations or create an editable draft starter. Starters are previewed before they
  can enter the editor and are never saved or published automatically.
- `WallWorkspace` resolves either one YAML file or a directory of uniquely named WallSpecs. It
  rescans on each request so new local walls appear without restarting the process.
- `sync` exports a consistent SQLite backup and specs into a versioned, path-validated archive,
  then protects it with scrypt-derived AES-GCM authenticated encryption.

Discovery does not rank. Providers do not discover or decide what is eligible. Renderers do not
reach back into state. These boundaries keep hosted AI optional and make ranking inspectable.

## Adding a source

```python
from wall_harness.models import Item, SourceSpec


class MySource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        return [Item.create(title="...", url="...", summary="...", source="my-source")]


pipeline = WallPipeline(spec, sources={"my-source": MySource()})
```

External packages can self-register without application changes:

```toml
[project.entry-points."wall.sources"]
my-source = "my_package:MySource"
```

Installed plugins are discovered at pipeline startup. A broken external plugin is skipped without
breaking the built-in registry; an explicitly referenced missing source still appears as a source
failure in the edition.

## Trust and privacy

Feed contents are untrusted input. The deterministic pipeline treats them as data. When an analyzer
is enabled, only the selected item's title and excerpt are sent; source text cannot change tools or
configuration. When embeddings are enabled, discovered titles and bounded excerpts go to that
provider before ranking. Margin uses the same untrusted-data boundary for its library assistant:
only a query's locally selected source records, notes, and highlights are sent, never the whole
SQLite library. Wall never uploads the SQLite knowledge database. Use `none` or local `ollama`
providers for fully local operation.
