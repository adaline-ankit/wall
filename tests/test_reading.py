from pathlib import Path

from fastapi.testclient import TestClient

from wall_harness.web.app import create_app


def write_spec(path: Path) -> None:
    path.write_text(
        """version: 1
name: personal-ai
goal: Stay current on AI.
topics:
  - name: AI
    keywords: [ai]
sources:
  - type: rss
    name: Example
    url: https://example.com/feed.xml
"""
    )


def client_for(tmp_path: Path) -> TestClient:
    spec_path = tmp_path / "wall.yaml"
    write_spec(spec_path)
    return TestClient(create_app(spec_path, state_path=tmp_path / ".wall" / "state.db"))


def test_reading_home_is_served_as_the_primary_workspace(tmp_path: Path) -> None:
    page = client_for(tmp_path).get("/")

    assert page.status_code == 200
    assert "Your reading," in page.text
    assert "made useful." in page.text
    assert "New draft" in page.text


def test_reading_entry_can_gather_notes_tasks_and_a_draft(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    entry = client.post(
        "/api/reading/entries",
        json={
            "title": "A practical guide to evaluation-driven agents",
            "url": "https://example.com/agents",
            "source": "Example Research",
            "summary": "A grounded analysis of how to evaluate long-running agents.",
            "tags": ["agents", "evals"],
            "origin": "browser",
        },
    )
    assert entry.status_code == 201
    entry_id = entry.json()["id"]
    assert entry.json()["status"] == "inbox"

    note = client.post(
        f"/api/reading/entries/{entry_id}/notes",
        json={"body": "The important distinction is measuring outcomes, not model fluency."},
    )
    task = client.post(
        "/api/reading/tasks",
        json={"title": "Compare this with our harness evaluation loop", "entry_id": entry_id},
    )
    draft = client.post(
        "/api/reading/drafts",
        json={"title": "What evaluation-driven agents get right", "entry_ids": [entry_id]},
    )

    assert note.status_code == 201
    assert task.status_code == 201
    assert draft.status_code == 201
    detail = client.get(f"/api/reading/entries/{entry_id}")
    assert detail.status_code == 200
    assert detail.json()["notes"][0]["body"].startswith("The important distinction")
    assert detail.json()["tasks"][0]["title"].startswith("Compare this")
    assert detail.json()["drafts"][0]["title"] == "What evaluation-driven agents get right"


def test_weekly_review_and_publication_keep_private_notes_private(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    entry = client.post(
        "/api/reading/entries",
        json={
            "title": "Frontier model release notes",
            "url": "https://example.com/release",
            "source": "Model Lab",
            "origin": "manual",
        },
    ).json()
    client.post(
        f"/api/reading/entries/{entry['id']}/notes",
        json={"body": "Private working note: check the benchmark methodology."},
    )
    client.post(
        "/api/reading/tasks",
        json={"title": "Read model card", "entry_id": entry["id"]},
    )
    draft = client.post(
        "/api/reading/drafts",
        json={
            "title": "The useful part of this release",
            "body": "A short public synthesis.",
            "entry_ids": [entry["id"]],
        },
    ).json()

    review = client.get("/api/reading/review")
    assert review.status_code == 200
    assert review.json()["open_tasks"][0]["title"] == "Read model card"
    assert review.json()["unfinished_drafts"][0]["id"] == draft["id"]

    published = client.post(f"/api/reading/drafts/{draft['id']}/publish")
    assert published.status_code == 200
    public_page = client.get(f"/read/{published.json()['slug']}")
    assert public_page.status_code == 200
    assert "A short public synthesis." in public_page.text
    assert "Private working note" not in public_page.text


def test_markdown_export_contains_private_workspace_content(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post(
        "/api/reading/entries",
        json={
            "title": "Useful paper",
            "url": "https://example.com/paper",
            "source": "arXiv",
            "origin": "email",
        },
    )

    export = client.get("/api/reading/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/zip")
    assert export.content.startswith(b"PK")
