from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from wall_harness.models import DeliveryTarget, Item
from wall_harness.spec import load_spec


def test_loads_example_spec() -> None:
    spec = load_spec(Path("examples/frontier-ai.yaml"))
    assert spec.name == "frontier-ai"
    assert spec.learning.depth == "deep-dive"
    assert len(spec.sources) == 6


@pytest.mark.parametrize("name", ["frontier-ai", "distributed-systems"])
def test_bundled_examples_match_repository_examples(name: str) -> None:
    assert (
        Path(f"wall_harness/examples/{name}.yaml").read_text()
        == Path(f"examples/{name}.yaml").read_text()
    )


def test_rejects_unknown_delivery_format(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "name: x\ngoal: x\ntopics: [{name: x}]\nsources: [{url: https://example.com/feed}]\n"
        "delivery: {formats: [telepathy]}\n"
    )
    with pytest.raises(ValidationError):
        load_spec(path)


def test_item_normalizes_naive_publish_time_to_utc() -> None:
    item = Item.create(
        title="A release",
        url="https://example.com/release",
        summary="Details",
        source="test",
        published_at=datetime(2026, 8, 11),
    )
    assert item.published_at.tzinfo == UTC


def test_item_normalizes_its_validated_url() -> None:
    item = Item.create(
        title="A release",
        url="https://EXAMPLE.com/report",
        summary="Details",
        source="test",
    )
    assert item.url == "https://example.com/report"


def test_email_target_rejects_header_injection() -> None:
    with pytest.raises(ValidationError):
        DeliveryTarget(
            type="email",
            to="reader@example.com\nBcc: attacker@example.com",
            from_address="wall@example.com",
            smtp_host="smtp.example.com",
        )


def test_rejects_unsupported_wallspec_version(tmp_path: Path) -> None:
    path = tmp_path / "future.yaml"
    path.write_text(
        "version: 99\nname: future\ngoal: test\ntopics: [{name: test}]\n"
        "sources: [{url: https://example.com/feed}]\n"
    )
    with pytest.raises(ValidationError):
        load_spec(path)


def test_rejects_unknown_model_provider(tmp_path: Path) -> None:
    path = tmp_path / "provider.yaml"
    path.write_text(
        "name: provider\ngoal: test\ntopics: [{name: test}]\n"
        "sources: [{url: https://example.com/feed}]\nllm: {provider: mystery}\n"
    )
    with pytest.raises(ValidationError):
        load_spec(path)
