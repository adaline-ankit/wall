from pathlib import Path
from threading import Barrier

from wall_harness.models import Item, SourceSpec, Topic, WallSpec
from wall_harness.pipeline import WallPipeline
from wall_harness.providers import NoopAnalyzer
from wall_harness.state import KnowledgeState


class FakeSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        return [
            Item.create(
                title="A new consensus algorithm",
                url="https://example.com/consensus",
                summary="Distributed consensus and replication",
                source=spec.name or "fake",
            )
        ]


def test_pipeline_runs_and_writes_all_formats(tmp_path: Path) -> None:
    spec = WallSpec(
        name="systems",
        goal="learn distributed systems",
        topics=[Topic(name="consensus", keywords=["distributed", "replication"])],
        sources=[SourceSpec(type="fake", name="fixture", url="https://example.com/feed")],
        delivery={"formats": ["markdown", "html", "json"], "output_dir": str(tmp_path / "out")},
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"fake": FakeSource()},
        analyzer=NoopAnalyzer(),
    )
    edition = pipeline.run()
    paths = pipeline.write(edition)
    assert len(edition.items) == 1
    assert {path.suffix for path in paths} == {".md", ".html", ".json"}
    assert "A new consensus algorithm" in (tmp_path / "out" / "index.html").read_text()


def test_partial_source_failure_does_not_erase_success(tmp_path: Path) -> None:
    class Broken:
        def fetch(self, spec: SourceSpec) -> list[Item]:
            raise RuntimeError("offline")

    spec = WallSpec(
        name="systems",
        goal="learn systems",
        topics=[Topic(name="consensus")],
        sources=[
            SourceSpec(type="fake", url="https://example.com/ok"),
            SourceSpec(type="broken", url="https://example.com/broken"),
        ],
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"fake": FakeSource(), "broken": Broken()},
        analyzer=NoopAnalyzer(),
    )
    assert len(pipeline.discover()) == 1


def test_pipeline_fetches_independent_sources_concurrently(tmp_path: Path) -> None:
    barrier = Barrier(2)

    class BarrierSource:
        def fetch(self, spec: SourceSpec) -> list[Item]:
            barrier.wait(timeout=0.25)
            return FakeSource().fetch(spec)

    spec = WallSpec(
        name="systems",
        goal="learn systems",
        topics=[Topic(name="consensus")],
        sources=[
            SourceSpec(type="barrier", url="https://example.com/one"),
            SourceSpec(type="barrier", url="https://example.com/two"),
        ],
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"barrier": BarrierSource()},
        analyzer=NoopAnalyzer(),
    )

    assert len(pipeline.discover()) == 2


def test_pipeline_reports_source_failures_without_losing_results(tmp_path: Path) -> None:
    class Broken:
        def fetch(self, spec: SourceSpec) -> list[Item]:
            raise RuntimeError("offline")

    spec = WallSpec(
        name="systems",
        goal="learn systems",
        topics=[Topic(name="consensus")],
        sources=[
            SourceSpec(type="fake", url="https://example.com/ok"),
            SourceSpec(type="broken", url="https://example.com/broken"),
        ],
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"fake": FakeSource(), "broken": Broken()},
        analyzer=NoopAnalyzer(),
    )
    edition = pipeline.run()
    assert edition.source_failures == ["https://example.com/broken: RuntimeError"]
    with KnowledgeState(tmp_path / "state.db") as state:
        assert state.source_health("systems") == [
            {
                "source_label": "https://example.com/broken",
                "source_type": "broken",
                "status": "failed",
                "item_count": 0,
                "detail": "RuntimeError",
            },
            {
                "source_label": "https://example.com/ok",
                "source_type": "fake",
                "status": "ok",
                "item_count": 1,
                "detail": None,
            },
        ]


def test_source_failure_redacts_url_credentials(tmp_path: Path) -> None:
    class Broken:
        def fetch(self, spec: SourceSpec) -> list[Item]:
            raise RuntimeError("offline")

    spec = WallSpec(
        name="systems",
        goal="learn systems",
        topics=[Topic(name="consensus")],
        sources=[
            SourceSpec(type="fake", url="https://example.com/ok"),
            SourceSpec(
                type="broken",
                url="https://reader:secret@example.com/broken?token=private",
            ),
        ],
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"fake": FakeSource(), "broken": Broken()},
        analyzer=NoopAnalyzer(),
    )

    edition = pipeline.run()

    assert edition.source_failures == ["https://example.com/broken: RuntimeError"]


def test_no_llm_does_not_require_a_configured_provider_key(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = WallSpec(
        name="systems",
        goal="learn systems",
        topics=[Topic(name="consensus")],
        sources=[SourceSpec(type="fake", url="https://example.com/ok")],
        llm={"provider": "openai", "model": "gpt-test"},
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"fake": FakeSource()},
    )

    edition = pipeline.run(use_llm=False)

    assert len(edition.items) == 1


def test_analyzer_failure_preserves_the_local_edition(tmp_path: Path) -> None:
    class BrokenAnalyzer:
        def analyze(self, item: Item, spec: WallSpec) -> str:
            raise RuntimeError("provider secret must not leak")

    spec = WallSpec(
        name="systems",
        goal="learn systems",
        topics=[Topic(name="consensus")],
        sources=[SourceSpec(type="fake", url="https://example.com/ok")],
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"fake": FakeSource()},
        analyzer=BrokenAnalyzer(),
    )

    edition = pipeline.run()

    assert len(edition.items) == 1
    assert edition.items[0].analysis is None
    assert edition.processing_warnings == [
        f"analysis unavailable for {edition.items[0].item.id}: RuntimeError"
    ]


def test_embedding_failure_falls_back_to_lexical_clustering(tmp_path: Path) -> None:
    class BrokenEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("local model unavailable")

    class TwoItemSource:
        def fetch(self, spec: SourceSpec) -> list[Item]:
            return [
                *FakeSource().fetch(spec),
                Item.create(
                    title="Consensus replication update",
                    url="https://example.com/second",
                    summary="Another consensus result",
                    source="fake",
                ),
            ]

    spec = WallSpec(
        name="systems",
        goal="learn systems",
        topics=[Topic(name="consensus")],
        sources=[SourceSpec(type="fake", url="https://example.com/ok")],
    )
    pipeline = WallPipeline(
        spec,
        state_path=tmp_path / "state.db",
        sources={"fake": TwoItemSource()},
        analyzer=NoopAnalyzer(),
        embedder=BrokenEmbedder(),
    )

    edition = pipeline.run()

    assert len(edition.items) == 2
    assert edition.processing_warnings == ["semantic clustering unavailable: RuntimeError"]
