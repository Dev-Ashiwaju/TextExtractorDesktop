"""SQLite history store. Local only; the file is created with owner-only permissions where supported."""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    text: str
    title: str | None
    created_at: float
    updated_at: float
    image_path: str | None = None   # reference only, never a copy of the image
    is_favorite: bool = False

    def display_title(self) -> str:
        if self.title and self.title.strip():
            return self.title.strip()
        for line in self.text.splitlines():
            if line.strip():
                return line.strip()[:60]
        return "Untitled"


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class HistoryRepository:
    def __init__(self, path: str | Path = ":memory:", clock: Callable[[], float] = time.time):
        self._clock = clock
        is_file = str(path) != ":memory:"
        if is_file:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        if is_file:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        self._migrate()

    # schema -----------------------------------------------------------------
    def _migrate(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    title TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    image_path TEXT,
                    is_favorite INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC);
                """
            )
        # future migrations: if version < 2: ...
        self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._db.commit()

    @staticmethod
    def _row(r: sqlite3.Row) -> HistoryEntry:
        return HistoryEntry(r["id"], r["text"], r["title"], r["created_at"], r["updated_at"],
                            r["image_path"], bool(r["is_favorite"]))

    # queries ----------------------------------------------------------------
    def search(self, query: str = "", limit: int = 500) -> list[HistoryEntry]:
        q = query.strip()
        if q:
            like = f"%{_escape_like(q)}%"
            cur = self._db.execute(
                "SELECT * FROM history WHERE text LIKE ? ESCAPE '\\' OR IFNULL(title,'') LIKE ? ESCAPE '\\' "
                "ORDER BY created_at DESC, id DESC LIMIT ?", (like, like, limit))
        else:
            cur = self._db.execute("SELECT * FROM history ORDER BY created_at DESC, id DESC LIMIT ?", (limit,))
        return [self._row(r) for r in cur.fetchall()]

    def recent(self, limit: int = 5) -> list[HistoryEntry]:
        return self.search("", limit)

    def get(self, entry_id: int) -> HistoryEntry | None:
        r = self._db.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
        return self._row(r) if r else None

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM history").fetchone()[0]

    # commands ---------------------------------------------------------------
    def insert(self, text: str, image_path: str | None = None) -> int:
        now = self._clock()
        cur = self._db.execute(
            "INSERT INTO history(text, title, created_at, updated_at, image_path, is_favorite) VALUES (?,?,?,?,?,0)",
            (text, None, now, now, image_path))
        self._db.commit()
        return int(cur.lastrowid)

    def restore(self, entry: HistoryEntry) -> None:
        """Re-insert a deleted entry with its original id (used by Undo)."""
        self._db.execute(
            "INSERT OR REPLACE INTO history(id, text, title, created_at, updated_at, image_path, is_favorite) "
            "VALUES (?,?,?,?,?,?,?)",
            (entry.id, entry.text, entry.title, entry.created_at, entry.updated_at, entry.image_path, int(entry.is_favorite)))
        self._db.commit()

    def update_text(self, entry_id: int, text: str) -> None:
        self._db.execute("UPDATE history SET text=?, updated_at=? WHERE id=?", (text, self._clock(), entry_id))
        self._db.commit()

    def rename(self, entry_id: int, title: str | None) -> None:
        title = (title or "").strip() or None
        self._db.execute("UPDATE history SET title=?, updated_at=? WHERE id=?", (title, self._clock(), entry_id))
        self._db.commit()

    def set_favorite(self, entry_id: int, favorite: bool) -> None:
        self._db.execute("UPDATE history SET is_favorite=? WHERE id=?", (int(favorite), entry_id))
        self._db.commit()

    def delete(self, entry_id: int) -> None:
        self._db.execute("DELETE FROM history WHERE id=?", (entry_id,))
        self._db.commit()

    def clear_all(self) -> None:
        self._db.execute("DELETE FROM history")
        self._db.commit()
        self._db.execute("VACUUM")  # actually drop the deleted text from the file

    def delete_older_than_days(self, days: int) -> int:
        """Favourites are kept."""
        cutoff = self._clock() - days * 86400
        cur = self._db.execute("DELETE FROM history WHERE created_at < ? AND is_favorite = 0", (cutoff,))
        self._db.commit()
        return cur.rowcount

    def close(self) -> None:
        self._db.close()


__all__ = ["HistoryEntry", "HistoryRepository", "replace"]
