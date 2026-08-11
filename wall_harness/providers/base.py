from __future__ import annotations

from typing import Protocol

from wall_harness.models import Item, WallSpec


class Analyzer(Protocol):
    """LLM boundary. Providers receive selected content, never own discovery or ranking."""

    def analyze(self, item: Item, spec: WallSpec) -> str: ...


class NoopAnalyzer:
    def analyze(self, item: Item, spec: WallSpec) -> str:
        del item, spec
        return ""
