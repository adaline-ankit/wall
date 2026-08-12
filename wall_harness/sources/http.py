from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

USER_AGENT = "Wall/0.15 (+https://github.com/adaline-ankit/wall)"
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 30.0
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def get(url: str, *, github: bool = False) -> httpx.Response:
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


def get_json(url: str, *, github: bool = False) -> dict[str, Any]:
    payload = get(url, github=github).json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return payload
