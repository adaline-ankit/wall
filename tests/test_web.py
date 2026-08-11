from pathlib import Path

from fastapi.testclient import TestClient

from wall_harness.models import Item, SourceSpec
from wall_harness.pipeline import WallPipeline
from wall_harness.providers import NoopAnalyzer
from wall_harness.web.app import create_app


class FakeSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        return [
            Item.create(
                title="Sparse attention reaches production",
                url="https://example.com/sparse",
                summary="A practical architecture report.",
                source=spec.name or "fixture",
            )
        ]


def write_spec(path: Path) -> None:
    path.write_text(
        """version: 1
name: frontier-test
goal: Track important model architecture changes.
topics:
  - name: sparse attention
    keywords: [architecture]
sources:
  - type: fake
    name: Fixture Lab
    url: https://example.com/feed
delivery:
  formats: [json]
  output_dir: .wall/output
"""
    )


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    spec_path = tmp_path / "wall.yaml"
    write_spec(spec_path)

    def pipeline_factory(spec):  # type: ignore[no-untyped-def]
        return WallPipeline(
            spec,
            state_path=tmp_path / ".wall" / "state.db",
            sources={"fake": FakeSource()},
            analyzer=NoopAnalyzer(),
        )

    app = create_app(
        spec_path,
        state_path=tmp_path / ".wall" / "state.db",
        pipeline_factory=pipeline_factory,
    )
    return TestClient(app), spec_path


def test_dashboard_and_spec_api_load(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    page = client.get("/")
    config = client.get("/api/spec")
    assert page.status_code == 200
    assert "Your reading," in page.text
    assert config.json()["name"] == "frontier-test"
    assert client.get("/api/edition").json() is None
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in page.headers["content-security-policy"]


def test_run_builds_an_edition_and_persists_latest(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = client.post("/api/run", json={"use_llm": False})
    assert response.status_code == 200
    assert response.json()["items"][0]["item"]["title"].startswith("Sparse attention")
    latest = client.get("/api/edition")
    assert latest.status_code == 200
    assert latest.json()["wall_name"] == "frontier-test"


def test_feedback_changes_future_editions(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    item = client.post("/api/run", json={"use_llm": False}).json()["items"][0]["item"]
    feedback = client.post("/api/feedback", json={"item": item, "action": "hide"})
    rerun = client.post("/api/run", json={"use_llm": False})
    assert feedback.status_code == 204
    assert rerun.json()["items"] == []


def test_feedback_api_restores_persisted_dashboard_state(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    item = client.post("/api/run", json={"use_llm": False}).json()["items"][0]["item"]
    client.post("/api/feedback", json={"item": item, "action": "save"})

    response = client.get("/api/feedback")

    assert response.status_code == 200
    assert response.json() == {item["id"]: "save"}


def test_spec_editor_validates_before_overwriting(tmp_path: Path) -> None:
    client, spec_path = make_client(tmp_path)
    original = spec_path.read_text()
    invalid = client.put("/api/spec", json={"yaml": "name: broken"})
    assert invalid.status_code == 422
    assert spec_path.read_text() == original

    updated = original.replace("frontier-test", "edited-wall")
    response = client.put("/api/spec", json={"yaml": updated})
    assert response.status_code == 200
    assert response.json()["name"] == "edited-wall"
    assert "edited-wall" in spec_path.read_text()


def test_spec_editor_rejects_duplicate_wall_names(tmp_path: Path) -> None:
    first = tmp_path / "ai.yaml"
    second = tmp_path / "systems.yaml"
    write_spec(first)
    second.write_text(first.read_text().replace("frontier-test", "systems-test"))
    client = TestClient(create_app(tmp_path, state_path=tmp_path / ".wall" / "state.db"))

    duplicate = second.read_text().replace("systems-test", "frontier-test")
    response = client.put("/api/spec", params={"wall": "systems-test"}, json={"yaml": duplicate})

    assert response.status_code == 422
    assert "unique" in response.json()["detail"]
    assert "systems-test" in second.read_text()


def test_run_error_does_not_expose_internal_details(tmp_path: Path) -> None:
    spec_path = tmp_path / "wall.yaml"
    write_spec(spec_path)

    class BrokenPipeline:
        def run(self, *, use_llm: bool):
            raise RuntimeError("secret-token-in-upstream-url")

    client = TestClient(create_app(spec_path, pipeline_factory=lambda spec: BrokenPipeline()))
    response = client.post("/api/run", json={"use_llm": False})

    assert response.status_code == 502
    assert response.json()["detail"] == "Wall build failed. Check the server logs for details."


def test_directory_workspace_lists_and_switches_walls(tmp_path: Path) -> None:
    first = tmp_path / "ai.yaml"
    second = tmp_path / "systems.yaml"
    write_spec(first)
    second.write_text(first.read_text().replace("frontier-test", "systems-test"))
    app = create_app(tmp_path, state_path=tmp_path / ".wall" / "state.db")
    client = TestClient(app)

    walls = client.get("/api/walls")
    selected = client.get("/api/spec", params={"wall": "systems-test"})
    missing = client.get("/api/spec", params={"wall": "missing"})

    assert walls.status_code == 200
    assert [wall["name"] for wall in walls.json()] == ["frontier-test", "systems-test"]
    assert selected.json()["name"] == "systems-test"
    assert missing.status_code == 404
