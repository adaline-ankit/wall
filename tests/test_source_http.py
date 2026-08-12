import httpx
import pytest

from wall_harness.sources.http import get


def _response(status: int, *, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        headers=headers,
        request=httpx.Request("GET", "https://example.com/feed"),
    )


def test_get_retries_a_transient_server_failure_before_returning_a_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter([_response(503), _response(200)])
    waits: list[float] = []

    monkeypatch.setattr(
        "wall_harness.sources.http.httpx.get", lambda *args, **kwargs: next(responses)
    )
    monkeypatch.setattr("wall_harness.sources.http.time.sleep", waits.append)

    response = get("https://example.com/feed")

    assert response.status_code == 200
    assert waits == [0.5]


def test_get_honors_a_bounded_retry_after_for_rate_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter([_response(429, headers={"Retry-After": "3"}), _response(200)])
    waits: list[float] = []

    monkeypatch.setattr(
        "wall_harness.sources.http.httpx.get", lambda *args, **kwargs: next(responses)
    )
    monkeypatch.setattr("wall_harness.sources.http.time.sleep", waits.append)

    assert get("https://example.com/feed").status_code == 200
    assert waits == [3.0]


def test_get_bounds_an_excessive_retry_after_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter([_response(503, headers={"Retry-After": "3600"}), _response(200)])
    waits: list[float] = []

    monkeypatch.setattr(
        "wall_harness.sources.http.httpx.get", lambda *args, **kwargs: next(responses)
    )
    monkeypatch.setattr("wall_harness.sources.http.time.sleep", waits.append)

    assert get("https://example.com/feed").status_code == 200
    assert waits == [30.0]


def test_get_retries_a_transport_error_before_returning_a_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    waits: list[float] = []

    def fake_get(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            request = httpx.Request("GET", "https://example.com/feed")
            raise httpx.ConnectError("offline", request=request)
        return _response(200)

    monkeypatch.setattr("wall_harness.sources.http.httpx.get", fake_get)
    monkeypatch.setattr("wall_harness.sources.http.time.sleep", waits.append)

    assert get("https://example.com/feed").status_code == 200
    assert calls == 2
    assert waits == [0.5]


def test_get_does_not_retry_a_permanent_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    waits: list[float] = []

    def fake_get(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(404)

    monkeypatch.setattr("wall_harness.sources.http.httpx.get", fake_get)
    monkeypatch.setattr("wall_harness.sources.http.time.sleep", waits.append)

    with pytest.raises(httpx.HTTPStatusError):
        get("https://example.com/feed")

    assert calls == 1
    assert waits == []


def test_get_reuses_a_fresh_local_cache_entry(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def fake_get(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            content=b"cached source body",
            headers={"Content-Type": "application/json"},
            request=httpx.Request("GET", "https://example.com/feed?private=value"),
        )

    monkeypatch.setenv("WALL_HTTP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr("wall_harness.sources.http.httpx.get", fake_get)

    first = get("https://example.com/feed?private=value", cache_ttl_minutes=30)
    second = get("https://example.com/feed?private=value", cache_ttl_minutes=30)

    assert first.content == second.content == b"cached source body"
    assert calls == 1
    assert all("private" not in path.name for path in (tmp_path / "cache").iterdir())


def test_get_refreshes_an_expired_local_cache_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    calls = 0
    now = [1_000.0]

    def fake_get(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            content=f"response-{calls}".encode(),
            request=httpx.Request("GET", "https://example.com/feed"),
        )

    monkeypatch.setenv("WALL_HTTP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr("wall_harness.sources.http.httpx.get", fake_get)
    monkeypatch.setattr("wall_harness.sources.http.time.time", lambda: now[0])

    assert get("https://example.com/feed", cache_ttl_minutes=1).content == b"response-1"
    now[0] += 61
    assert get("https://example.com/feed", cache_ttl_minutes=1).content == b"response-2"
    assert calls == 2


def test_get_can_disable_local_caching(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def fake_get(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(200)

    monkeypatch.setenv("WALL_HTTP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr("wall_harness.sources.http.httpx.get", fake_get)

    get("https://example.com/feed", cache_ttl_minutes=0)
    get("https://example.com/feed", cache_ttl_minutes=0)

    assert calls == 2
    assert not (tmp_path / "cache").exists()
