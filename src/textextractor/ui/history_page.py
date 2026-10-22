"""History: search, open, rename, favourite, delete (with Undo), clear all."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QScrollArea,
                               QVBoxLayout, QWidget)

from ..context import AppContext
from ..data.database import HistoryEntry
from .theme import theme
from .widgets import IconLabel, ThemedButton, clear_layout, make_label

log = logging.getLogger(__name__)


def format_date(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M")


class HistoryCard(QFrame):
    clicked = Signal()
    favoriteToggled = Signal()
    renameRequested = Signal()
    deleteRequested = Signal()

    def __init__(self, entry: HistoryEntry, compact: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.entry = entry
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 10, 12)
        row.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(8)
        title = make_label(entry.display_title(), "h3")
        title.setSizePolicy(title.sizePolicy().horizontalPolicy(), title.sizePolicy().verticalPolicy())
        head.addWidget(title)
        if entry.is_favorite and compact:
            head.addWidget(IconLabel("star-fill", 16, "accent"))
        head.addStretch(1)
        head.addWidget(make_label(format_date(entry.created_at), "small"))
        col.addLayout(head)
        flat = " ".join(entry.text.split())
        preview = QLabel(flat if len(flat) <= 200 else flat[:197] + "…")
        preview.setProperty("role", "muted")
        preview.setWordWrap(True)
        preview.setMaximumHeight(preview.fontMetrics().lineSpacing() * 2 + 6)
        col.addWidget(preview)
        row.addLayout(col, 1)

        if not compact:
            self._fav = ThemedButton("", "star-fill" if entry.is_favorite else "star", "icon", 20)
            self._fav.setToolTip("Remove from favorites" if entry.is_favorite else "Add to favorites")
            self._fav.clicked.connect(self.favoriteToggled)
            self._rename = ThemedButton("", "edit", "icon", 20)
            self._rename.setToolTip("Rename")
            self._rename.clicked.connect(self.renameRequested)
            self._delete = ThemedButton("", "trash", "icon", 20)
            self._delete.setToolTip("Delete")
            self._delete.clicked.connect(self.deleteRequested)
            for b in (self._fav, self._rename, self._delete):
                row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            if entry.is_favorite:
                self._fav.set_accent_icon(True)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class HistoryPage(QWidget):
    openRequested = Signal(object)
    changed = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 20)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.addWidget(make_label("History", "h1"))
        self._badge = make_label("", "badge")
        head.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        self._clear_all = ThemedButton("Clear all", "trash", "danger")
        self._clear_all.clicked.connect(self._confirm_clear_all)
        head.addWidget(self._clear_all)
        root.addLayout(head)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search saved text and titles")
        self._search.setClearButtonEnabled(True)
        root.addWidget(self._search)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda _t: self._timer.start())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("page")
        self._list = QVBoxLayout(host)
        self._list.setContentsMargins(0, 0, 8, 0)
        self._list.setSpacing(8)
        self._scroll.setWidget(host)
        root.addWidget(self._scroll, 1)

        self._empty = QWidget()
        el = QVBoxLayout(self._empty)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.setSpacing(8)
        el.addWidget(IconLabel("history", 44, "muted"), 0, Qt.AlignmentFlag.AlignCenter)
        self._empty_title = make_label("", "h2")
        self._empty_sub = make_label("", "muted")
        el.addWidget(self._empty_title, 0, Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self._empty_sub, 0, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._empty, 1)
        self.refresh()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self.refresh()

    def refresh(self) -> None:
        query = self._search.text()
        entries = self.ctx.repo.search(query, limit=300)
        total = self.ctx.repo.count()
        clear_layout(self._list)
        for entry in entries:
            card = HistoryCard(entry)
            card.clicked.connect(lambda e=entry: self.openRequested.emit(e))
            card.favoriteToggled.connect(lambda e=entry: self._toggle_fav(e))
            card.renameRequested.connect(lambda e=entry: self._rename(e))
            card.deleteRequested.connect(lambda e=entry: self._delete(e))
            self._list.addWidget(card)
        self._list.addStretch(1)
        self._badge.setText(f"{total} saved")
        self._badge.setVisible(total > 0)
        self._clear_all.setEnabled(total > 0)
        has = bool(entries)
        self._scroll.setVisible(has)
        self._empty.setVisible(not has)
        if not has:
            if query.strip():
                self._empty_title.setText("No matches")
                self._empty_sub.setText("No saved extraction contains that text.")
            else:
                self._empty_title.setText("Nothing saved yet")
                self._empty_sub.setText("Text you save after extracting will appear here.")

    # -------------------------------------------------------------- actions
    def _guard(self, fn) -> None:
        try:
            fn()
        except sqlite3.Error:
            log.exception("history operation failed")
            self._toast("Something went wrong with the history database.")
        self.refresh()
        self.changed.emit()

    def _toggle_fav(self, e: HistoryEntry) -> None:
        self._guard(lambda: self.ctx.repo.set_favorite(e.id, not e.is_favorite))

    def _rename(self, e: HistoryEntry) -> None:
        title, ok = QInputDialog.getText(self, "Rename", "Title:", QLineEdit.EchoMode.Normal, e.title or "")
        if ok:
            self._guard(lambda: self.ctx.repo.rename(e.id, title))

    def _delete(self, e: HistoryEntry) -> None:
        self._guard(lambda: self.ctx.repo.delete(e.id))
        w = self.window()
        if hasattr(w, "show_toast"):
            w.show_toast("Deleted", "Undo", lambda: self._guard(lambda: self.ctx.repo.restore(e)), 6000)

    def _confirm_clear_all(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Clear all history?")
        box.setText("This permanently deletes every saved extraction, including favorites. It can't be undone.")
        yes = box.addButton("Delete all", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self._guard(self.ctx.repo.clear_all)

    def _toast(self, msg: str) -> None:
        w = self.window()
        if hasattr(w, "show_toast"):
            w.show_toast(msg)
