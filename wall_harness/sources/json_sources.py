from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from wall_harness.models import Item, SourceSpec

from .http import get_json


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class HackerNewsSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        payload = get_json(
            str(spec.url),
            cache_ttl_minutes=spec.cache_ttl_minutes,
            min_request_interval_seconds=spec.min_request_interval_seconds,
        )
        items: list[Item] = []
        for hit in payload.get("hits", []):
            url = hit.get("url") or hit.get("story_url")
            title = hit.get("title") or hit.get("story_title")
            if not url or not title:
                continue
            items.append(
                Item.create(
                    title=str(title),
                    url=str(url),
                    summary=str(hit.get("story_text") or hit.get("comment_text") or ""),
                    source=spec.name or "Hacker News",
                    published_at=parse_time(hit.get("created_at")),
                    tags=spec.tags,
                )
            )
        return items


class GitHubSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        payload = get_json(
            str(spec.url),
            github=True,
            cache_ttl_minutes=spec.cache_ttl_minutes,
            min_request_interval_seconds=spec.min_request_interval_seconds,
        )
        items: list[Item] = []
        for result in payload.get("items", []):
            url = result.get("html_url")
            title = result.get("full_name") or result.get("title") or result.get("name")
            if not url or not title:
                continue
            items.append(
                Item.create(
                    title=str(title),
                    url=str(url),
                    summary=str(result.get("description") or result.get("body") or ""),
                    source=spec.name or "GitHub",
                    published_at=parse_time(result.get("updated_at") or result.get("created_at")),
                    tags=[str(tag) for tag in result.get("topics", [])] or spec.tags,
                )
            )
        return items


def content_value(content: dict[str, Any], key: str, default: Any = "") -> Any:
    value = content.get(key, default)
    return value.get("value", default) if isinstance(value, dict) else value


class OpenReviewSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        payload = get_json(
            str(spec.url),
            cache_ttl_minutes=spec.cache_ttl_minutes,
            min_request_interval_seconds=spec.min_request_interval_seconds,
        )
        items: list[Item] = []
        for note in payload.get("notes", []):
            note_id = note.get("id")
            content = note.get("content", {})
            title = content_value(content, "title")
            if not note_id or not title:
                continue
            created = note.get("cdate") or note.get("tcdate")
            published = (
                datetime.fromtimestamp(float(created) / 1000, tz=UTC)
                if created
                else datetime.now(UTC)
            )
            keywords = content_value(content, "keywords", [])
            items.append(
                Item.create(
                    title=str(title),
                    url=f"https://openreview.net/forum?id={note_id}",
                    summary=str(content_value(content, "abstract")),
                    source=spec.name or "OpenReview",
                    published_at=published,
                    tags=[str(keyword) for keyword in keywords]
                    if isinstance(keywords, list)
                    else spec.tags,
                )
            )
        return items
