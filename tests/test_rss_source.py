from datetime import UTC, datetime

import httpx

from wall_harness.models import SourceSpec
from wall_harness.sources.rss import RSSSource


def test_rss_source_fetches_with_a_bounded_timeout(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured = {}
    content = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test feed</title><item>
    <title>Sparse systems</title><link>https://example.com/item</link>
    <description>A useful report.</description><pubDate>Mon, 11 Aug 2025 12:00:00 GMT</pubDate>
    </item></channel></rss>"""

    def fake_get(url, **options):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured.update(options)
        return httpx.Response(200, content=content, request=httpx.Request("GET", str(url)))

    monkeypatch.setattr("wall_harness.sources.http.httpx.get", fake_get)
    items = RSSSource().fetch(SourceSpec(url="https://example.com/feed", cache_ttl_minutes=0))
    assert captured["timeout"] == 20
    assert captured["follow_redirects"] is True
    assert items[0].title == "Sparse systems"
    assert items[0].published_at == datetime(2025, 8, 11, 12, tzinfo=UTC)


def test_rss_source_surfaces_http_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_get(url, **options):  # type: ignore[no-untyped-def]
        del options
        return httpx.Response(503, request=httpx.Request("GET", str(url)))

    monkeypatch.setattr("wall_harness.sources.http.httpx.get", fake_get)
    monkeypatch.setattr("wall_harness.sources.http.time.sleep", lambda seconds: None)
    try:
        RSSSource().fetch(SourceSpec(url="https://example.com/feed", cache_ttl_minutes=0))
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 503
    else:
        raise AssertionError("expected an HTTP status error")
