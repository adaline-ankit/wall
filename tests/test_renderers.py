from datetime import UTC, datetime

from wall_harness.models import Item, RankedItem, WallEdition
from wall_harness.renderers import render_html, render_markdown


def test_renderers_escape_html_and_emit_link() -> None:
    item = Item.create(
        title="<Model>", url="https://example.com/?a=1&b=2", summary="A & B", source="Lab"
    )
    edition = WallEdition(
        wall_name="Test <Wall>",
        goal="Learn & test",
        generated_at=datetime.now(UTC),
        items=[RankedItem(item=item, score=0.9, reasons=["new"], novelty=1)],
        discovered_count=1,
        clustered_count=1,
    )
    html = render_html(edition)
    markdown = render_markdown(edition)
    assert "&lt;Model&gt;" in html
    assert "A &amp; B" in html
    assert "[<Model>](https://example.com/?a=1&b=2)" in markdown
