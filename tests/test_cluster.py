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


def test_optional_embeddings_cluster_semantically_equivalent_coverage() -> None:
    class FakeEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            assert len(texts) == 3
            return [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]

    items = [
        make_item("New cache design", "https://one.test", "Cuts serving memory."),
        make_item("Serving gets leaner", "https://two.test", "A redesigned state store."),
        make_item("Compiler release", "https://three.test", "New static analysis."),
    ]

    clustered = cluster_items(items, embedder=FakeEmbedder(), semantic_threshold=0.95)

    assert clustered == [items[1], items[2]]


def test_invalid_embedding_shape_fails_closed() -> None:
    class BrokenEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0]]

    items = [
        make_item("One", "https://one.test"),
        make_item("Two", "https://two.test"),
    ]

    try:
        cluster_items(items, embedder=BrokenEmbedder())
    except ValueError as exc:
        assert "one vector per item" in str(exc)
    else:
        raise AssertionError("expected invalid embeddings to fail")


def test_precomputes_lexical_representations_once_per_item(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import wall_harness.cluster as cluster

    calls = 0
    original_tokens = cluster.tokens

    def counted_tokens(text: str) -> set[str]:
        nonlocal calls
        calls += 1
        return original_tokens(text)

    monkeypatch.setattr(cluster, "tokens", counted_tokens)
    items = [
        make_item(
            f"Research system uniquetopic{index}", f"https://example.com/{index}", "Unique summary"
        )
        for index in range(20)
    ]

    assert cluster.cluster_items(items, threshold=1.0) == items
    assert calls == len(items) * 2
