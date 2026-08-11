from __future__ import annotations

from importlib.metadata import entry_points

from .base import Source
from .json_sources import GitHubSource, HackerNewsSource, OpenReviewSource
from .rss import RSSSource
from .web import WebSource


def source_registry(*, include_plugins: bool = True) -> dict[str, Source]:
    sources: dict[str, Source] = {
        "rss": RSSSource(),
        "atom": RSSSource(),
        "web": WebSource(),
        "hackernews": HackerNewsSource(),
        "github": GitHubSource(),
        "openreview": OpenReviewSource(),
    }
    if include_plugins:
        for entry_point in entry_points(group="wall.sources"):
            try:
                loaded = entry_point.load()
                sources[entry_point.name] = loaded() if isinstance(loaded, type) else loaded
            except Exception:
                continue
    return sources
