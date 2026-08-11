from __future__ import annotations

from typing import Protocol

from wall_harness.models import Item, WallSpec


class Analyzer(Protocol):
    """LLM boundary. Providers receive selected content, never own discovery or ranking."""

    def analyze(self, item: Item, spec: WallSpec) -> str: ...


class Embedder(Protocol):
    """Optional vector boundary used only when semantic clustering is configured."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class NoopAnalyzer:
    def analyze(self, item: Item, spec: WallSpec) -> str:
        del item, spec
        return ""
