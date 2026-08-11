from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from wall_harness.models import EmbeddingConfig

from .base import Embedder


def _vectors(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        raise ValueError("Embedding provider returned no vector list")
    try:
        return [[float(component) for component in vector] for vector in value]
    except (TypeError, ValueError) as exc:
        raise ValueError("Embedding provider returned invalid vectors") from exc


@dataclass
class OllamaEmbedder:
    model: str
    base_url: str = "http://localhost:11434"

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        response.raise_for_status()
        return _vectors(response.json().get("embeddings"))


@dataclass
class OpenAIEmbedder:
    model: str
    api_key: str = field(repr=False)
    base_url: str = "https://api.openai.com/v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json().get("data")
        if not isinstance(payload, list):
            raise ValueError("Embedding provider returned no data list")
        try:
            indexes = [int(record["index"]) for record in payload]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Embedding provider returned invalid indexes") from exc
        if sorted(indexes) != list(range(len(texts))):
            raise ValueError("Embedding provider returned invalid indexes")
        ordered = [record for _, record in sorted(zip(indexes, payload, strict=True))]
        return _vectors([record.get("embedding") for record in ordered])


def embedder_from_config(config: EmbeddingConfig) -> Embedder | None:
    provider = config.provider.lower()
    if provider == "none":
        return None
    if provider == "ollama":
        return OllamaEmbedder(
            model=config.model or "embeddinggemma",
            base_url=config.base_url or "http://localhost:11434",
        )
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        return OpenAIEmbedder(
            model=config.model or "text-embedding-3-small",
            api_key=api_key,
            base_url=config.base_url or "https://api.openai.com/v1",
        )
    raise ValueError(f"Unknown embedding provider: {config.provider}")
