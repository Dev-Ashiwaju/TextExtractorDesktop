"""Application services shared by all pages (hand-wired dependency container)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from . import APP_NAME, ORG_NAME
from .data.database import HistoryRepository
from .workers import TaskManager

THEMES = ("system", "light", "dark")
ENGINES = ("auto", "tesseract", "rapidocr")
AUTO_CLEAR_CHOICES = (0, 7, 30, 90)


def data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    p = Path(base) if base else Path.home() / f".{ORG_NAME.lower()}"
    p.mkdir(parents=True, exist_ok=True)
    return p


class AppSettings:
    """Thin typed wrapper over QSettings. Never stores image or text content (only file paths of recent images)."""

    def __init__(self, qsettings: QSettings | None = None):
        self._s = qsettings or QSettings(ORG_NAME, APP_NAME)

    @property
    def theme(self) -> str:
        v = str(self._s.value("theme", "system"))
        return v if v in THEMES else "system"

    @theme.setter
    def theme(self, v: str) -> None:
        self._s.setValue("theme", v)

    @property
    def engine(self) -> str:
        v = str(self._s.value("ocr_engine", "auto"))
        return v if v in ENGINES else "auto"

    @engine.setter
    def engine(self, v: str) -> None:
        self._s.setValue("ocr_engine", v)

    @property
    def language(self) -> str:
        return str(self._s.value("ocr_language", "eng")) or "eng"

    @language.setter
    def language(self, v: str) -> None:
        self._s.setValue("ocr_language", v)

    @property
    def auto_clear_days(self) -> int:
        try:
            v = int(self._s.value("auto_clear_days", 0))
        except (TypeError, ValueError):
            v = 0
        return v if v in AUTO_CLEAR_CHOICES else 0

    @auto_clear_days.setter
    def auto_clear_days(self, v: int) -> None:
        self._s.setValue("auto_clear_days", int(v))

    # recent image files --------------------------------------------------------
    def recent_files(self) -> list[str]:
        try:
            data = json.loads(str(self._s.value("recent_files", "[]")))
            return [p for p in data if isinstance(p, str)]
        except (ValueError, TypeError):
            return []

    def add_recent(self, path: str, limit: int = 6) -> None:
        files = [path] + [p for p in self.recent_files() if p != path]
        self._s.setValue("recent_files", json.dumps(files[:limit]))

    def existing_recent_files(self) -> list[str]:
        return [p for p in self.recent_files() if Path(p).is_file()]

    # window --------------------------------------------------------------------
    def geometry(self):
        return self._s.value("geometry")

    def set_geometry(self, data) -> None:
        self._s.setValue("geometry", data)


@dataclass
class AppContext:
    repo: HistoryRepository
    settings: AppSettings
    tasks: TaskManager
