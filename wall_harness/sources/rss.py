from __future__ import annotations

import calendar
from datetime import UTC, datetime

import feedparser

from wall_harness.models import Item, SourceSpec


class RSSSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        feed = feedparser.parse(str(spec.url))
        if getattr(feed, "bozo", False) and not feed.entries:
            raise RuntimeError(f"Could not read feed {spec.url}: {feed.bozo_exception}")
        source_name = spec.name or feed.feed.get("title") or str(spec.url)
        items: list[Item] = []
        for entry in feed.entries:
            title = entry.get("title", "Untitled")
            url = entry.get("link") or entry.get("id")
            if not url:
                continue
            struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
            published = (
                datetime.fromtimestamp(calendar.timegm(struct_time), tz=UTC)
                if struct_time
                else datetime.now(UTC)
            )
            items.append(
                Item.create(
                    title=title,
                    url=url,
                    summary=entry.get("summary", ""),
                    source=source_name,
                    published_at=published,
                    tags=spec.tags,
                )
            )
        return items
