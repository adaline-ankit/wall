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


def test_clusters_different_headlines_about_the_same_concept() -> None:
    first = make_item(
        "Acme launches its newest model",
        "https://one.test",
        "The Acme release uses sparse mixture of experts routing for efficient inference.",
    )
    second = make_item(
        "Sparse expert routing reaches Acme production",
        "https://two.test",
        "Acme describes mixture of experts inference in its new model release.",
    )
    assert len(cluster_items([first, second], threshold=0.5)) == 1
