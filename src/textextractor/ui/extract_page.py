"""The main page: home (drop zone, recents) and the workspace (image + crop on the left, results on the right)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QMessageBox, QPushButton, QScrollArea, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget)

from ..context import AppContext
from ..core import imaging
from ..core.imaging import CropRect, ImageLoadError, load_image
from ..core.models import EngineUnavailable, OcrError
from ..core.ocr import resolve_engine
from ..data.database import HistoryEntry
from .capture_overlay import CaptureOverlay
from .crop_view import CropView
from .qt_images import qpixmap_to_png_bytes
from .results_panel import ResultsPanel
from .history_page import HistoryCard
from .widgets import IconLabel, ThemedButton, clear_layout, make_card, make_label

log = logging.getLogger(__name__)
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff);;All files (*)"
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_EXTS


class ExtractPage(QWidget):
    historyChanged = Signal()
    openSettingsRequested = Signal()
    openHistoryEntryRequested = Signal(object)
    HOME, WORKSPACE = 0, 1

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self._base: Image.Image | None = None
        self._display: Image.Image | None = None
        self._rotation = 0
        self._source_path: str | None = None
        self._saved_id: int | None = None
        self._extracting = False
        self._load_task: int | None = None
        self._loading = False
        self._ocr_task: int | None = None
        self._overlay: CaptureOverlay | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        root.addWidget(self._stack)
        self._stack.addWidget(self._build_home())
        self._stack.addWidget(self._build_workspace())
        self.refresh_home()

    # ================================================================== home
    def _build_home(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("page")
        outer = QHBoxLayout(host)
        outer.setContentsMargins(32, 28, 32, 28)
        col_host = QWidget()
        col_host.setMaximumWidth(900)
        col = QVBoxLayout(col_host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(18)
        outer.addStretch(1)
        outer.addWidget(col_host, 100)
        outer.addStretch(1)

        col.addWidget(make_label("Extract text from any image", "h1"))
        col.addWidget(make_label("Screenshots, photos and scans are recognized on your computer — nothing is uploaded.",
                                 "muted", wrap=True))

        self._dropzone = QFrame()
        self._dropzone.setObjectName("dropzone")
        dz = QVBoxLayout(self._dropzone)
        dz.setContentsMargins(24, 36, 24, 32)
        dz.setSpacing(8)
        dz.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.addWidget(IconLabel("image", 44, "accent"), 0, Qt.AlignmentFlag.AlignCenter)
        t = make_label("Drop an image here", "h2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.addWidget(t)
        s = make_label("PNG, JPEG, WebP, BMP, GIF or TIFF · or paste a screenshot with Ctrl+V", "muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.addWidget(s)
        dz.addSpacing(10)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.open_btn = ThemedButton("Open image", "folder", "primary")
        self.capture_btn = ThemedButton("Capture screen", "scan", "secondary")
        self.paste_btn = ThemedButton("Paste from clipboard", "paste", "secondary")
        self.open_btn.clicked.connect(self.open_file_dialog)
        self.capture_btn.clicked.connect(self.capture_screen)
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        for b in (self.open_btn, self.capture_btn, self.paste_btn):
            b.setMinimumHeight(40)
            btns.addWidget(b)
        dz.addLayout(btns)
        col.addWidget(self._dropzone)

        self._recent_images_title = make_label("Recent images", "h2")
        col.addWidget(self._recent_images_title)
        self._recent_images_row = QHBoxLayout()
        self._recent_images_row.setSpacing(10)
        self._recent_images_host = QWidget()
        self._recent_images_host.setLayout(self._recent_images_row)
        col.addWidget(self._recent_images_host)

        self._recent_title = make_label("Recent extractions", "h2")
        col.addWidget(self._recent_title)
        self._recent_list = QVBoxLayout()
        self._recent_list.setSpacing(8)
        self._recent_host = QWidget()
        self._recent_host.setLayout(self._recent_list)
        col.addWidget(self._recent_host)
        self._recent_empty = make_label("Nothing saved yet. Extract some text and click Save to keep it here.", "muted", wrap=True)
        col.addWidget(self._recent_empty)
        col.addStretch(1)
        scroll.setWidget(host)
        return scroll

    def set_drop_active(self, active: bool) -> None:
        self._dropzone.setProperty("active", active)
        self._dropzone.style().unpolish(self._dropzone)
        self._dropzone.style().polish(self._dropzone)

    def refresh_home(self) -> None:
        # recent images (thumbnails of files that still exist)
        clear_layout(self._recent_images_row)
        shown = 0
        for path in self.ctx.settings.existing_recent_files():
            pm = self._thumbnail(path)
            btn = QPushButton()
            btn.setProperty("variant", "icon")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(96, 96)
            btn.setIconSize(QSize(88, 88))
            if pm is not None:
                btn.setIcon(QIcon(pm))
            else:
                btn.setText(Path(path).suffix.upper())
            btn.setToolTip(Path(path).name)
            btn.clicked.connect(lambda _=False, p=path: self.load_path(p))
            self._recent_images_row.addWidget(btn)
            shown += 1
        self._recent_images_row.addStretch(1)
        self._recent_images_title.setVisible(shown > 0)
        self._recent_images_host.setVisible(shown > 0)

        # recent extractions
        clear_layout(self._recent_list)
        entries = self.ctx.repo.recent(4)
        for e in entries:
            card = HistoryCard(e, compact=True)
            card.clicked.connect(lambda _=None, entry=e: self.openHistoryEntryRequested.emit(entry))
            self._recent_list.addWidget(card)
        self._recent_host.setVisible(bool(entries))
        self._recent_empty.setVisible(not entries)

    @staticmethod
    def _thumbnail(path: str) -> QPixmap | None:
        try:
            if Path(path).stat().st_size > 30_000_000:
                return None
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if not size.isValid():
                return None
            scaled = size.scaled(176, 176, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            reader.setScaledSize(scaled)
            img = reader.read()
            if img.isNull():
                return None
            return QPixmap.fromImage(img)
        except OSError:
            return None

    # ================================================================== workspace
    def _build_workspace(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._back = ThemedButton("New image", "arrow-left", "ghost")
        self._back.clicked.connect(self.new_image)
        self._name = make_label("", "h2")
        self._rot_l = ThemedButton("", "rotate-ccw", "icon", 20)
        self._rot_r = ThemedButton("", "rotate-cw", "icon", 20)
        self._rot_l.setToolTip("Rotate left")
        self._rot_r.setToolTip("Rotate right")
        self._rot_l.clicked.connect(lambda: self.rotate(-90))
        self._rot_r.clicked.connect(lambda: self.rotate(90))
        self._reset_crop = ThemedButton("Reset selection", "crop", "ghost")
        self._reset_crop.setToolTip("Clear the selected area (or double-click the image)")
        self._reset_crop.clicked.connect(lambda: self.view.reset_crop())
        self._extract = ThemedButton("Extract text", "text", "primary")
        self._extract.setMinimumHeight(38)
        self._extract.setToolTip("Ctrl+Enter")
        self._extract.clicked.connect(self.start_extract)
        bar.addWidget(self._back)
        bar.addWidget(self._name, 1)
        bar.addWidget(self._rot_l)
        bar.addWidget(self._rot_r)
        bar.addWidget(self._reset_crop)
        bar.addSpacing(8)
        bar.addWidget(self._extract)
        lay.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(14)
        self.view = CropView()
        self.view.cropChanged.connect(lambda _c: self._update_controls())
        split.addWidget(self.view)
        card = make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 14)
        self.results = ResultsPanel()
        self.results.saveRequested.connect(self.save_current)
        self.results.extractAgainRequested.connect(self.start_extract)
        self.results.cancelRequested.connect(self.cancel_extract)
        cl.addWidget(self.results)
        card.setMinimumWidth(420)
        split.addWidget(card)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 6)
        lay.addWidget(split, 1)
        self._update_controls()
        return page

    def _update_controls(self) -> None:
        has_img = self._display is not None
        idle = has_img and not self._extracting
        self._rot_l.setEnabled(idle)
        self._rot_r.setEnabled(idle)
        self._extract.setEnabled(idle)
        self._reset_crop.setEnabled(idle and not self.view.crop().is_full)

    # ================================================================== loading images
    def open_file_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        start = str(Path.home() / "Pictures") if (Path.home() / "Pictures").is_dir() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Open image", start, IMAGE_FILTER)
        if path:
            self.load_path(path)

    def load_path(self, path: str) -> None:
        self._begin_load(path, Path(path).name, path)

    def load_bytes(self, data: bytes, name: str) -> None:
        self._begin_load(data, name, None)

    def paste_from_clipboard(self) -> None:
        md = QGuiApplication.clipboard().mimeData()
        if md is not None and md.hasImage():
            img = QGuiApplication.clipboard().image()
            if not img.isNull():
                from .qt_images import qimage_to_png_bytes
                self.load_bytes(qimage_to_png_bytes(img), "Pasted image")
                return
        if md is not None and md.hasUrls():
            for url in md.urls():
                if url.isLocalFile() and is_image_path(url.toLocalFile()):
                    self.load_path(url.toLocalFile())
                    return
        self._toast("There is no image on the clipboard")

    def _begin_load(self, source, name: str, path: str | None, keep_text: bool = False) -> None:
        if not self._confirm_discard():
            return
        self._cancel_load()
        self._cancel_ocr_silently()
        self._loading = True
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        self._load_task = self.ctx.tasks.submit(
            lambda: load_image(source),
            lambda img: self._on_loaded(img, name, path, keep_text),
            lambda err: self._on_load_failed(err),
        )

    def _cancel_load(self) -> None:
        self.ctx.tasks.cancel(self._load_task)
        self._load_task = None
        if self._loading:
            self._loading = False
            QApplication.restoreOverrideCursor()

    def _on_loaded(self, img: Image.Image, name: str, path: str | None, keep_text: bool) -> None:
        self._loading = False
        QApplication.restoreOverrideCursor()
        self._base = self._display = img
        self._rotation = 0
        self._source_path = path
        self._name.setText(name)
        self.view.set_image(img)
        if not keep_text:
            self._saved_id = None
            self.results.show_placeholder()
        if path:
            self.ctx.settings.add_recent(path)
        self._stack.setCurrentIndex(self.WORKSPACE)
        self._update_controls()

    def _on_load_failed(self, err: BaseException) -> None:
        self._loading = False
        QApplication.restoreOverrideCursor()
        if isinstance(err, ImageLoadError):
            self._toast(err.user_message)
        else:
            log.error("unexpected load failure: %s", type(err).__name__)
            self._toast("This image couldn't be opened.")

    # ================================================================== transforms
    def rotate(self, degrees: int) -> None:
        if self._base is None or self._extracting:
            return
        self._rotation = (self._rotation + degrees) % 360
        self._display = imaging.rotate(self._base, self._rotation)
        self.view.set_image(self._display)  # also clears the selection (it refers to the old orientation)
        self._update_controls()

    # ================================================================== OCR
    def start_extract(self) -> None:
        if self._display is None or self._extracting:
            return
        if self.results.is_editor_visible() and self.results.is_modified():
            answer = QMessageBox.question(self, "Replace your edits?",
                                          "Extracting again will replace the text you have edited. Continue?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        engine = resolve_engine(self.ctx.settings.engine)
        languages = [self.ctx.settings.language]
        image = imaging.crop(self._display, self.view.crop())
        self._extracting = True
        self._update_controls()
        self.results.show_running(f"Recognizing text with {engine.label}…")
        self._ocr_task = self.ctx.tasks.submit(lambda: engine.recognize(image, languages),
                                               self._on_ocr_done, self._on_ocr_failed)

    def cancel_extract(self) -> None:
        self._cancel_ocr_silently()
        self.results.show_placeholder()

    def _cancel_ocr_silently(self) -> None:
        self.ctx.tasks.cancel(self._ocr_task)
        self._ocr_task = None
        if self._extracting:
            self._extracting = False
            self._update_controls()

    def _on_ocr_done(self, result) -> None:
        self._extracting = False
        self._saved_id = None
        self._update_controls()
        if result.is_empty:
            self.results.show_message(
                "No text was detected in this image",
                "Try selecting the area with text, rotating the image, or using a sharper, better-lit picture.",
                "Try again", self.start_extract, "Dismiss", self.results.show_placeholder)
        else:
            self.results.show_result(result.text, result.blocks, result.engine, result.elapsed, saved=False)

    def _on_ocr_failed(self, err: BaseException) -> None:
        self._extracting = False
        self._update_controls()
        if isinstance(err, EngineUnavailable):
            self.results.show_message("Text recognition isn't set up yet", str(err), "Open settings",
                                      self.openSettingsRequested.emit)
        elif isinstance(err, OcrError):
            self.results.show_message("Recognition failed", str(err), "Retry", self.start_extract)
        else:
            log.error("unexpected OCR failure: %s", type(err).__name__)
            self.results.show_message("Something went wrong", "Text recognition failed unexpectedly. Please try again.",
                                      "Retry", self.start_extract)

    # ================================================================== history
    def save_current(self) -> None:
        text = self.results.text()
        if not text.strip():
            self._toast("There is no text to save")
            return
        try:
            if self._saved_id is None:
                self._saved_id = self.ctx.repo.insert(text, self._source_path)
            else:
                self.ctx.repo.update_text(self._saved_id, text)
        except sqlite3.Error:
            log.exception("saving history failed")
            self._toast("Couldn't save. Please try again.")
            return
        self.results.set_saved(True)
        self.results.mark_clean()
        self._toast("Saved to history")
        self.historyChanged.emit()

    def open_saved(self, entry: HistoryEntry) -> None:
        if not self._confirm_discard():
            return
        self._cancel_load()
        self._cancel_ocr_silently()
        self._base = self._display = None
        self._rotation = 0
        self._source_path = entry.image_path
        self._saved_id = entry.id
        self._name.setText(entry.display_title())
        self.view.set_placeholder("Opened from history")
        self.results.show_result(entry.text, [], "", 0.0, saved=True)
        self._stack.setCurrentIndex(self.WORKSPACE)
        self._update_controls()
        if entry.image_path and Path(entry.image_path).is_file():  # best effort: bring the image back
            self._load_task = self.ctx.tasks.submit(
                lambda: load_image(entry.image_path),
                lambda img: self._attach_image(img),
                lambda _e: None)

    def _attach_image(self, img: Image.Image) -> None:
        if self._saved_id is None or self._base is not None:
            return
        self._base = self._display = img
        self.view.set_image(img)
        self._update_controls()

    # ================================================================== navigation & misc
    def new_image(self) -> None:
        if not self._confirm_discard():
            return
        self._cancel_ocr_silently()
        self._cancel_load()
        self._base = self._display = None
        self._saved_id = None
        self.results.show_placeholder()
        self.refresh_home()
        self._stack.setCurrentIndex(self.HOME)

    def has_unsaved_changes(self) -> bool:
        return self._stack.currentIndex() == self.WORKSPACE and self.results.is_editor_visible() \
            and self.results.is_modified()

    def _confirm_discard(self) -> bool:
        if not self.has_unsaved_changes():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Discard your edits?")
        box.setText("You have edited the extracted text without saving it.")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is save:
            self.save_current()
            return not self.has_unsaved_changes()
        return box.clickedButton() is discard

    def in_workspace(self) -> bool:
        return self._stack.currentIndex() == self.WORKSPACE

    def _toast(self, msg: str) -> None:
        w = self.window()
        if hasattr(w, "show_toast"):
            w.show_toast(msg)

    # ================================================================== screen capture
    def capture_screen(self) -> None:
        win = self.window()
        screen = win.screen() or QGuiApplication.primaryScreen()
        win.hide()
        QTimer.singleShot(350, lambda: self._grab(win, screen))

    def _grab(self, win: QWidget, screen) -> None:
        pm = screen.grabWindow(0)
        if pm.isNull():
            self._restore(win)
            self._toast("Screen capture isn't available here (on macOS allow Screen Recording; on Wayland use Paste)")
            return
        self._overlay = CaptureOverlay(pm, screen)
        self._overlay.captured.connect(lambda p: self._capture_done(win, p))
        self._overlay.cancelled.connect(lambda: self._restore(win))
        self._overlay.start()

    def _capture_done(self, win: QWidget, pixmap: QPixmap) -> None:
        self._restore(win)
        self.load_bytes(qpixmap_to_png_bytes(pixmap), "Screen capture")

    @staticmethod
    def _restore(win: QWidget) -> None:
        win.show()
        win.raise_()
        win.activateWindow()
