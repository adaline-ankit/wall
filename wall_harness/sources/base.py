from __future__ import annotations

from typing import Protocol

from wall_harness.models import Item, SourceSpec


class Source(Protocol):
    """A discovery plugin. Implement fetch and register it by source type."""

    def fetch(self, spec: SourceSpec) -> list[Item]: ...
