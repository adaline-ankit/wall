from datetime import UTC, datetime
from pathlib import Path

from wall_harness.models import Item, SourceSpec, Topic, WallSpec
from wall_harness.ranking import rank_items
from wall_harness.state import KnowledgeState


def spec() -> WallSpec:
    return WallSpec(
        name="test-wall",
        goal="learn AI systems",
        topics=[Topic(name="model architecture", weight=2, keywords=["sparse attention"])],
        exclude=["funding round"],
        sources=[SourceSpec(url="https://example.com/feed")],
    )


def test_relevant_novel_item_ranks_above_unrelated_item(tmp_path: Path) -> None:
    relevant = Item.create(
        title="Sparse attention model architecture",
        url="https://example.com/relevant",
        summary="A new sparse attention system",
        source="test",
        published_at=datetime.now(UTC),
    )
    unrelated = Item.create(
        title="Gardening notes",
        url="https://example.com/garden",
        summary="Tomatoes",
        source="test",
        published_at=datetime.now(UTC),
    )
    with KnowledgeState(tmp_path / "state.db") as state:
        ranked = rank_items([unrelated, relevant], spec(), state)
    assert ranked[0].item == relevant
    assert "matches model architecture" in ranked[0].reasons


def test_exclusion_is_fail_closed(tmp_path: Path) -> None:
    item = Item.create(
        title="Model company funding round",
        url="https://example.com/funding",
        summary="sparse attention",
        source="test",
    )
    with KnowledgeState(tmp_path / "state.db") as state:
        assert rank_items([item], spec(), state) == []


def test_seen_item_loses_novelty(tmp_path: Path) -> None:
    item = Item.create(
        title="Sparse attention architecture",
        url="https://example.com/item",
        summary="model architecture",
        source="test",
    )
    with KnowledgeState(tmp_path / "state.db") as state:
        first = rank_items([item], spec(), state)[0]
        state.remember("test-wall", [item])
        second = rank_items([item], spec(), state)[0]
    assert first.novelty == 1
    assert second.novelty == 0
    assert first.score > second.score


def test_hidden_item_is_removed_from_future_editions(tmp_path: Path) -> None:
    item = Item.create(
        title="Sparse attention architecture",
        url="https://example.com/hidden",
        summary="model architecture",
        source="test",
    )
    with KnowledgeState(tmp_path / "state.db") as state:
        state.record_feedback("test-wall", item, "hide")
        assert rank_items([item], spec(), state) == []


def test_positive_feedback_boosts_related_items(tmp_path: Path) -> None:
    previous = Item.create(
        title="Sparse attention kernels",
        url="https://example.com/previous",
        summary="Fast inference",
        source="test",
    )
    related = Item.create(
        title="Sparse attention serving",
        url="https://example.com/related",
        summary="Production inference",
        source="test",
    )
    baseline_item = Item.create(
        title="Model architecture overview",
        url="https://example.com/baseline",
        summary="General model architecture",
        source="test",
    )
    with KnowledgeState(tmp_path / "state.db") as state:
        state.remember("test-wall", [related, baseline_item])
        before = rank_items([related, baseline_item], spec(), state)
        before_related = next(result.score for result in before if result.item == related)
        state.record_feedback("test-wall", previous, "more_like_this")
        after = rank_items([related, baseline_item], spec(), state)
        after_related = next(result.score for result in after if result.item == related)
    assert after_related > before_related
    assert "matches your feedback" in next(
        result.reasons for result in after if result.item == related
    )
