# Architecture

Wall's core is a synchronous pipeline with narrow boundaries. That is intentional: the MVP is
easy to run, test, and embed. Async fetching and job orchestration can arrive without changing the
data contracts.

```text
WallSpec ──► source plugins ──► Item[] ──► cluster ──► deterministic rank
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
- `KnowledgeState` owns local seen/unseen memory. Its SQLite schema is private to that adapter.
- `WallEdition` is the stable output passed to Markdown, HTML, and JSON renderers.
- `web.app` exposes the same application contracts through a localhost-only FastAPI service. The
  dashboard never reimplements ranking or writes an invalid spec.

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

The next plugin milestone will add entry-point discovery so packages can self-register without
application code changes.

## Trust and privacy

Feed contents are untrusted input. The deterministic pipeline treats them as data. When an LLM is
enabled, only the selected item's title and excerpt are sent; source text cannot change tools or
configuration. Wall never uploads the SQLite knowledge database. Hosted providers still receive
selected content, so use `none` or `ollama` for fully local operation.
