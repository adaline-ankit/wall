from __future__ import annotations

import re

from .models import Item

WORDS = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    return {word for word in WORDS.findall(text.lower()) if len(word) > 2}


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
    content_overlap = (
        shared / min(len(left_content), len(right_content)) if shared >= 3 else 0.0
    )
    return max(title_jaccard, content_overlap * 0.85)


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
