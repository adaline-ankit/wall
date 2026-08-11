from __future__ import annotations

from wall_harness.models import WallEdition


def render_markdown(edition: WallEdition) -> str:
    lines = [
        f"# {edition.wall_name}",
        "",
        f"> {edition.goal}",
        "",
        f"_Generated {edition.generated_at:%Y-%m-%d %H:%M UTC} · "
        f"{edition.discovered_count} discovered · {edition.clustered_count} after clustering_",
        "",
    ]
    if not edition.items:
        lines.extend(["No items crossed your relevance threshold today.", ""])
    for index, ranked in enumerate(edition.items, 1):
        item = ranked.item
        lines.extend(
            [
                f"## {index}. [{item.title}]({item.url})",
                "",
                f"**{item.source}** · score {ranked.score:.2f} · {item.published_at:%Y-%m-%d}",
                "",
                ranked.analysis or item.summary or "No summary supplied by the source.",
                "",
                f"_Why here: {'; '.join(ranked.reasons) or 'recent source item'}_",
                "",
            ]
        )
    return "\n".join(lines)
