from __future__ import annotations

import os
from typing import Any

import httpx

USER_AGENT = "Wall/0.7 (+https://github.com/adaline-ankit/wall)"


def get(url: str, *, github: bool = False) -> httpx.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if github and (token := os.getenv("GITHUB_TOKEN")):
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    response = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
    response.raise_for_status()
    return response


def get_json(url: str, *, github: bool = False) -> dict[str, Any]:
    payload = get(url, github=github).json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return payload
