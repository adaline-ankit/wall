from __future__ import annotations

import calendar
from datetime import UTC, datetime

import feedparser
import httpx

from wall_harness.models import Item, SourceSpec

from .http import USER_AGENT


class RSSSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        response = httpx.get(
            str(spec.url),
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        feed = feedparser.parse(response.content)
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
