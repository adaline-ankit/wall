from pathlib import Path

from wall_harness.models import Item, SourceSpec, Topic, WallSpec
from wall_harness.pipeline import WallPipeline
from wall_harness.providers import NoopAnalyzer


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
