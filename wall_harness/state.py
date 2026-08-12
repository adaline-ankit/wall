from __future__ import annotations

import re
import sqlite3
from hashlib import sha256
from pathlib import Path

from .cluster import tokens
from .models import Item, SourceSpec


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
                summary TEXT NOT NULL DEFAULT '',
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (wall_name, item_id)
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS source_health (
                wall_name TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_label TEXT NOT NULL,
                source_type TEXT NOT NULL,
                status TEXT NOT NULL,
                item_count INTEGER NOT NULL DEFAULT 0,
                detail TEXT,
                checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (wall_name, source_id)
            )"""
        )
        seen_columns = {
            str(row[1]) for row in self.connection.execute("PRAGMA table_info(seen_items)")
        }
        if "summary" not in seen_columns:
            self.connection.execute(
                "ALTER TABLE seen_items ADD COLUMN summary TEXT NOT NULL DEFAULT ''"
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

    def concept_novelty(self, wall_name: str, item: Item) -> float:
        if self.novelty(wall_name, item) == 0:
            return 0.0
        document = tokens(f"{item.title} {item.summary}")
        if not document:
            return 1.0
        rows = self.connection.execute(
            """SELECT title, summary FROM seen_items
               WHERE wall_name = ? ORDER BY first_seen DESC LIMIT 500""",
            (wall_name,),
        ).fetchall()
        similarities = []
        for title, summary in rows:
            known = tokens(f"{title} {summary}")
            if known:
                similarities.append(len(document & known) / len(document | known))
        closest = max(similarities, default=0.0)
        if closest < 0.25:
            return 1.0
        return round(max(0.0, 1 - closest), 4)

    def remember(self, wall_name: str, items: list[Item]) -> None:
        self.connection.executemany(
            """INSERT OR IGNORE INTO seen_items(wall_name, item_id, title, summary)
               VALUES (?, ?, ?, ?)""",
            [(wall_name, item.id, item.title, item.summary) for item in items],
        )
        self.connection.commit()

    def record_source_health(
        self,
        wall_name: str,
        source: SourceSpec,
        *,
        source_label: str,
        status: str,
        item_count: int = 0,
        detail: str | None = None,
    ) -> None:
        source_id = sha256(str(source.url).encode()).hexdigest()[:16]
        self.connection.execute(
            """INSERT INTO source_health
            (wall_name, source_id, source_label, source_type, status, item_count, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(wall_name, source_id) DO UPDATE SET
              source_label = excluded.source_label,
              source_type = excluded.source_type,
              status = excluded.status,
              item_count = excluded.item_count,
              detail = excluded.detail,
              checked_at = CURRENT_TIMESTAMP""",
            (wall_name, source_id, source_label, source.type, status, item_count, detail),
        )
        self.connection.commit()

    def source_health(self, wall_name: str) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """SELECT source_label, source_type, status, item_count, detail
               FROM source_health WHERE wall_name = ? ORDER BY source_label""",
            (wall_name,),
        ).fetchall()
        return [
            {
                "source_label": str(row[0]),
                "source_type": str(row[1]),
                "status": str(row[2]),
                "item_count": int(row[3]),
                "detail": str(row[4]) if row[4] is not None else None,
            }
            for row in rows
        ]

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

    def feedback_actions(self, wall_name: str, item_ids: list[str]) -> dict[str, str]:
        if not item_ids:
            return {}
        placeholders = ", ".join("?" for _ in item_ids)
        rows = self.connection.execute(
            f"SELECT item_id, action FROM feedback WHERE wall_name = ? "
            f"AND item_id IN ({placeholders})",
            (wall_name, *item_ids),
        ).fetchall()
        return {str(item_id): str(action) for item_id, action in rows}

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
