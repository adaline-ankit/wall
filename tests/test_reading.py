from base64 import b64encode
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
    assert "Ask your library" in page.text
    assert "Source-backed starter" in page.text


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
    highlight = client.post(
        f"/api/reading/entries/{entry_id}/highlights",
        json={"quote": "Measure outcomes, not model fluency.", "note": "The line to cite later."},
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
    assert highlight.status_code == 201
    assert task.status_code == 201
    assert draft.status_code == 201
    detail = client.get(f"/api/reading/entries/{entry_id}")
    assert detail.status_code == 200
    assert detail.json()["notes"][0]["body"].startswith("The important distinction")
    assert detail.json()["highlights"][0]["quote"] == "Measure outcomes, not model fluency."
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


def test_published_post_escapes_user_supplied_content(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    entry = client.post(
        "/api/reading/entries",
        json={
            "title": "<script>entry()</script>",
            "url": "https://example.com/?q=one&two=three",
            "source": "Research",
            "origin": "manual",
        },
    ).json()
    draft = client.post(
        "/api/reading/drafts",
        json={
            "title": "<script>title()</script>",
            "body": "<img src=x onerror=alert(1)>",
            "entry_ids": [entry["id"]],
        },
    ).json()

    published = client.post(f"/api/reading/drafts/{draft['id']}/publish")
    public_page = client.get(f"/read/{published.json()['slug']}")

    assert "<script>" not in public_page.text
    assert "<img " not in public_page.text
    assert "&lt;script&gt;title()&lt;/script&gt;" in public_page.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in public_page.text
    assert "?q=one&amp;two=three" in public_page.text


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


def test_browser_and_forwarded_email_captures_land_in_the_same_inbox(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    browser = client.post(
        "/api/reading/captures/browser",
        json={
            "title": "A browser-saved article",
            "url": "https://example.com/browser-save",
            "source": "Browser",
        },
    )
    email = client.post(
        "/api/reading/captures/email",
        json={
            "subject": "A paper to return to",
            "sender": "research@example.com",
            "body": "Worth reading: https://example.com/forwarded-paper",
        },
    )

    assert browser.status_code == 201
    assert browser.json()["origin"] == "browser"
    assert email.status_code == 201
    assert email.json()["origin"] == "email"
    assert email.json()["url"] == "https://example.com/forwarded-paper"
    assert [entry["origin"] for entry in client.get("/api/reading/entries").json()] == [
        "email",
        "browser",
    ]


def test_local_library_assistant_returns_source_bound_material(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    entry = client.post(
        "/api/reading/entries",
        json={
            "title": "A serious way to evaluate coding agents",
            "url": "https://example.com/agent-evals",
            "source": "Agent Research",
            "summary": "Evaluation needs deterministic verifiers and repeated trials.",
            "tags": ["agents", "evals"],
            "origin": "manual",
        },
    ).json()
    client.post(
        f"/api/reading/entries/{entry['id']}/notes",
        json={"body": "Use this when we compare routing strategies."},
    )

    answer = client.post(
        "/api/reading/ask",
        json={"question": "What have I kept about evaluating agents?"},
    )

    assert answer.status_code == 200
    assert answer.json()["mode"] == "local"
    assert answer.json()["sources"][0]["id"] == entry["id"]
    assert "deterministic verifiers" in answer.json()["answer"]
    assert "routing strategies" in answer.json()["answer"]


def test_library_assistant_configuration_failures_do_not_leak_details(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    spec_path = tmp_path / "wall.yaml"
    write_spec(spec_path)
    spec_path.write_text(spec_path.read_text() + "\nllm:\n  provider: openai\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(spec_path, state_path=tmp_path / ".wall" / "state.db"))

    answer = client.post("/api/reading/ask", json={"question": "What did I save?"})

    assert answer.status_code == 502
    assert (
        answer.json()["detail"]
        == "Library assistant is unavailable. Your saved material remains local."
    )


def test_source_linked_draft_starter_is_reviewable_before_saving(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    entry = client.post(
        "/api/reading/entries",
        json={
            "title": "What repeatable evaluations teach us",
            "url": "https://example.com/repeatable-evals",
            "source": "Agent Research",
            "summary": "Repeated trials expose whether an improvement is stable.",
            "origin": "manual",
        },
    ).json()
    client.post(
        f"/api/reading/entries/{entry['id']}/notes",
        json={"body": "Connect this to why single-run demos are misleading."},
    )

    starter = client.post(
        "/api/reading/drafts/starter",
        json={
            "title": "Why repeated trials belong in agent evaluation",
            "intent": "Make the case for a more disciplined evaluation culture.",
            "entry_ids": [entry["id"]],
        },
    )

    assert starter.status_code == 200
    assert starter.json()["mode"] == "local"
    assert starter.json()["sources"][0]["id"] == entry["id"]
    assert "[Source 1]" in starter.json()["body"]
    assert "single-run demos" in starter.json()["body"]
    assert client.get("/api/reading/drafts").json() == []


def test_published_posts_are_public_while_the_workspace_stays_private(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    spec_path = tmp_path / "wall.yaml"
    write_spec(spec_path)
    monkeypatch.setenv("WALL_APP_PASSWORD", "private-service-password")
    client = TestClient(create_app(spec_path, state_path=tmp_path / ".wall" / "state.db"))
    headers = {"Authorization": f"Basic {b64encode(b'margin:private-service-password').decode()}"}
    entry = client.post(
        "/api/reading/entries",
        headers=headers,
        json={
            "title": "A source worth sharing",
            "url": "https://example.com/source",
            "source": "Research",
            "origin": "manual",
        },
    ).json()
    draft = client.post(
        "/api/reading/drafts",
        headers=headers,
        json={
            "title": "A public thought",
            "body": "Only this is public.",
            "entry_ids": [entry["id"]],
        },
    ).json()
    published = client.post(f"/api/reading/drafts/{draft['id']}/publish", headers=headers).json()

    assert client.get("/api/reading/entries").status_code == 401
    public_page = client.get(f"/read/{published['slug']}")
    assert public_page.status_code == 200
    assert "Only this is public." in public_page.text
    assert client.get("/static/app.css").status_code == 200
