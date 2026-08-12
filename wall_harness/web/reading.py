from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _identifier() -> str:
    return uuid.uuid4().hex[:16]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:72] or "untitled"


class ReadingEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=4096)
    source: str = Field(default="Saved link", min_length=1, max_length=200)
    summary: str = Field(default="", max_length=20_000)
    tags: list[str] = Field(default_factory=list, max_length=24)
    origin: Literal["manual", "browser", "email", "telegram", "wall", "rss"] = "manual"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = HttpUrl(value)
        if parsed.username or parsed.password:
            raise ValueError("URLs cannot contain credentials")
        return str(parsed).rstrip("/")

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip()[:60] for value in values if value.strip()))


class EntryUpdate(BaseModel):
    status: Literal["inbox", "reading", "kept", "archived"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    tags: list[str] | None = Field(default=None, max_length=24)


class EmailCapture(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    sender: str = Field(min_length=1, max_length=320)
    body: str = Field(default="", max_length=50_000)
    url: str | None = Field(default=None, max_length=4096)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return ReadingEntryCreate.validate_url(value)

    def as_entry(self) -> ReadingEntryCreate:
        match = re.search(r"https?://[^\s<>\]\[\"']+", self.body)
        return ReadingEntryCreate(
            title=self.subject,
            url=self.url or (match.group(0).rstrip(".,;:!?") if match else None),
            source=f"Forwarded from {self.sender}",
            summary=self.body,
            origin="email",
        )


class TelegramCapture(BaseModel):
    """Small, stable boundary around the Telegram webhook update we consume."""

    message: dict[str, object]

    def chat_id(self) -> str | None:
        chat = self.message.get("chat")
        if not isinstance(chat, dict) or chat.get("id") is None:
            return None
        return str(chat["id"])

    def as_entry(self) -> ReadingEntryCreate:
        text = self.message.get("text") or self.message.get("caption") or ""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Telegram update has no text or caption to save")
        sender = self.message.get("from")
        username = sender.get("username") if isinstance(sender, dict) else None
        sender_name = username if isinstance(username, str) and username else "Telegram"
        match = re.search(r"https?://[^\s<>\]\[\"']+", text)
        return ReadingEntryCreate(
            title=text.splitlines()[0].strip()[:500],
            url=match.group(0).rstrip(".,;:!?") if match else None,
            source=f"Telegram · {sender_name}",
            summary=text,
            origin="telegram",
        )


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=50_000)


class HighlightCreate(BaseModel):
    quote: str = Field(min_length=1, max_length=10_000)
    note: str = Field(default="", max_length=10_000)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    entry_id: str | None = Field(default=None, max_length=32)


class TaskUpdate(BaseModel):
    done: bool


class DraftCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=100_000)
    entry_ids: list[str] = Field(default_factory=list, max_length=100)


class DraftUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, max_length=100_000)
    entry_ids: list[str] | None = Field(default=None, max_length=100)


class DraftStarterRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    intent: str = Field(default="", max_length=2_000)
    entry_ids: list[str] = Field(min_length=1, max_length=24)


class LibraryQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1_000)


class ReadingStore:
    """Private, file-backed reading-to-writing workspace data."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS reading_entries (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                source TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                origin TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'inbox',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_notes (
                id TEXT PRIMARY KEY,
                entry_id TEXT NOT NULL REFERENCES reading_entries(id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_highlights (
                id TEXT PRIMARY KEY,
                entry_id TEXT NOT NULL REFERENCES reading_entries(id) ON DELETE CASCADE,
                quote TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_tasks (
                id TEXT PRIMARY KEY,
                entry_id TEXT REFERENCES reading_entries(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_drafts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                slug TEXT UNIQUE,
                published_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_draft_sources (
                draft_id TEXT NOT NULL REFERENCES reading_drafts(id) ON DELETE CASCADE,
                entry_id TEXT NOT NULL REFERENCES reading_entries(id) ON DELETE CASCADE,
                PRIMARY KEY (draft_id, entry_id)
            );
            CREATE INDEX IF NOT EXISTS idx_reading_entries_status ON reading_entries(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_reading_tasks_done ON reading_tasks(done, updated_at DESC);
            CREATE TABLE IF NOT EXISTS reading_refresh_jobs (
                id TEXT PRIMARY KEY,
                wall_name TEXT NOT NULL,
                status TEXT NOT NULL,
                item_count INTEGER,
                imported_count INTEGER,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_reading_refresh_jobs_created
              ON reading_refresh_jobs(created_at DESC);
            """
        )
        self.connection.commit()

    @staticmethod
    def _entry(row: sqlite3.Row) -> dict[str, object]:
        entry = dict(row)
        entry["tags"] = json.loads(str(entry.pop("tags_json")))
        return entry

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, object]:
        result = dict(row)
        if "done" in result:
            result["done"] = bool(result["done"])
        return result

    def _require_entry(self, entry_id: str) -> None:
        if (
            self.connection.execute(
                "SELECT 1 FROM reading_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            is None
        ):
            raise KeyError("Reading entry not found")

    def create_entry(self, request: ReadingEntryCreate) -> dict[str, object]:
        identifier = _identifier()
        now = _timestamp()
        self.connection.execute(
            """INSERT INTO reading_entries
            (id, title, url, source, summary, tags_json, origin, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'inbox', ?, ?)""",
            (
                identifier,
                request.title.strip(),
                request.url,
                request.source.strip(),
                request.summary.strip(),
                json.dumps(request.tags),
                request.origin,
                now,
                now,
            ),
        )
        self.connection.commit()
        return self.get_entry(identifier)

    def create_entry_if_new(self, request: ReadingEntryCreate) -> dict[str, object] | None:
        if request.url:
            existing = self.connection.execute(
                "SELECT id FROM reading_entries WHERE url = ?", (request.url,)
            ).fetchone()
            if existing is not None:
                return None
        return self.create_entry(request)

    def create_refresh_job(self, wall_name: str) -> dict[str, object]:
        identifier = _identifier()
        self.connection.execute(
            """INSERT INTO reading_refresh_jobs (id, wall_name, status, created_at)
            VALUES (?, ?, 'queued', ?)""",
            (identifier, wall_name, _timestamp()),
        )
        self.connection.commit()
        return self.get_refresh_job(identifier)

    def complete_refresh_job(
        self, identifier: str, *, item_count: int, imported_count: int
    ) -> dict[str, object]:
        self.connection.execute(
            """UPDATE reading_refresh_jobs
            SET status = 'completed', item_count = ?, imported_count = ?, completed_at = ?
            WHERE id = ?""",
            (item_count, imported_count, _timestamp(), identifier),
        )
        self.connection.commit()
        return self.get_refresh_job(identifier)

    def fail_refresh_job(self, identifier: str) -> dict[str, object]:
        self.connection.execute(
            """UPDATE reading_refresh_jobs
            SET status = 'failed', completed_at = ? WHERE id = ?""",
            (_timestamp(), identifier),
        )
        self.connection.commit()
        return self.get_refresh_job(identifier)

    def get_refresh_job(self, identifier: str) -> dict[str, object]:
        row = self.connection.execute(
            "SELECT * FROM reading_refresh_jobs WHERE id = ?", (identifier,)
        ).fetchone()
        if row is None:
            raise KeyError("Refresh job not found")
        return self._row(row)

    def latest_refresh_job(self) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT * FROM reading_refresh_jobs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return self._row(row) if row is not None else None

    def list_entries(self, status: str | None = None) -> list[dict[str, object]]:
        query = "SELECT * FROM reading_entries"
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at DESC"
        return [self._entry(row) for row in self.connection.execute(query, params).fetchall()]

    def get_entry(self, entry_id: str) -> dict[str, object]:
        row = self.connection.execute(
            "SELECT * FROM reading_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Reading entry not found")
        entry = self._entry(row)
        entry["notes"] = [
            self._row(note)
            for note in self.connection.execute(
                "SELECT * FROM reading_notes WHERE entry_id = ? ORDER BY created_at", (entry_id,)
            ).fetchall()
        ]
        entry["highlights"] = [
            self._row(highlight)
            for highlight in self.connection.execute(
                "SELECT * FROM reading_highlights WHERE entry_id = ? ORDER BY created_at",
                (entry_id,),
            ).fetchall()
        ]
        entry["tasks"] = [
            self._row(task)
            for task in self.connection.execute(
                "SELECT * FROM reading_tasks WHERE entry_id = ? ORDER BY done, updated_at DESC",
                (entry_id,),
            ).fetchall()
        ]
        entry["drafts"] = [
            self._row(draft)
            for draft in self.connection.execute(
                """SELECT d.* FROM reading_drafts d
                   JOIN reading_draft_sources s ON s.draft_id = d.id
                   WHERE s.entry_id = ? ORDER BY d.updated_at DESC""",
                (entry_id,),
            ).fetchall()
        ]
        return entry

    def update_entry(self, entry_id: str, request: EntryUpdate) -> dict[str, object]:
        self._require_entry(entry_id)
        fields: list[str] = []
        values: list[object] = []
        if request.status is not None:
            fields.append("status = ?")
            values.append(request.status)
        if request.title is not None:
            fields.append("title = ?")
            values.append(request.title.strip())
        if request.tags is not None:
            fields.append("tags_json = ?")
            values.append(
                json.dumps(list(dict.fromkeys(tag.strip() for tag in request.tags if tag.strip())))
            )
        if fields:
            fields.append("updated_at = ?")
            values.append(_timestamp())
            values.append(entry_id)
            self.connection.execute(
                f"UPDATE reading_entries SET {', '.join(fields)} WHERE id = ?", values
            )
            self.connection.commit()
        return self.get_entry(entry_id)

    def add_note(self, entry_id: str, request: NoteCreate) -> dict[str, object]:
        self._require_entry(entry_id)
        note: dict[str, object] = {
            "id": _identifier(),
            "entry_id": entry_id,
            "body": request.body.strip(),
            "created_at": _timestamp(),
        }
        self.connection.execute(
            "INSERT INTO reading_notes(id, entry_id, body, created_at) VALUES (?, ?, ?, ?)",
            tuple(note.values()),
        )
        self.connection.execute(
            "UPDATE reading_entries SET updated_at = ? WHERE id = ?", (_timestamp(), entry_id)
        )
        self.connection.commit()
        return note

    def add_highlight(self, entry_id: str, request: HighlightCreate) -> dict[str, object]:
        self._require_entry(entry_id)
        highlight: dict[str, object] = {
            "id": _identifier(),
            "entry_id": entry_id,
            "quote": request.quote.strip(),
            "note": request.note.strip(),
            "created_at": _timestamp(),
        }
        self.connection.execute(
            "INSERT INTO reading_highlights(id, entry_id, quote, note, created_at) VALUES (?, ?, ?, ?, ?)",
            tuple(highlight.values()),
        )
        self.connection.execute(
            "UPDATE reading_entries SET updated_at = ? WHERE id = ?", (_timestamp(), entry_id)
        )
        self.connection.commit()
        return highlight

    def create_task(self, request: TaskCreate) -> dict[str, object]:
        if request.entry_id:
            self._require_entry(request.entry_id)
        now = _timestamp()
        task: dict[str, object] = {
            "id": _identifier(),
            "entry_id": request.entry_id,
            "title": request.title.strip(),
            "done": False,
            "created_at": now,
            "updated_at": now,
        }
        self.connection.execute(
            "INSERT INTO reading_tasks(id, entry_id, title, done, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
            (task["id"], task["entry_id"], task["title"], now, now),
        )
        self.connection.commit()
        return task

    def list_tasks(self, include_done: bool = True) -> list[dict[str, object]]:
        query = "SELECT * FROM reading_tasks"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY done, updated_at DESC"
        return [self._row(row) for row in self.connection.execute(query).fetchall()]

    def update_task(self, task_id: str, request: TaskUpdate) -> dict[str, object]:
        self.connection.execute(
            "UPDATE reading_tasks SET done = ?, updated_at = ? WHERE id = ?",
            (int(request.done), _timestamp(), task_id),
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT * FROM reading_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Task not found")
        return self._row(row)

    def _set_draft_sources(self, draft_id: str, entry_ids: list[str]) -> None:
        for entry_id in entry_ids:
            self._require_entry(entry_id)
        self.connection.execute("DELETE FROM reading_draft_sources WHERE draft_id = ?", (draft_id,))
        self.connection.executemany(
            "INSERT INTO reading_draft_sources(draft_id, entry_id) VALUES (?, ?)",
            [(draft_id, entry_id) for entry_id in dict.fromkeys(entry_ids)],
        )

    def create_draft(self, request: DraftCreate) -> dict[str, object]:
        identifier = _identifier()
        now = _timestamp()
        self.connection.execute(
            "INSERT INTO reading_drafts(id, title, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (identifier, request.title.strip(), request.body.strip(), now, now),
        )
        self._set_draft_sources(identifier, request.entry_ids)
        self.connection.commit()
        return self.get_draft(identifier)

    def get_draft(self, draft_id: str) -> dict[str, object]:
        row = self.connection.execute(
            "SELECT * FROM reading_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Draft not found")
        draft = self._row(row)
        draft["sources"] = [
            self._entry(entry)
            for entry in self.connection.execute(
                """SELECT e.* FROM reading_entries e
                   JOIN reading_draft_sources s ON s.entry_id = e.id
                   WHERE s.draft_id = ? ORDER BY e.created_at""",
                (draft_id,),
            ).fetchall()
        ]
        return draft

    def list_drafts(self, status: str | None = None) -> list[dict[str, object]]:
        query = "SELECT * FROM reading_drafts"
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at DESC"
        return [self._row(row) for row in self.connection.execute(query, params).fetchall()]

    def update_draft(self, draft_id: str, request: DraftUpdate) -> dict[str, object]:
        if (
            self.connection.execute(
                "SELECT 1 FROM reading_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            is None
        ):
            raise KeyError("Draft not found")
        fields: list[str] = []
        values: list[object] = []
        if request.title is not None:
            fields.append("title = ?")
            values.append(request.title.strip())
        if request.body is not None:
            fields.append("body = ?")
            values.append(request.body.strip())
        if fields:
            fields.append("updated_at = ?")
            values.append(_timestamp())
            values.append(draft_id)
            self.connection.execute(
                f"UPDATE reading_drafts SET {', '.join(fields)} WHERE id = ?", values
            )
        if request.entry_ids is not None:
            self._set_draft_sources(draft_id, request.entry_ids)
        self.connection.commit()
        return self.get_draft(draft_id)

    def publish_draft(self, draft_id: str) -> dict[str, object]:
        draft = self.get_draft(draft_id)
        slug = str(draft.get("slug") or _slugify(str(draft["title"])))
        candidate = slug
        suffix = 2
        while self.connection.execute(
            "SELECT 1 FROM reading_drafts WHERE slug = ? AND id != ?", (candidate, draft_id)
        ).fetchone():
            candidate = f"{slug}-{suffix}"
            suffix += 1
        now = _timestamp()
        self.connection.execute(
            "UPDATE reading_drafts SET status = 'published', slug = ?, published_at = ?, updated_at = ? WHERE id = ?",
            (candidate, now, now, draft_id),
        )
        self.connection.commit()
        return self.get_draft(draft_id)

    def public_draft(self, slug: str) -> dict[str, object]:
        row = self.connection.execute(
            "SELECT id FROM reading_drafts WHERE slug = ? AND status = 'published'", (slug,)
        ).fetchone()
        if row is None:
            raise KeyError("Published post not found")
        return self.get_draft(str(row["id"]))

    def weekly_review(self) -> dict[str, object]:
        return {
            "open_tasks": self.list_tasks(include_done=False),
            "unfinished_drafts": self.list_drafts(status="draft"),
            "recent_entries": self.list_entries()[:8],
        }

    def relevant_material(self, question: str, limit: int = 6) -> list[dict[str, object]]:
        """Return the saved material most likely to help answer a private question."""
        question_terms = {
            term[:6] for term in re.findall(r"[a-z0-9]+", question.lower()) if len(term) >= 3
        }
        ranked: list[tuple[int, dict[str, object]]] = []
        for entry in self.list_entries():
            detail = self.get_entry(str(entry["id"]))
            notes = detail["notes"]
            highlights = detail["highlights"]
            tags = detail["tags"]
            assert isinstance(notes, list)
            assert isinstance(highlights, list)
            assert isinstance(tags, list)
            material = " ".join(
                [
                    str(detail["title"]),
                    str(detail["source"]),
                    str(detail["summary"]),
                    *[str(tag) for tag in tags],
                    *[str(note["body"]) for note in notes if isinstance(note, dict)],
                    *[
                        str(highlight["quote"])
                        for highlight in highlights
                        if isinstance(highlight, dict)
                    ],
                    *[
                        str(highlight["note"])
                        for highlight in highlights
                        if isinstance(highlight, dict)
                    ],
                ]
            ).lower()
            material_terms = {
                term[:6] for term in re.findall(r"[a-z0-9]+", material) if len(term) >= 3
            }
            score = len(question_terms & material_terms)
            if score:
                ranked.append((score, detail))
        ranked.sort(
            key=lambda candidate: (candidate[0], str(candidate[1]["updated_at"])), reverse=True
        )
        return [entry for _, entry in ranked[:limit]]

    def entries_for_draft_starter(self, entry_ids: list[str]) -> list[dict[str, object]]:
        unique_ids = list(dict.fromkeys(entry_ids))
        for entry_id in unique_ids:
            self._require_entry(entry_id)
        return [self.get_entry(entry_id) for entry_id in unique_ids]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ReadingStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
