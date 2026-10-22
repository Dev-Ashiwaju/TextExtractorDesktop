"""Settings: appearance, recognition engine/language, history retention, about."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QHBoxLayout, QMessageBox, QRadioButton, QScrollArea,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..context import AppContext, data_dir
from ..core.ocr import get_engine
from .theme import theme
from .widgets import ThemedButton, make_card, make_label

LANG_NAMES = {
    "eng": "English", "fra": "French", "deu": "German", "spa": "Spanish", "por": "Portuguese", "ita": "Italian",
    "nld": "Dutch", "rus": "Russian", "ara": "Arabic", "hin": "Hindi", "jpn": "Japanese", "kor": "Korean",
    "chi_sim": "Chinese (Simplified)", "chi_tra": "Chinese (Traditional)", "tur": "Turkish", "pol": "Polish",
    "swe": "Swedish", "ukr": "Ukrainian", "vie": "Vietnamese", "ind": "Indonesian",
}


def _section(title: str, subtitle: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    card = make_card()
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(8)
    lay.addWidget(make_label(title, "h2"))
    if subtitle:
        lay.addWidget(make_label(subtitle, "muted", wrap=True))
    return card, lay


class SettingsPage(QWidget):
    historyCleared = Signal()
    themeChanged = Signal(str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.addWidget(make_label("Settings", "h1"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("page")
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 10, 8, 10)
        col.setSpacing(14)
        host.setMaximumWidth(760)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        # appearance --------------------------------------------------------
        card, lay = _section("Appearance")
        self._theme_group = QButtonGroup(self)
        self._theme_buttons: dict[str, QRadioButton] = {}
        for key, label in (("system", "Follow system"), ("light", "Light"), ("dark", "Dark")):
            rb = QRadioButton(label)
            self._theme_group.addButton(rb)
            self._theme_buttons[key] = rb
            rb.toggled.connect(lambda checked, k=key: checked and self._set_theme(k))
            lay.addWidget(rb)
        col.addWidget(card)

        # recognition -------------------------------------------------------
        card, lay = _section("Text recognition",
                             "Recognition runs entirely on this computer. Tesseract gives the best accuracy for printed "
                             "text; RapidOCR is a pip-only fallback.")
        row = QHBoxLayout()
        row.addWidget(make_label("Engine", "h3"))
        row.addStretch(1)
        self._engine = QComboBox()
        self._engine.addItem("Automatic (recommended)", "auto")
        self._engine.addItem("Tesseract", "tesseract")
        self._engine.addItem("RapidOCR", "rapidocr")
        self._engine.currentIndexChanged.connect(self._on_engine)
        row.addWidget(self._engine)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(make_label("Language (Tesseract)", "h3"))
        row.addStretch(1)
        self._language = QComboBox()
        self._language.currentIndexChanged.connect(self._on_language)
        row.addWidget(self._language)
        lay.addLayout(row)
        self._status = make_label("", "small", wrap=True)
        lay.addWidget(self._status)
        col.addWidget(card)

        # history -----------------------------------------------------------
        card, lay = _section("History", "Saved text is stored only on this computer. Favorites are never auto-deleted.")
        self._clear_group = QButtonGroup(self)
        self._clear_buttons: dict[int, QRadioButton] = {}
        for days, label in ((0, "Keep until I delete it"), (7, "Delete after 7 days"),
                            (30, "Delete after 30 days"), (90, "Delete after 90 days")):
            rb = QRadioButton(label)
            self._clear_group.addButton(rb)
            self._clear_buttons[days] = rb
            rb.toggled.connect(lambda checked, d=days: checked and self._set_auto_clear(d))
            lay.addWidget(rb)
        clear = ThemedButton("Clear all history now", "trash", "danger")
        clear.clicked.connect(self._clear_history)
        lay.addWidget(clear, 0, Qt.AlignmentFlag.AlignLeft)
        col.addWidget(card)

        # about -------------------------------------------------------------
        card, lay = _section(APP_NAME)
        lay.addWidget(make_label(f"Version {__version__}", "muted"))
        folder = ThemedButton("Open data folder", "folder", "secondary")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        lay.addWidget(folder, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(make_label("Open-source components: Qt/PySide6 (LGPL), Pillow (HPND), Tesseract (Apache-2.0), "
                                 "RapidOCR (Apache-2.0). See THIRD_PARTY_NOTICES.md.", "small", wrap=True))
        col.addWidget(card)
        col.addStretch(1)
        self.load()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self._refresh_engine_info()

    # ------------------------------------------------------------------
    def load(self) -> None:
        s = self.ctx.settings
        self._theme_buttons[s.theme].setChecked(True)
        self._clear_buttons[s.auto_clear_days].setChecked(True)
        idx = self._engine.findData(s.engine)
        self._engine.blockSignals(True)
        self._engine.setCurrentIndex(max(0, idx))
        self._engine.blockSignals(False)
        self._refresh_engine_info()

    def _refresh_engine_info(self) -> None:
        tess, rapid = get_engine("tesseract"), get_engine("rapidocr")
        langs = tess.languages() if tess.is_available() else ["eng"]
        self._language.blockSignals(True)
        self._language.clear()
        for code in langs:
            self._language.addItem(f"{LANG_NAMES.get(code, code)} ({code})", code)
        i = self._language.findData(self.ctx.settings.language)
        self._language.setCurrentIndex(max(0, i))
        self._language.blockSignals(False)
        self._language.setEnabled(tess.is_available())
        lines = []
        lines.append(f"✓ Tesseract found: {tess.executable}" if tess.is_available() else f"✗ {tess.unavailable_hint()}")
        lines.append("✓ RapidOCR installed" if rapid.is_available() else f"✗ {rapid.unavailable_hint()}")
        self._status.setText("\n".join(lines))

    def _set_theme(self, key: str) -> None:
        self.ctx.settings.theme = key
        self.themeChanged.emit(key)

    def _on_engine(self, _i: int) -> None:
        self.ctx.settings.engine = self._engine.currentData()

    def _on_language(self, _i: int) -> None:
        code = self._language.currentData()
        if code:
            self.ctx.settings.language = code

    def _set_auto_clear(self, days: int) -> None:
        self.ctx.settings.auto_clear_days = days
        if days > 0:
            removed = self.ctx.repo.delete_older_than_days(days)
            if removed:
                self.historyCleared.emit()

    def _clear_history(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Clear all history?")
        box.setText("This permanently deletes every saved extraction, including favorites.")
        yes = box.addButton("Delete all", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.ctx.repo.clear_all()
            self.historyCleared.emit()
            w = self.window()
            if hasattr(w, "show_toast"):
                w.show_toast("History cleared")
