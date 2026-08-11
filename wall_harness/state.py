from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .models import Item


class KnowledgeState:
    """Local record of what a wall has seen; no account or cloud required."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS seen_items (
                wall_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                title TEXT NOT NULL,
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (wall_name, item_id)
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS feedback (
                wall_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                action TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (wall_name, item_id)
            )"""
        )

    def novelty(self, wall_name: str, item: Item) -> float:
        row = self.connection.execute(
            "SELECT 1 FROM seen_items WHERE wall_name = ? AND item_id = ?",
            (wall_name, item.id),
        ).fetchone()
        return 0.0 if row else 1.0

    def remember(self, wall_name: str, items: list[Item]) -> None:
        self.connection.executemany(
            "INSERT OR IGNORE INTO seen_items(wall_name, item_id, title) VALUES (?, ?, ?)",
            [(wall_name, item.id, item.title) for item in items],
        )
        self.connection.commit()

    def record_feedback(self, wall_name: str, item: Item, action: str) -> None:
        allowed = {"save", "hide", "known", "more_like_this"}
        if action not in allowed:
            raise ValueError(f"feedback action must be one of: {', '.join(sorted(allowed))}")
        self.connection.execute(
            """INSERT INTO feedback(wall_name, item_id, action, title, summary)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(wall_name, item_id) DO UPDATE SET
                 action = excluded.action,
                 title = excluded.title,
                 summary = excluded.summary,
                 updated_at = CURRENT_TIMESTAMP""",
            (wall_name, item.id, action, item.title, item.summary),
        )
        self.connection.commit()

    def feedback_action(self, wall_name: str, item_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT action FROM feedback WHERE wall_name = ? AND item_id = ?",
            (wall_name, item_id),
        ).fetchone()
        return str(row[0]) if row else None

    def positive_terms(self, wall_name: str) -> set[str]:
        rows = self.connection.execute(
            """SELECT title, summary FROM feedback
               WHERE wall_name = ? AND action = 'more_like_this'""",
            (wall_name,),
        ).fetchall()
        words = re.compile(r"[a-z0-9]+")
        return {
            token
            for title, summary in rows
            for token in words.findall(f"{title} {summary}".lower())
            if len(token) > 3
        }

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> KnowledgeState:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
