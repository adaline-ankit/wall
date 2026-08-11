from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .cluster import cluster_items
from .delivery import deliver_edition
from .models import Item, WallEdition, WallSpec
from .providers import Analyzer, analyzer_from_spec
from .ranking import rank_items
from .renderers import render_html, render_markdown
from .sources import Source, source_registry
from .state import KnowledgeState


class WallPipeline:
    def __init__(
        self,
        spec: WallSpec,
        *,
        state_path: Path = Path(".wall/state.db"),
        sources: dict[str, Source] | None = None,
        analyzer: Analyzer | None = None,
    ) -> None:
        self.spec = spec
        self.state_path = state_path
        self.sources = sources or source_registry()
        self.analyzer = analyzer or analyzer_from_spec(spec)
        self.source_failures: list[str] = []

    def discover(self) -> list[Item]:
        items: list[Item] = []
        failures: list[str] = []
        for source_spec in self.spec.sources:
            source = self.sources.get(source_spec.type)
            if source is None:
                failures.append(f"unknown source type {source_spec.type!r}")
                continue
            try:
                items.extend(source.fetch(source_spec))
            except Exception as exc:
                failures.append(f"{source_spec.name or source_spec.url}: {exc}")
        if not items and failures:
            raise RuntimeError("All sources failed: " + "; ".join(failures))
        self.source_failures = failures
        return items

    def run(self, *, use_llm: bool = True) -> WallEdition:
        discovered = self.discover()
        clustered = cluster_items(discovered)
        with KnowledgeState(self.state_path) as state:
            ranked = rank_items(clustered, self.spec, state)
            if use_llm:
                for result in ranked:
                    analysis = self.analyzer.analyze(result.item, self.spec)
                    result.analysis = analysis or None
            state.remember(self.spec.name, [result.item for result in ranked])
        return WallEdition(
            wall_name=self.spec.name,
            goal=self.spec.goal,
            generated_at=datetime.now(UTC),
            items=ranked,
            discovered_count=len(discovered),
            clustered_count=len(clustered),
            source_failures=self.source_failures,
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
