from __future__ import annotations

import re
from math import isfinite, sqrt

from .models import Item
from .providers.base import Embedder

WORDS = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "has",
    "have",
    "into",
    "not",
    "that",
    "the",
    "their",
    "this",
    "using",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
    "your",
}
SHORT_TERMS = {"ai", "db", "ml", "os", "rl"}


def tokens(text: str) -> set[str]:
    return {
        word
        for word in WORDS.findall(text.lower())
        if (len(word) > 2 or word in SHORT_TERMS) and word not in STOPWORDS
    }


def similarity(left: Item, right: Item) -> float:
    left_title, right_title = tokens(left.title), tokens(right.title)
    left_content = tokens(f"{left.title} {left.summary}")
    right_content = tokens(f"{right.title} {right.summary}")
    if not left_content or not right_content:
        return 0.0
    title_jaccard = (
        len(left_title & right_title) / len(left_title | right_title)
        if left_title and right_title
        else 0.0
    )
    shared = len(left_content & right_content)
    content_overlap = shared / min(len(left_content), len(right_content)) if shared >= 3 else 0.0
    return max(title_jaccard, content_overlap * 0.85)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("Embedding vectors must be non-empty and have equal dimensions")
    if not all(isfinite(value) for value in [*left, *right]):
        raise ValueError("Embedding vectors must contain only finite values")
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def cluster_items(
    items: list[Item],
    threshold: float = 0.6,
    *,
    embedder: Embedder | None = None,
    semantic_threshold: float = 0.86,
) -> list[Item]:
    """Collapse likely coverage duplicates, retaining the richest item."""
    vectors = (
        embedder.embed([f"{item.title}\n{item.summary[:6000]}" for item in items])
        if embedder is not None and len(items) > 1
        else None
    )
    if vectors is not None and len(vectors) != len(items):
        raise ValueError("Embedding provider must return one vector per item")

    representatives: list[tuple[Item, int]] = []
    for item_index, item in enumerate(items):
        match = next(
            (
                (existing, vector_index)
                for existing, vector_index in representatives
                if similarity(item, existing) >= threshold
                or (
                    vectors is not None
                    and cosine_similarity(vectors[item_index], vectors[vector_index])
                    >= semantic_threshold
                )
            ),
            None,
        )
        if match is None:
            representatives.append((item, item_index))
        elif len(item.summary) > len(match[0].summary):
            representatives[representatives.index(match)] = (item, item_index)
    return [item for item, _ in representatives]
