from pathlib import Path

import pytest
from pydantic import ValidationError

from wall_harness.spec import load_spec


def test_loads_example_spec() -> None:
    spec = load_spec(Path("examples/frontier-ai.yaml"))
    assert spec.name == "frontier-ai"
    assert spec.learning.depth == "deep-dive"
    assert len(spec.sources) == 3


def test_rejects_unknown_delivery_format(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "name: x\ngoal: x\ntopics: [{name: x}]\nsources: [{url: https://example.com/feed}]\n"
        "delivery: {formats: [telepathy]}\n"
    )
    with pytest.raises(ValidationError):
        load_spec(path)
