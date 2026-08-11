from datetime import UTC, datetime

import httpx

from wall_harness.models import SourceSpec
from wall_harness.sources.registry import source_registry


def response(payload) -> httpx.Response:  # type: ignore[no-untyped-def]
    return httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", "https://example.com/api"),
    )


def test_hacker_news_source_maps_search_hits(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "wall_harness.sources.http.httpx.get",
        lambda *args, **kwargs: response(
            {
                "hits": [
                    {
                        "objectID": "42",
                        "title": "A new database",
                        "url": "https://example.com/database",
                        "story_text": "Architecture notes",
                        "created_at": "2026-08-10T12:30:00Z",
                    }
                ]
            }
        ),
    )
    source = source_registry()["hackernews"]
    items = source.fetch(
        SourceSpec(name="HN", type="hackernews", url="https://hn.algolia.com/api/v1/search")
    )
    assert items[0].title == "A new database"
    assert items[0].published_at == datetime(2026, 8, 10, 12, 30, tzinfo=UTC)


def test_github_source_maps_repositories(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "wall_harness.sources.http.httpx.get",
        lambda *args, **kwargs: response(
            {
                "items": [
                    {
                        "id": 7,
                        "full_name": "acme/engine",
                        "html_url": "https://github.com/acme/engine",
                        "description": "A fast inference engine",
                        "updated_at": "2026-08-09T08:00:00Z",
                        "topics": ["inference"],
                    }
                ]
            }
        ),
    )
    item = source_registry()["github"].fetch(
        SourceSpec(type="github", url="https://api.github.com/search/repositories?q=inference")
    )[0]
    assert item.title == "acme/engine"
    assert item.tags == ["inference"]


def test_openreview_source_unwraps_content_values(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "wall_harness.sources.http.httpx.get",
        lambda *args, **kwargs: response(
            {
                "notes": [
                    {
                        "id": "note-1",
                        "content": {
                            "title": {"value": "Learning useful representations"},
                            "abstract": {"value": "We study a new objective."},
                            "keywords": {"value": ["representation learning"]},
                        },
                        "cdate": 1786262400000,
                    }
                ]
            }
        ),
    )
    item = source_registry()["openreview"].fetch(
        SourceSpec(type="openreview", url="https://api2.openreview.net/notes?limit=10")
    )[0]
    assert item.title == "Learning useful representations"
    assert item.url == "https://openreview.net/forum?id=note-1"
    assert item.tags == ["representation learning"]


def test_web_source_extracts_readable_page_metadata(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    html = """<html><head><title>Systems dispatch</title>
    <meta name="description" content="A production reliability report."></head>
    <body><main><p>Longer article body.</p></main></body></html>"""
    monkeypatch.setattr(
        "wall_harness.sources.http.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            200, text=html, request=httpx.Request("GET", "https://example.com/report")
        ),
    )
    item = source_registry()["web"].fetch(
        SourceSpec(type="web", name="Dispatch", url="https://example.com/report")
    )[0]
    assert item.title == "Systems dispatch"
    assert item.summary == "A production reliability report."


def test_registry_exposes_all_builtin_sources() -> None:
    assert {"rss", "atom", "web", "hackernews", "github", "openreview"} <= set(source_registry())
