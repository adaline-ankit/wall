from __future__ import annotations

import re

from .models import Item

WORDS = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    return {word for word in WORDS.findall(text.lower()) if len(word) > 2}


def similarity(left: Item, right: Item) -> float:
    a, b = tokens(left.title), tokens(right.title)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_items(items: list[Item], threshold: float = 0.6) -> list[Item]:
    """Collapse likely coverage duplicates, retaining the richest item."""
    representatives: list[Item] = []
    for item in items:
        match = next(
            (existing for existing in representatives if similarity(item, existing) >= threshold),
            None,
        )
        if match is None:
            representatives.append(item)
        elif len(item.summary) > len(match.summary):
            representatives[representatives.index(match)] = item
    return representatives
