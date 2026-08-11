from __future__ import annotations

import html

from wall_harness.models import WallEdition


def render_html(edition: WallEdition) -> str:
    cards = []
    for ranked in edition.items:
        item = ranked.item
        reasons = " · ".join(ranked.reasons)
        body = ranked.analysis or item.summary or "No summary supplied by the source."
        cards.append(f"""<article>
  <div class="meta"><span>{html.escape(item.source)}</span><b>{ranked.score:.2f}</b></div>
  <h2><a href="{html.escape(item.url, quote=True)}">{html.escape(item.title)}</a></h2>
  <p>{html.escape(body)}</p>
  <footer>{html.escape(reasons)}</footer>
</article>""")
    empty = "<p class=empty>No items crossed your relevance threshold today.</p>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(edition.wall_name)}</title><style>
:root{{--ink:#171717;--muted:#6b6b63;--paper:#f5f2e9;--card:#fffdf7;--accent:#d3532c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:17px/1.55 ui-serif,Georgia,serif}}
main{{max-width:820px;margin:auto;padding:64px 24px}}header{{border-bottom:3px solid var(--ink);margin-bottom:28px}}
h1{{font:800 clamp(42px,8vw,78px)/.95 ui-sans-serif,system-ui;margin:0 0 16px;letter-spacing:-.06em}}
.goal{{font-size:22px;max-width:650px}}.edition{{color:var(--muted);font:13px ui-monospace,monospace;text-transform:uppercase}}
article{{background:var(--card);border:1px solid #d7d1c3;padding:24px;margin:16px 0;box-shadow:4px 4px 0 #ded8ca}}
.meta{{display:flex;justify-content:space-between;color:var(--accent);font:700 12px ui-monospace,monospace;text-transform:uppercase}}
h2{{font:700 28px/1.1 ui-sans-serif,system-ui;letter-spacing:-.03em}}a{{color:inherit;text-decoration-thickness:2px;text-decoration-color:var(--accent)}}
footer{{color:var(--muted);font:12px ui-monospace,monospace;border-top:1px solid #ddd6c8;padding-top:12px}}.empty{{padding:48px 0}}
</style></head><body><main><header><p class="edition">Daily intent diff · {edition.generated_at:%B %d, %Y}</p>
<h1>{html.escape(edition.wall_name)}</h1><p class="goal">{html.escape(edition.goal)}</p>
<p class="edition">{edition.discovered_count} discovered · {edition.clustered_count} clustered · {len(edition.items)} selected</p></header>
{"".join(cards) if cards else empty}</main></body></html>"""
