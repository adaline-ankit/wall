from base64 import b64encode
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


def test_configured_app_password_protects_network_service(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    spec_path = tmp_path / "wall.yaml"
    write_spec(spec_path)
    monkeypatch.setenv("WALL_APP_PASSWORD", "private-service-password")
    client = TestClient(create_app(spec_path, state_path=tmp_path / ".wall" / "state.db"))

    rejected = client.get("/")
    accepted = client.get(
        "/",
        headers={
            "Authorization": f"Basic {b64encode(b'margin:private-service-password').decode()}"
        },
    )

    assert rejected.status_code == 401
    assert rejected.headers["www-authenticate"] == 'Basic realm="Margin"'
    assert accepted.status_code == 200


def test_capture_token_can_write_to_the_inbox_but_cannot_read_the_private_app(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    spec_path = tmp_path / "wall.yaml"
    write_spec(spec_path)
    monkeypatch.setenv("WALL_APP_PASSWORD", "private-service-password")
    monkeypatch.setenv("WALL_CAPTURE_TOKEN", "narrow-write-token")
    client = TestClient(create_app(spec_path, state_path=tmp_path / ".wall" / "state.db"))

    rejected = client.post(
        "/api/reading/captures/browser",
        json={"title": "Untrusted request", "source": "Browser"},
    )
    invalid = client.post(
        "/api/reading/captures/browser",
        headers={"Authorization": "Bearer wrong-token"},
        json={"title": "Invalid token", "source": "Browser"},
    )
    captured = client.post(
        "/api/reading/captures/browser",
        headers={"Authorization": "Bearer narrow-write-token"},
        json={
            "title": "A safely captured article",
            "url": "https://example.com/captured",
            "source": "Browser",
        },
    )
    owner_capture = client.post(
        "/api/reading/captures/browser",
        headers={
            "Authorization": f"Basic {b64encode(b'margin:private-service-password').decode()}"
        },
        json={"title": "The owner's capture", "source": "Browser"},
    )
    read_attempt = client.get(
        "/api/reading/entries",
        headers={"Authorization": "Bearer narrow-write-token"},
    )

    assert rejected.status_code == 401
    assert rejected.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 401
    assert captured.status_code == 201
    assert captured.json()["origin"] == "browser"
    assert owner_capture.status_code == 201
    assert read_attempt.status_code == 401
    assert read_attempt.headers["www-authenticate"] == 'Basic realm="Margin"'


def test_wall_edition_can_be_added_to_the_reading_inbox_without_duplicates(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    client.post("/api/run", json={"use_llm": False})

    first = client.post("/api/reading/import/wall")
    second = client.post("/api/reading/import/wall")

    assert first.status_code == 201
    assert first.json()["imported_count"] == 1
    assert second.status_code == 201
    assert second.json()["imported_count"] == 0
    entries = client.get("/api/reading/entries").json()
    assert len(entries) == 1
    assert entries[0]["origin"] == "wall"


def test_refreshing_sources_builds_and_imports_new_wall_items(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    refreshed = client.post("/api/reading/refresh", json={"use_llm": False})

    assert refreshed.status_code == 201
    assert refreshed.json() == {
        "wall_name": "frontier-test",
        "item_count": 1,
        "imported_count": 1,
    }
    assert client.get("/api/edition").json()["wall_name"] == "frontier-test"
    assert client.get("/api/reading/entries").json()[0]["origin"] == "wall"
