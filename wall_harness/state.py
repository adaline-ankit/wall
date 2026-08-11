from __future__ import annotations

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

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> KnowledgeState:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
