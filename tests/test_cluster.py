from wall_harness.cluster import cluster_items
from wall_harness.models import Item


def make_item(title: str, url: str, summary: str = "") -> Item:
    return Item.create(title=title, url=url, summary=summary, source="test")


def test_clusters_similar_titles_and_keeps_richer_summary() -> None:
    short = make_item("Acme releases a new frontier model", "https://one.test", "Short")
    rich = make_item(
        "Acme releases new frontier model",
        "https://two.test",
        "A substantially richer description of the architecture.",
    )
    result = cluster_items([short, rich], threshold=0.5)
    assert result == [rich]


def test_keeps_distinct_items() -> None:
    items = [
        make_item("New database consensus protocol", "https://one.test"),
        make_item("Language model inference engine", "https://two.test"),
    ]
    assert cluster_items(items) == items
