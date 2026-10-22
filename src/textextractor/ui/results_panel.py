"""Right-hand panel: placeholder → progress → editable result (with find, actions, links, blocks) or message."""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import quote

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QProgressBar,
                               QScrollArea, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)
from PySide6.QtWidgets import QTextEdit

from ..core.models import OcrBlock
from ..core.text_tools import DetectedEntity, char_count, detect_entities, find_all, word_count
from .theme import theme
from .widgets import FlowLayout, IconLabel, ThemedButton, clear_layout, make_card, make_label

_MAX_BLOCK_CARDS = 60


def _toast(widget: QWidget, text: str) -> None:
    w = widget.window()
    if hasattr(w, "show_toast"):
        w.show_toast(text)


class ResultsPanel(QWidget):
    saveRequested = Signal()
    extractAgainRequested = Signal()
    cancelRequested = Signal()

    PLACEHOLDER, RUNNING, MESSAGE, EDITOR = range(4)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._saved = False
        self._matches: list[tuple[int, int]] = []
        self._match_index = -1
        self._msg_primary: Callable[[], None] | None = None
        self._msg_secondary: Callable[[], None] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        root.addWidget(self._stack)
        self._stack.addWidget(self._build_placeholder())
        self._stack.addWidget(self._build_running())
        self._stack.addWidget(self._build_message())
        self._stack.addWidget(self._build_editor())

        self._entity_timer = QTimer(self)
        self._entity_timer.setSingleShot(True)
        self._entity_timer.setInterval(250)
        self._entity_timer.timeout.connect(self._refresh_entities)
        theme.changed.connect(lambda *_: self._apply_highlights())
        self.show_placeholder()

    # ------------------------------------------------------------------ builders
    def _centered(self, *widgets: QWidget) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        for w in widgets:
            lay.addWidget(w, 0, Qt.AlignmentFlag.AlignCenter)
        return page

    def _build_placeholder(self) -> QWidget:
        title = make_label("Ready when you are", "h2")
        sub = make_label("Optionally drag on the image to select an area,\nthen click Extract Text.", "muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return self._centered(IconLabel("text", 44, "muted"), title, sub)

    def _build_running(self) -> QWidget:
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(240)
        cancel = ThemedButton("Cancel", None, "ghost")
        cancel.clicked.connect(self.cancelRequested)
        self._running_label = make_label("Recognizing text…", "h3")
        return self._centered(self._running_label, self._bar, cancel)

    def _build_message(self) -> QWidget:
        self._msg_title = make_label("", "h2", wrap=True)
        self._msg_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg_title.setMaximumWidth(380)
        self._msg_detail = make_label("", "muted", wrap=True)
        self._msg_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg_detail.setMaximumWidth(380)
        self._msg_primary_btn = ThemedButton("", None, "primary")
        self._msg_secondary_btn = ThemedButton("", None, "ghost")
        self._msg_primary_btn.clicked.connect(lambda: self._msg_primary and self._msg_primary())
        self._msg_secondary_btn.clicked.connect(lambda: self._msg_secondary and self._msg_secondary())
        return self._centered(self._msg_title, self._msg_detail, self._msg_primary_btn, self._msg_secondary_btn)

    def _build_editor(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self._stats = make_label("", "h3")
        self._engine_label = make_label("", "small")
        head.addWidget(self._stats)
        head.addStretch()
        head.addWidget(self._engine_label)
        lay.addLayout(head)

        find = QHBoxLayout()
        find.setSpacing(6)
        self._find = QLineEdit()
        self._find.setPlaceholderText("Find in text  (Ctrl+F)")
        self._find.setClearButtonEnabled(True)
        self._find.textChanged.connect(self._on_find_changed)
        self._find.returnPressed.connect(lambda: self._step_match(1))
        self._find_count = make_label("", "small")
        self._prev = ThemedButton("", "chevron-up", "icon")
        self._next = ThemedButton("", "chevron-down", "icon")
        self._prev.setToolTip("Previous match")
        self._next.setToolTip("Next match")
        self._prev.clicked.connect(lambda: self._step_match(-1))
        self._next.clicked.connect(lambda: self._step_match(1))
        find.addWidget(self._find, 1)
        find.addWidget(self._find_count)
        find.addWidget(self._prev)
        find.addWidget(self._next)
        lay.addLayout(find)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("No text. Extract again, or type here.")
        self._editor.setAcceptDrops(False)  # let image drops reach the main window instead of inserting a path
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.selectionChanged.connect(self._on_selection_changed)
        lay.addWidget(self._editor, 1)

        actions = QWidget()
        flow = FlowLayout(actions, 8, 8)
        self._copy_all = ThemedButton("Copy all", "copy", "primary")
        self._copy_sel = ThemedButton("Copy selection", None, "secondary")
        self._share = ThemedButton("Share", "share", "secondary")
        self._save = ThemedButton("Save", "save", "secondary")
        self._clear = ThemedButton("Clear", "x", "secondary")
        self._again = ThemedButton("Extract again", "refresh", "secondary")
        for b in (self._copy_all, self._copy_sel, self._share, self._save, self._clear, self._again):
            flow.addWidget(b)
        self._copy_all.clicked.connect(self.copy_all)
        self._copy_sel.clicked.connect(self.copy_selection)
        self._save.clicked.connect(self.saveRequested)
        self._clear.clicked.connect(self._editor.clear)
        self._again.clicked.connect(self.extractAgainRequested)
        menu = QMenu(self)
        menu.addAction("Save as text file…", self.export_txt)
        menu.addAction("Send by email…", self.send_email)
        self._share.setMenu(menu)
        lay.addWidget(actions)

        self._tabs = QTabWidget()
        self._tabs.setMaximumHeight(190)
        self._blocks_host = QWidget()
        self._blocks_lay = QVBoxLayout(self._blocks_host)
        self._blocks_lay.setContentsMargins(0, 4, 0, 4)
        self._blocks_lay.setSpacing(6)
        blocks_scroll = QScrollArea()
        blocks_scroll.setWidgetResizable(True)
        blocks_scroll.setWidget(self._blocks_host)
        self._entities_host = QWidget()
        self._entities_flow = FlowLayout(self._entities_host, 8, 8)
        self._entities_flow.setContentsMargins(0, 8, 0, 8)
        ent_scroll = QScrollArea()
        ent_scroll.setWidgetResizable(True)
        ent_scroll.setWidget(self._entities_host)
        self._tabs.addTab(blocks_scroll, "Text blocks")
        self._tabs.addTab(ent_scroll, "Links and contacts")
        lay.addWidget(self._tabs)

        self._disclaimer = make_label(
            "Accuracy depends on image quality, resolution, lighting, font and language. Always review the result.",
            "small", wrap=True)
        lay.addWidget(self._disclaimer)
        return page

    # ------------------------------------------------------------------ states
    def show_placeholder(self) -> None:
        self._stack.setCurrentIndex(self.PLACEHOLDER)

    def show_running(self, text: str = "Recognizing text…") -> None:
        self._running_label.setText(text)
        self._stack.setCurrentIndex(self.RUNNING)

    def show_message(self, title: str, detail: str, primary_label: str, primary: Callable[[], None],
                     secondary_label: str | None = None, secondary: Callable[[], None] | None = None) -> None:
        self._msg_title.setText(title)
        self._msg_detail.setText(detail)
        self._msg_detail.setVisible(bool(detail))
        self._msg_primary_btn.setText(primary_label)
        self._msg_primary = primary
        self._msg_secondary_btn.setVisible(bool(secondary_label))
        self._msg_secondary_btn.setText(secondary_label or "")
        self._msg_secondary = secondary
        self._stack.setCurrentIndex(self.MESSAGE)

    def show_result(self, text: str, blocks: list[OcrBlock], engine_label: str = "", elapsed: float = 0.0,
                    saved: bool = False) -> None:
        self._find.clear()
        self._editor.setPlainText(text)
        self._editor.document().setModified(False)
        self._editor.moveCursor(QTextCursor.MoveOperation.Start)
        self._engine_label.setText(f"{engine_label} · {elapsed:.1f}s" if engine_label and elapsed else engine_label)
        self.set_saved(saved)
        self._fill_blocks(blocks)
        self._refresh_entities()
        self._on_text_changed()
        self._stack.setCurrentIndex(self.EDITOR)

    def is_editor_visible(self) -> bool:
        return self._stack.currentIndex() == self.EDITOR

    # ------------------------------------------------------------------ data access
    def text(self) -> str:
        return self._editor.toPlainText()

    def is_modified(self) -> bool:
        return self._editor.document().isModified()

    def mark_clean(self) -> None:
        self._editor.document().setModified(False)

    def set_saved(self, saved: bool) -> None:
        self._saved = saved
        self._save.setText("Update saved" if saved else "Save")

    def focus_find(self) -> None:
        if self.is_editor_visible():
            self._find.setFocus()
            self._find.selectAll()

    # ------------------------------------------------------------------ clipboard & export
    def copy_all(self) -> None:
        if self.text():
            QGuiApplication.clipboard().setText(self.text())
            _toast(self, "Copied to clipboard")

    def copy_selection(self) -> None:
        sel = self._editor.textCursor().selectedText().replace("\u2029", "\n")
        if sel:
            QGuiApplication.clipboard().setText(sel)
            _toast(self, "Selection copied")

    def export_txt(self) -> None:
        if not self.text().strip():
            _toast(self, "There is no text to save")
            return
        default = str(Path.home() / "extracted-text.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save text", default, "Text files (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.text(), encoding="utf-8")
            _toast(self, "Text file saved")
        except OSError:
            _toast(self, "Couldn't save the file. Check the location and permissions.")

    def send_email(self) -> None:
        text = self.text()
        if not text.strip():
            _toast(self, "There is no text to send")
            return
        limit = 1800  # mailto: URLs are length-limited by mail clients
        body = text[:limit]
        url = QUrl(f"mailto:?subject={quote('Extracted text')}&body={quote(body)}")
        if not QDesktopServices.openUrl(url):
            _toast(self, "No email app could be opened")
        elif len(text) > limit:
            _toast(self, "Long text was shortened for email. Use “Save as text file” to send everything.")

    # ------------------------------------------------------------------ slots
    def _on_text_changed(self) -> None:
        t = self._editor.toPlainText()
        self._stats.setText(f"{word_count(t):,} words · {char_count(t):,} characters")
        has = bool(t)
        self._copy_all.setEnabled(has)
        self._share.setEnabled(has)
        self._save.setEnabled(bool(t.strip()))
        self._clear.setEnabled(has)
        self._recompute_matches(keep_position=True)
        self._entity_timer.start()

    def _on_selection_changed(self) -> None:
        self._copy_sel.setEnabled(self._editor.textCursor().hasSelection())

    # ------------------------------------------------------------------ find
    def _on_find_changed(self, _t: str) -> None:
        self._match_index = -1
        self._recompute_matches(keep_position=False)
        if self._matches:
            self._step_match(1)

    def _recompute_matches(self, keep_position: bool) -> None:
        self._matches = find_all(self._editor.toPlainText(), self._find.text())
        if not keep_position or self._match_index >= len(self._matches):
            self._match_index = -1
        has = bool(self._matches)
        self._prev.setEnabled(has)
        self._next.setEnabled(has)
        if self._find.text():
            n = len(self._matches)
            cur = f"{self._match_index + 1} of {n}" if self._match_index >= 0 else f"{n} found"
            self._find_count.setText(cur if n else "No matches")
        else:
            self._find_count.setText("")
        self._apply_highlights()

    def _step_match(self, direction: int) -> None:
        if not self._matches:
            return
        self._match_index = (self._match_index + direction) % len(self._matches)
        start, end = self._matches[self._match_index]
        cur = self._editor.textCursor()
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cur)
        self._editor.ensureCursorVisible()
        self._find_count.setText(f"{self._match_index + 1} of {len(self._matches)}")
        self._apply_highlights()

    def _apply_highlights(self) -> None:
        p = theme.palette
        sels = []
        for i, (start, end) in enumerate(self._matches):
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(p.highlight_current if i == self._match_index else p.highlight))
            if i == self._match_index:
                fmt.setForeground(QColor("#000000"))
            es = QTextEdit.ExtraSelection()
            cur = QTextCursor(self._editor.document())
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            es.cursor = cur
            es.format = fmt
            sels.append(es)
        self._editor.setExtraSelections(sels)

    # ------------------------------------------------------------------ blocks & entities
    def _fill_blocks(self, blocks: list[OcrBlock]) -> None:
        clear_layout(self._blocks_lay)
        shown = blocks[:_MAX_BLOCK_CARDS]
        for i, b in enumerate(shown, 1):
            card = make_card(flat=True)
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 8, 6, 8)
            preview = b.text if len(b.text) <= 220 else b.text[:217] + "…"
            lab = QLabel(preview)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            btn = ThemedButton("", "copy", "icon")
            btn.setToolTip(f"Copy block {i}")
            btn.clicked.connect(lambda _=False, t=b.text, n=i: self._copy_block(t, n))
            row.addWidget(lab, 1)
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            self._blocks_lay.addWidget(card)
        self._blocks_lay.addStretch()
        self._tabs.setTabText(0, f"Text blocks ({len(blocks)})")
        self._tabs.setTabVisible(0, len(blocks) > 1)
        self._update_tabs_visibility()

    def _copy_block(self, text: str, n: int) -> None:
        QGuiApplication.clipboard().setText(text)
        _toast(self, f"Block {n} copied")

    def _refresh_entities(self) -> None:
        entities = detect_entities(self._editor.toPlainText())
        clear_layout(self._entities_flow)
        icon_for = {"url": "link", "email": "mail", "phone": "phone"}
        for e in entities[:40]:
            label = e.value if len(e.value) <= 42 else e.value[:39] + "…"
            chip = ThemedButton(label, icon_for[e.kind], "chip", 16)
            chip.setToolTip({"url": "Open in browser", "email": "Write an email", "phone": "Copy phone number"}[e.kind])
            chip.clicked.connect(lambda _=False, ent=e: self._open_entity(ent))
            self._entities_flow.addWidget(chip)
        self._tabs.setTabText(1, f"Links and contacts ({len(entities)})")
        self._tabs.setTabVisible(1, bool(entities))
        self._update_tabs_visibility()

    def _update_tabs_visibility(self) -> None:
        visible = [i for i in range(self._tabs.count()) if self._tabs.isTabVisible(i)]
        self._tabs.setVisible(bool(visible))
        if visible and not self._tabs.isTabVisible(self._tabs.currentIndex()):
            self._tabs.setCurrentIndex(visible[0])

    def _open_entity(self, e: DetectedEntity) -> None:
        if e.kind == "url":
            url = e.value if e.value.lower().startswith("http") else f"https://{e.value}"
            if not QDesktopServices.openUrl(QUrl(url)):
                _toast(self, "Couldn't open the link")
        elif e.kind == "email":
            if not QDesktopServices.openUrl(QUrl(f"mailto:{e.value}")):
                _toast(self, "No email app could be opened")
        else:
            QGuiApplication.clipboard().setText(e.value)
            _toast(self, "Phone number copied")
