"""Main window: sidebar navigation, pages, toast, shortcuts, drag & drop."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..context import AppContext
from ..data.database import HistoryEntry
from .extract_page import ExtractPage, is_image_path
from .history_page import HistoryPage
from .privacy_page import PrivacyPage
from .qt_images import qimage_to_png_bytes
from .settings_page import SettingsPage
from .theme import theme
from .widgets import IconLabel, NavButton, Toast, make_label


class MainWindow(QMainWindow):
    EXTRACT, HISTORY, SETTINGS, PRIVACY = range(4)

    def __init__(self, ctx: AppContext, logo: QPixmap | None = None):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 780)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)

        central = QWidget()
        central.setObjectName("page")
        self.setCentralWidget(central)
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ---- sidebar
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(224)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 14)
        brand.setSpacing(10)
        if logo is not None:
            lab = make_label()
            lab.setPixmap(logo.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            brand.addWidget(lab)
        brand.addWidget(make_label(APP_NAME, "appname"))
        brand.addStretch(1)
        sl.addLayout(brand)
        self._nav: list[NavButton] = []
        for label, icon in (("Extract", "text"), ("History", "history"), ("Settings", "settings"), ("Privacy", "shield")):
            btn = NavButton(label, icon)
            idx = len(self._nav)
            btn.clicked.connect(lambda _=False, i=idx: self.select_page(i))
            self._nav.append(btn)
            sl.addWidget(btn)
        sl.addStretch(1)
        foot = QHBoxLayout()
        foot.setContentsMargins(6, 0, 0, 0)
        foot.setSpacing(8)
        foot.addWidget(IconLabel("lock", 16, "muted"))
        foot.addWidget(make_label(f"Offline · v{__version__}", "small"))
        foot.addStretch(1)
        sl.addLayout(foot)
        row.addWidget(side)

        # ---- pages
        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self.extract_page = ExtractPage(ctx)
        self.history_page = HistoryPage(ctx)
        self.settings_page = SettingsPage(ctx)
        self.privacy_page = PrivacyPage()
        for p in (self.extract_page, self.history_page, self.settings_page, self.privacy_page):
            self.pages.addWidget(p)
        row.addWidget(self.pages, 1)

        self.toast = Toast(central)

        # ---- wiring
        self.extract_page.historyChanged.connect(self.history_page.refresh)
        self.extract_page.openSettingsRequested.connect(lambda: self.select_page(self.SETTINGS))
        self.extract_page.openHistoryEntryRequested.connect(self.open_entry)
        self.history_page.openRequested.connect(self.open_entry)
        self.history_page.changed.connect(self.extract_page.refresh_home)
        self.settings_page.historyCleared.connect(self._history_cleared)
        self.settings_page.themeChanged.connect(theme.set_mode)

        self._shortcuts()
        self.select_page(self.EXTRACT)
        geo = ctx.settings.geometry()
        if isinstance(geo, (QByteArray, bytes)):
            self.restoreGeometry(geo)

    # ------------------------------------------------------------------ navigation
    def select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self._nav[index].setChecked(True)
        if index == self.EXTRACT and not self.extract_page.in_workspace():
            self.extract_page.refresh_home()

    def open_entry(self, entry: HistoryEntry) -> None:
        self.select_page(self.EXTRACT)
        self.extract_page.open_saved(entry)

    def open_path(self, path: str) -> None:
        if Path(path).is_file():
            self.select_page(self.EXTRACT)
            self.extract_page.load_path(path)

    def _history_cleared(self) -> None:
        self.history_page.refresh()
        self.extract_page.refresh_home()

    def show_toast(self, text: str, action_text: str | None = None, action=None, timeout_ms: int = 4500) -> None:
        self.toast.show_message(text, action_text, action, timeout_ms)

    # ------------------------------------------------------------------ shortcuts
    def _shortcuts(self) -> None:
        def add(seq: str, fn) -> None:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)

        add("Ctrl+O", lambda: (self.select_page(self.EXTRACT), self.extract_page.open_file_dialog()))
        add("Ctrl+V", self._paste)
        add("Ctrl+Shift+X", lambda: (self.select_page(self.EXTRACT), self.extract_page.capture_screen()))
        add("Ctrl+Return", self._extract_shortcut)
        add("Ctrl+Enter", self._extract_shortcut)
        add("Ctrl+S", self._save_shortcut)
        add("Ctrl+F", self._find_shortcut)
        for i in range(4):
            add(f"Ctrl+{i + 1}", lambda i=i: self.select_page(i))

    def _paste(self) -> None:
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QPlainTextEdit)):  # normal text paste where the user is typing
            w.paste()
            return
        self.select_page(self.EXTRACT)
        self.extract_page.paste_from_clipboard()

    def _extract_shortcut(self) -> None:
        if self.pages.currentIndex() == self.EXTRACT and self.extract_page.in_workspace():
            self.extract_page.start_extract()

    def _save_shortcut(self) -> None:
        if self.pages.currentIndex() == self.EXTRACT and self.extract_page.in_workspace():
            self.extract_page.save_current()

    def _find_shortcut(self) -> None:
        if self.pages.currentIndex() == self.EXTRACT and self.extract_page.in_workspace():
            self.extract_page.results.focus_find()

    # ------------------------------------------------------------------ drag & drop
    @staticmethod
    def _droppable(md) -> bool:
        if md.hasImage():
            return True
        return any(u.isLocalFile() and is_image_path(u.toLocalFile()) for u in md.urls())

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if self._droppable(e.mimeData()):
            e.acceptProposedAction()
            self.extract_page.set_drop_active(True)

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self.extract_page.set_drop_active(False)

    def dropEvent(self, e) -> None:  # noqa: N802
        self.extract_page.set_drop_active(False)
        md = e.mimeData()
        for u in md.urls():
            if u.isLocalFile() and is_image_path(u.toLocalFile()):
                e.acceptProposedAction()
                self.select_page(self.EXTRACT)
                self.extract_page.load_path(u.toLocalFile())
                return
        if md.hasImage():
            img = QGuiApplication.clipboard().image() if False else md.imageData()
            if img is not None and not img.isNull():
                e.acceptProposedAction()
                self.select_page(self.EXTRACT)
                self.extract_page.load_bytes(qimage_to_png_bytes(img), "Dropped image")

    # ------------------------------------------------------------------ lifecycle
    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.extract_page.has_unsaved_changes():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Quit without saving?")
            box.setText("You have edited the extracted text without saving it.")
            save = box.addButton("Save and quit", QMessageBox.ButtonRole.AcceptRole)
            quit_ = box.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is save:
                self.extract_page.save_current()
            elif box.clickedButton() is not quit_:
                e.ignore()
                return
        self.ctx.settings.set_geometry(self.saveGeometry())
        self.ctx.tasks.wait_for_done(3000)
        super().closeEvent(e)
