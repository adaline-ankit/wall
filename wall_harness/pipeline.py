from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from .cluster import cluster_items
from .delivery import deliver_edition
from .models import Item, SourceSpec, WallEdition, WallSpec
from .providers import Analyzer, Embedder, analyzer_from_spec, embedder_from_config
from .ranking import rank_items
from .renderers import render_html, render_markdown
from .sources import Source, source_registry
from .state import KnowledgeState

MAX_CONCURRENT_SOURCES = 8


class WallPipeline:
    def __init__(
        self,
        spec: WallSpec,
        *,
        state_path: Path = Path(".wall/state.db"),
        sources: dict[str, Source] | None = None,
        analyzer: Analyzer | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.spec = spec
        self.state_path = state_path
        self.sources = sources if sources is not None else source_registry()
        self.analyzer = analyzer
        self.embedder = embedder if embedder is not None else embedder_from_config(spec.embeddings)
        self.source_failures: list[str] = []

    def discover(self) -> list[Item]:
        items: list[Item] = []
        failures: list[str] = []
        fetches: list[tuple[SourceSpec, Source]] = []
        for source_spec in self.spec.sources:
            source = self.sources.get(source_spec.type)
            if source is None:
                failures.append(f"unknown source type {source_spec.type!r}")
                continue
            fetches.append((source_spec, source))

        # Source discovery is independent. Fetch in parallel so one slow external feed does not
        # make a reader wait through every other source timeout; consume results in spec order so
        # editions stay deterministic.
        with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_SOURCES, len(fetches) or 1)) as pool:
            futures = [pool.submit(source.fetch, source_spec) for source_spec, source in fetches]
            for (source_spec, _), future in zip(fetches, futures, strict=True):
                try:
                    items.extend(future.result())
                except Exception as exc:
                    failures.append(f"{source_label(source_spec)}: {failure_reason(exc)}")
        if not items and failures:
            raise RuntimeError("All sources failed: " + "; ".join(failures))
        self.source_failures = failures
        return items

    def run(self, *, use_llm: bool = True) -> WallEdition:
        discovered = self.discover()
        processing_warnings: list[str] = []
        try:
            clustered = cluster_items(
                discovered,
                embedder=self.embedder,
                semantic_threshold=self.spec.embeddings.similarity_threshold,
            )
        except Exception as exc:
            processing_warnings.append(f"semantic clustering unavailable: {failure_reason(exc)}")
            clustered = cluster_items(discovered)
        with KnowledgeState(self.state_path) as state:
            ranked = rank_items(clustered, self.spec, state)
            if use_llm and ranked:
                try:
                    analyzer = (
                        self.analyzer
                        if self.analyzer is not None
                        else analyzer_from_spec(self.spec)
                    )
                except Exception as exc:
                    processing_warnings.append(f"analysis unavailable: {failure_reason(exc)}")
                else:
                    for result in ranked:
                        try:
                            analysis = analyzer.analyze(result.item, self.spec)
                            result.analysis = analysis or None
                        except Exception as exc:
                            processing_warnings.append(
                                f"analysis unavailable for {result.item.id}: {failure_reason(exc)}"
                            )
            state.remember(self.spec.name, [result.item for result in ranked])
        return WallEdition(
            wall_name=self.spec.name,
            goal=self.spec.goal,
            generated_at=datetime.now(UTC),
            items=ranked,
            discovered_count=len(discovered),
            clustered_count=len(clustered),
            source_failures=self.source_failures,
            processing_warnings=processing_warnings,
        )

    def write(self, edition: WallEdition) -> list[Path]:
        output_dir = Path(self.spec.delivery.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = edition.generated_at.strftime("%Y-%m-%d")
        written: list[Path] = []
        for output_format in self.spec.delivery.formats:
            if output_format == "markdown":
                path, content = output_dir / f"{stamp}.md", render_markdown(edition)
            elif output_format == "html":
                path, content = output_dir / "index.html", render_html(edition)
            else:
                path = output_dir / f"{stamp}.json"
                content = json.dumps(edition.model_dump(mode="json"), indent=2)
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written

    def deliver(self, edition: WallEdition) -> None:
        edition.delivery_receipts = deliver_edition(edition, self.spec.delivery)


def source_label(source_spec: SourceSpec) -> str:
    if source_spec.name:
        return source_spec.name
    parsed = urlsplit(str(source_spec.url))
    hostname = parsed.hostname or "source"
    safe_host = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        safe_host = f"{safe_host}:{parsed.port}"
    return urlunsplit((parsed.scheme, safe_host, parsed.path, "", ""))


def failure_reason(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.RequestError):
        return "network error"
    return type(error).__name__
