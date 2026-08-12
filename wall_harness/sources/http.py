from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "Wall/0.16 (+https://github.com/adaline-ankit/wall)"
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 30.0
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
MAX_CACHE_BODY_BYTES = 5_000_000


def get(url: str, *, github: bool = False, cache_ttl_minutes: int = 0) -> httpx.Response:
    if cached := load_cached_response(url, cache_ttl_minutes):
        return cached
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/atom+xml, application/rss+xml, "
        "application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
    }
    if github and (token := os.getenv("GITHUB_TOKEN")):
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
        except httpx.TransportError:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            time.sleep(exponential_delay(attempt))
            continue
        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS - 1:
            time.sleep(retry_delay(response, attempt))
            continue
        response.raise_for_status()
        cache_response(url, response, cache_ttl_minutes)
        return response
    raise AssertionError("source request retry loop exhausted unexpectedly")


def exponential_delay(attempt: int) -> float:
    return float(min(MAX_RETRY_DELAY_SECONDS, 0.5 * (2**attempt)))


def retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = str(response.headers.get("Retry-After", ""))
    if retry_after:
        try:
            return min(MAX_RETRY_DELAY_SECONDS, max(0.0, float(retry_after)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError, IndexError):
                pass
            else:
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return min(
                    MAX_RETRY_DELAY_SECONDS,
                    max(0.0, (retry_at - datetime.now(UTC)).total_seconds()),
                )
    return exponential_delay(attempt)


def get_json(url: str, *, github: bool = False, cache_ttl_minutes: int = 0) -> dict[str, Any]:
    payload = get(url, github=github, cache_ttl_minutes=cache_ttl_minutes).json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return payload


def cache_path(url: str) -> Path:
    root = Path(os.getenv("WALL_HTTP_CACHE_DIR", ".wall/http-cache"))
    return root / f"{sha256(url.encode()).hexdigest()}.json"


def load_cached_response(url: str, cache_ttl_minutes: int) -> httpx.Response | None:
    if cache_ttl_minutes <= 0:
        return None
    path = cache_path(url)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(payload["fetched_at"])
        content = base64.b64decode(payload["content"], validate=True)
        status_code = int(payload["status_code"])
        content_type = str(payload.get("content_type", ""))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if time.time() - fetched_at >= cache_ttl_minutes * 60:
        return None
    headers = {"Content-Type": content_type} if content_type else {}
    return httpx.Response(
        status_code,
        headers=headers,
        content=content,
        request=httpx.Request("GET", url),
    )


def cache_response(url: str, response: httpx.Response, cache_ttl_minutes: int) -> None:
    if (
        cache_ttl_minutes <= 0
        or not response.is_success
        or len(response.content) > MAX_CACHE_BODY_BYTES
    ):
        return
    path = cache_path(url)
    payload = {
        "fetched_at": time.time(),
        "status_code": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "content": base64.b64encode(response.content).decode("ascii"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
