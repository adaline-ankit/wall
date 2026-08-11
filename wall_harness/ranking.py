from __future__ import annotations

import math
from datetime import UTC, datetime

from .cluster import tokens
from .models import Item, RankedItem, WallSpec
from .state import KnowledgeState


def rank_item(item: Item, spec: WallSpec, state: KnowledgeState, now: datetime) -> RankedItem:
    document = tokens(f"{item.title} {item.summary} {' '.join(item.tags)}")
    feedback_action = state.feedback_action(spec.name, item.id)
    if feedback_action == "hide":
        return RankedItem(item=item, score=0.0, novelty=0.0, reasons=["hidden by you"])
    excluded = [
        phrase
        for phrase in spec.exclude
        if phrase.lower() in f"{item.title} {item.summary}".lower()
    ]
    if excluded:
        return RankedItem(item=item, score=0.0, novelty=0.0, reasons=[f"excluded: {excluded[0]}"])

    matched: list[tuple[str, float]] = []
    total_weight = sum(topic.weight for topic in spec.topics) or 1
    for topic in spec.topics:
        topic_terms = tokens(f"{topic.name} {' '.join(topic.keywords)}")
        overlap = len(document & topic_terms) / max(1, len(topic_terms))
        if overlap:
            matched.append((topic.name, topic.weight * min(1.0, overlap * 2)))
    relevance = sum(score for _, score in matched) / total_weight
    age_hours = max(0.0, (now - item.published_at).total_seconds() / 3600)
    recency = math.pow(0.5, age_hours / spec.ranking.recency_half_life_hours)
    novelty = 0.0 if feedback_action == "known" else state.concept_novelty(spec.name, item)
    source_weight = spec.ranking.source_weights.get(item.source, 1.0)
    novelty_share = spec.ranking.novelty_weight
    score = source_weight * ((0.65 * relevance) + (0.35 * recency))
    score = ((1 - novelty_share) * score) + (novelty_share * novelty)
    reasons = [f"matches {name}" for name, _ in sorted(matched, key=lambda pair: -pair[1])[:3]]
    positive_terms = state.positive_terms(spec.name)
    feedback_overlap = len(document & positive_terms) / max(1, len(document))
    if feedback_overlap:
        score += min(0.12, feedback_overlap * 0.5)
        reasons.append("matches your feedback")
    if novelty >= 0.8:
        reasons.append("new to your wall")
    elif novelty:
        reasons.append("updates a known concept")
    return RankedItem(item=item, score=min(1.0, round(score, 4)), novelty=novelty, reasons=reasons)


def rank_items(items: list[Item], spec: WallSpec, state: KnowledgeState) -> list[RankedItem]:
    now = datetime.now(UTC)
    ranked = [rank_item(item, spec, state, now) for item in items]
    eligible = [item for item in ranked if item.score >= spec.ranking.minimum_score]
    return sorted(eligible, key=lambda item: (-item.score, item.item.published_at))[
        : spec.ranking.max_items
    ]
