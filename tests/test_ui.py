"""End-to-end UI tests (offscreen Qt). A controllable fake OCR engine makes the edge cases deterministic."""
import threading
import time

import pytest
from PIL import Image
from PySide6.QtCore import QEventLoop, QPoint, QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from textextractor.context import AppContext, AppSettings
from textextractor.core import ocr
from textextractor.core.imaging import CropRect
from textextractor.core.models import EngineUnavailable, OcrBlock, OcrError, OcrResult
from textextractor.data.database import HistoryRepository
from textextractor.ui.capture_overlay import CaptureOverlay
from textextractor.ui.crop_view import CropView
from textextractor.ui.main_window import MainWindow
from textextractor.ui.results_panel import ResultsPanel
from textextractor.ui.theme import DARK, LIGHT, theme
from textextractor.workers import TaskManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    return app


def pump(cond, timeout=8.0):
    end = time.time() + timeout
    while not cond() and time.time() < end:
        loop = QEventLoop()
        QTimer.singleShot(20, loop.quit)
        loop.exec()
    return cond()


def settle(ms=50):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class FakeEngine(ocr.OcrEngine):
    name, label = "fake", "Fake"

    def __init__(self):
        self.calls = 0
        self.delay = 0.0
        self.sizes = []
        self.result = OcrResult("Hello\nworld\n\nSecond block", [OcrBlock("Hello\nworld"), OcrBlock("Second block")], "Fake", 0.1)
        self.error = None

    def is_available(self):
        return True

    def recognize(self, image, languages=("eng",)):
        self.calls += 1
        self.sizes.append(image.size)
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def engine(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setitem(ocr._ENGINES, "tesseract", fake)
    return fake


@pytest.fixture
def ctx(qapp, tmp_path):
    settings = AppSettings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.engine = "tesseract"
    c = AppContext(HistoryRepository(":memory:"), settings, TaskManager())
    yield c
    c.tasks.wait_for_done(3000)
    c.repo.close()


@pytest.fixture
def win(ctx):
    theme.set_mode("light")
    w = MainWindow(ctx)
    w.show()
    yield w
    w.hide()


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "doc.png"
    Image.new("RGB", (800, 400), "white").save(p)
    return p


def user_edit(panel, text):
    """Replace the editor content the way typing does (setPlainText would reset Qt's modified flag)."""
    panel._editor.selectAll()
    panel._editor.insertPlainText(text)


def open_png(win, png):
    win.extract_page.load_path(str(png))
    assert pump(win.extract_page.in_workspace)
    return win.extract_page


# ------------------------------------------------------------------ loading
def test_open_image_shows_workspace_and_enables_controls(win, png):
    page = open_png(win, png)
    assert page._extract.isEnabled() and page._rot_l.isEnabled()
    assert page._name.text() == "doc.png"
    assert page.results._stack.currentIndex() == ResultsPanel.PLACEHOLDER
    assert str(png) in win.ctx.settings.recent_files()


def test_corrupt_file_shows_message_and_stays_home(win, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image" * 20)
    win.extract_page.load_path(str(bad))
    assert pump(win.toast.isVisible)
    assert "corrupted" in win.toast._text.text() or "readable" in win.toast._text.text()
    assert not win.extract_page.in_workspace()


def test_missing_file_message(win, tmp_path):
    win.extract_page.load_path(str(tmp_path / "gone.png"))
    assert pump(win.toast.isVisible)
    assert "can't be opened" in win.toast._text.text()


def test_paste_image_from_clipboard(win, qapp):
    img = QImage(300, 120, QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.white)
    QGuiApplication.clipboard().setImage(img)
    win.extract_page.paste_from_clipboard()
    assert pump(win.extract_page.in_workspace)
    assert win.extract_page._name.text() == "Pasted image"


def test_paste_with_empty_clipboard_shows_toast(win):
    QGuiApplication.clipboard().clear()
    win.extract_page.paste_from_clipboard()
    assert win.toast.isVisible() and "no image" in win.toast._text.text().lower()


# ------------------------------------------------------------------ OCR flow
def test_extract_shows_editable_result(win, png, engine):
    page = open_png(win, png)
    page.start_extract()
    assert pump(page.results.is_editor_visible)
    assert page.results.text() == "Hello\nworld\n\nSecond block"
    assert page.results._stats.text().startswith("4 words")
    assert page._extract.isEnabled()


def test_repeated_clicks_run_ocr_once(win, png, engine):
    engine.delay = 0.4
    page = open_png(win, png)
    page.start_extract()
    page.start_extract()
    page.start_extract()
    assert not page._extract.isEnabled()
    assert pump(page.results.is_editor_visible)
    assert engine.calls == 1


def test_cancel_discards_late_result(win, png, engine):
    engine.delay = 0.3
    page = open_png(win, png)
    page.start_extract()
    page.cancel_extract()
    assert page.results._stack.currentIndex() == ResultsPanel.PLACEHOLDER
    time.sleep(0.5)
    settle(100)
    assert page.results._stack.currentIndex() == ResultsPanel.PLACEHOLDER
    assert page._extract.isEnabled()


def test_no_text_message(win, png, engine):
    engine.result = OcrResult("", [])
    page = open_png(win, png)
    page.start_extract()
    assert pump(lambda: page.results._stack.currentIndex() == ResultsPanel.MESSAGE)
    assert "No text" in page.results._msg_title.text()


def test_engine_unavailable_message_and_settings_shortcut(win, png, engine):
    engine.error = EngineUnavailable("Tesseract was not found.")
    page = open_png(win, png)
    requested = []
    page.openSettingsRequested.connect(lambda: requested.append(1))
    page.start_extract()
    assert pump(lambda: page.results._stack.currentIndex() == ResultsPanel.MESSAGE)
    assert "Tesseract was not found" in page.results._msg_detail.text()
    page.results._msg_primary_btn.click()
    assert requested


def test_ocr_error_and_unexpected_error_offer_retry(win, png, engine):
    page = open_png(win, png)
    engine.error = OcrError("Recognition failed badly.")
    page.start_extract()
    assert pump(lambda: page.results._stack.currentIndex() == ResultsPanel.MESSAGE)
    assert page.results._msg_primary_btn.text() == "Retry"
    engine.error = RuntimeError("boom with secret text")
    page.results._msg_primary_btn.click()
    assert pump(lambda: "unexpectedly" in page.results._msg_detail.text())
    assert "secret" not in page.results._msg_detail.text()   # internal errors never leak into the UI
    engine.error = None
    page.results._msg_primary_btn.click()
    assert pump(page.results.is_editor_visible)


def test_crop_is_applied_before_ocr(win, png, engine):
    page = open_png(win, png)
    page.view._set_crop(CropRect(0, 0, 0.5, 0.5))
    page.start_extract()
    assert pump(page.results.is_editor_visible)
    assert engine.sizes[-1] == (400, 200)


def test_rotate_swaps_dimensions_and_clears_selection(win, png, engine):
    page = open_png(win, png)
    page.view._set_crop(CropRect(0.1, 0.1, 0.5, 0.5))
    page.rotate(90)
    assert page._display.size == (400, 800)
    assert page.view.crop().is_full
    page.rotate(-90)
    assert page._display.size == (800, 400)
    page.rotate(90)
    page.start_extract()
    assert pump(page.results.is_editor_visible)
    assert engine.sizes[-1] == (400, 800)


def test_extract_again_with_edits_asks_before_replacing(win, png, engine, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    page = open_png(win, png)
    page.start_extract()
    assert pump(page.results.is_editor_visible)
    user_edit(page.results, "my edits")
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(1) or QMessageBox.StandardButton.No)
    page.start_extract()
    assert asked and engine.calls == 1 and page.results.text() == "my edits"


# ------------------------------------------------------------------ saving & history
def test_save_then_update_does_not_duplicate(win, png, engine):
    page = open_png(win, png)
    page.start_extract()
    assert pump(page.results.is_editor_visible)
    page.save_current()
    assert win.ctx.repo.count() == 1
    assert page.results._save.text() == "Update saved"
    assert win.ctx.repo.recent(1)[0].image_path == str(png)
    user_edit(page.results, "edited text")
    assert page.has_unsaved_changes()
    page.save_current()
    assert win.ctx.repo.count() == 1 and win.ctx.repo.recent(1)[0].text == "edited text"
    assert not page.has_unsaved_changes()


def test_empty_text_cannot_be_saved(win, png, engine):
    page = open_png(win, png)
    page.start_extract()
    assert pump(page.results.is_editor_visible)
    page.results._clear.click()
    assert not page.results._save.isEnabled()
    page.save_current()
    assert win.ctx.repo.count() == 0


def test_open_saved_entry_from_history(win, ctx):
    i = ctx.repo.insert("Saved earlier", None)
    ctx.repo.rename(i, "My note")
    win.open_entry(ctx.repo.get(i))
    page = win.extract_page
    assert page.in_workspace() and page.results.text() == "Saved earlier"
    assert page._name.text() == "My note"
    assert not page._extract.isEnabled()          # no image attached
    assert page.results._save.text() == "Update saved"


def test_history_search_favorite_delete_and_undo(win, ctx):
    a = ctx.repo.insert("Electricity bill", None)
    ctx.repo.insert("Shopping list", None)
    h = win.history_page
    h.refresh()
    assert h._badge.text() == "2 saved"
    h._search.setText("shopping")
    assert pump(lambda: h._list.count() == 2)  # one card + trailing stretch
    h._search.setText("zzz")
    assert pump(lambda: h._empty.isVisibleTo(h))
    assert "No matches" in h._empty_title.text()
    h._search.clear()
    assert pump(lambda: h._list.count() == 3)
    entry = ctx.repo.get(a)
    h._toggle_fav(entry)
    assert ctx.repo.get(a).is_favorite
    h._delete(ctx.repo.get(a))
    assert ctx.repo.get(a) is None and win.toast.isVisible()
    win.toast._on_action()                      # Undo
    assert ctx.repo.get(a).text == "Electricity bill"


def test_history_empty_state(win):
    win.history_page.refresh()
    assert win.history_page._empty.isVisibleTo(win.history_page)
    assert not win.history_page._clear_all.isEnabled()


# ------------------------------------------------------------------ results panel details
def test_find_in_text_counts_and_navigates(qapp):
    panel = ResultsPanel()
    panel.show()
    panel.show_result("Apple pie. apple tart. APPLE juice.", [OcrBlock("x")])
    panel._find.setText("apple")
    assert panel._find_count.text() == "1 of 3"
    panel._step_match(1)
    assert panel._find_count.text() == "2 of 3"
    panel._step_match(-1)
    panel._step_match(-1)
    assert panel._find_count.text() == "3 of 3"
    panel._find.setText("nothing")
    assert panel._find_count.text() == "No matches"
    assert len(panel._editor.extraSelections()) == 0


def test_links_and_blocks_tabs(qapp):
    panel = ResultsPanel()
    panel.show()
    panel.show_result("See https://example.com or mail a@b.org\n\nSecond", [OcrBlock("See https://example.com or mail a@b.org"), OcrBlock("Second")])
    settle(400)
    assert panel._tabs.isVisibleTo(panel)
    assert panel._tabs.isTabVisible(0) and panel._tabs.isTabVisible(1)
    assert "(2)" in panel._tabs.tabText(1)
    panel.show_result("plain single block", [OcrBlock("plain single block")])
    settle(400)
    assert not panel._tabs.isVisibleTo(panel)


def test_copy_all_and_copy_selection(win):
    panel = win.extract_page.results
    panel.show_result("alpha beta gamma", [])
    panel.copy_all()
    assert QGuiApplication.clipboard().text() == "alpha beta gamma"
    cur = panel._editor.textCursor()
    cur.setPosition(6)
    cur.setPosition(10, cur.MoveMode.KeepAnchor)
    panel._editor.setTextCursor(cur)
    assert panel._copy_sel.isEnabled()
    panel.copy_selection()
    assert QGuiApplication.clipboard().text() == "beta"


def test_export_txt(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    panel = win.extract_page.results
    panel.show_result("héllo ₦100", [])
    target = tmp_path / "out.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    panel.export_txt()
    assert target.read_text(encoding="utf-8") == "héllo ₦100"


# ------------------------------------------------------------------ crop view & capture overlay
def test_crop_view_drag_create_move_resize_reset(qapp):
    v = CropView()
    v.resize(640, 440)
    v.show()
    v.set_image(Image.new("RGB", (600, 400), "white"))
    got = []
    v.cropChanged.connect(got.append)
    r = v._image_rect()
    p = lambda fx, fy: QPoint(round(r.left() + fx * r.width()), round(r.top() + fy * r.height()))  # noqa: E731
    QTest.mousePress(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p(0.2, 0.2))
    QTest.mouseMove(v, p(0.6, 0.7))
    QTest.mouseRelease(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p(0.6, 0.7))
    c = v.crop()
    assert (round(c.left, 1), round(c.top, 1), round(c.right, 1), round(c.bottom, 1)) == (0.2, 0.2, 0.6, 0.7)
    assert got and not c.is_full
    # move by dragging inside
    QTest.mousePress(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p(0.4, 0.45))
    QTest.mouseMove(v, p(0.5, 0.45))
    QTest.mouseRelease(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p(0.5, 0.45))
    moved = v.crop()
    assert moved.left > c.left and round(moved.right - moved.left, 2) == round(c.right - c.left, 2)
    # resize via right edge
    QTest.mousePress(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p(moved.right, 0.45))
    QTest.mouseMove(v, p(0.95, 0.45))
    QTest.mouseRelease(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p(0.95, 0.45))
    assert v.crop().right > moved.right
    # a plain click outside clears the selection; double-click also resets
    v.reset_crop()
    assert v.crop().is_full


def test_crop_view_ignores_tiny_selection_and_outside_clicks(qapp):
    v = CropView()
    v.resize(500, 400)
    v.show()
    v.set_image(Image.new("RGB", (500, 400), "white"))
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(250, 200))
    assert v.crop().is_full
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(1, 1))  # outside the image
    assert v.crop().is_full


def test_crop_view_without_image_does_not_crash(qapp):
    v = CropView()
    v.resize(300, 300)
    v.show()
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
    v.grab()


def test_capture_overlay_returns_selected_region_with_dpr(qapp):
    shot = QPixmap(400, 200)           # physical pixels
    shot.setDevicePixelRatio(2.0)      # logical size 200x100
    shot.fill(Qt.GlobalColor.white)
    overlay = CaptureOverlay(shot, QGuiApplication.primaryScreen())
    overlay.setGeometry(0, 0, 200, 100)
    overlay.show()
    out, cancelled = [], []
    overlay.captured.connect(out.append)
    overlay.cancelled.connect(lambda: cancelled.append(1))
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 10))
    QTest.mouseMove(overlay, QPoint(120, 60))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(120, 60))
    assert len(out) == 1 and (out[0].width(), out[0].height()) == (200, 100) and not cancelled


def test_capture_overlay_escape_cancels(qapp):
    shot = QPixmap(100, 100)
    overlay = CaptureOverlay(shot, QGuiApplication.primaryScreen())
    overlay.show()
    cancelled = []
    overlay.cancelled.connect(lambda: cancelled.append(1))
    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    assert cancelled == [1]


# ------------------------------------------------------------------ theme, settings, misc
def test_theme_switch_updates_palette_and_stylesheet(qapp):
    theme.set_mode("dark")
    assert theme.palette is DARK and DARK.bg.lower() in qapp.styleSheet().lower()
    theme.set_mode("light")
    assert theme.palette is LIGHT and LIGHT.bg.lower() in qapp.styleSheet().lower()
    theme.set_mode("bogus")
    assert theme.mode == "system"
    theme.set_mode("light")


def test_settings_roundtrip_and_validation(tmp_path):
    q = QSettings(str(tmp_path / "x.ini"), QSettings.Format.IniFormat)
    s = AppSettings(q)
    assert (s.theme, s.engine, s.language, s.auto_clear_days) == ("system", "auto", "eng", 0)
    s.theme, s.engine, s.language, s.auto_clear_days = "dark", "rapidocr", "fra", 30
    s2 = AppSettings(QSettings(str(tmp_path / "x.ini"), QSettings.Format.IniFormat))
    assert (s2.theme, s2.engine, s2.language, s2.auto_clear_days) == ("dark", "rapidocr", "fra", 30)
    q.setValue("theme", "neon")
    q.setValue("auto_clear_days", "not-a-number")
    assert s.theme == "system" and s.auto_clear_days == 0


def test_recent_files_are_deduplicated_limited_and_pruned(tmp_path):
    s = AppSettings(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    files = []
    for i in range(8):
        f = tmp_path / f"{i}.png"
        f.write_bytes(b"x")
        files.append(str(f))
        s.add_recent(str(f))
    s.add_recent(files[5])
    assert s.recent_files()[0] == files[5] and len(s.recent_files()) == 6
    (tmp_path / "5.png").unlink()
    assert files[5] not in s.existing_recent_files()


def test_settings_page_changes_persist_and_apply(win, ctx):
    page = win.settings_page
    page._theme_buttons["dark"].setChecked(True)
    assert ctx.settings.theme == "dark" and theme.palette is DARK
    page._theme_buttons["light"].setChecked(True)
    page._clear_buttons[30].setChecked(True)
    assert ctx.settings.auto_clear_days == 30
    page._engine.setCurrentIndex(page._engine.findData("rapidocr"))
    assert ctx.settings.engine == "rapidocr"


def test_auto_clear_setting_deletes_old_entries(win, ctx):
    old = ctx.repo.insert("old", None)
    ctx.repo.set_favorite(ctx.repo.insert("old fav", None), True)
    ctx._now = None
    # age the plain entry beyond the threshold
    ctx.repo._db.execute("UPDATE history SET created_at = created_at - ?", (40 * 86400,))
    ctx.repo._db.commit()
    win.settings_page._clear_buttons[30].setChecked(True)
    assert ctx.repo.get(old) is None and ctx.repo.count() == 1


def test_main_window_droppable_detection(win, png):
    from PySide6.QtCore import QMimeData, QUrl
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(png))])
    assert win._droppable(md)
    md2 = QMimeData()
    md2.setUrls([QUrl.fromLocalFile("/tmp/notes.txt")])
    assert not win._droppable(md2)
    assert not win._droppable(QMimeData())


def test_navigation_between_pages(win):
    for i, nav in enumerate(win._nav):
        nav.click()
        assert win.pages.currentIndex() == i and nav.isChecked()


def test_toast_shows_action_and_autohides(win):
    fired = []
    win.show_toast("Hello", "Undo", lambda: fired.append(1), timeout_ms=100)
    assert win.toast.isVisible() and win.toast._action.isVisible()
    assert pump(lambda: not win.toast.isVisible(), 2)
    win.show_toast("Again", "Undo", lambda: fired.append(1))
    win.toast._on_action()
    assert fired == [1]


# ------------------------------------------------------------------ workers
def test_task_callbacks_run_on_ui_thread_and_cancel_drops_result(qapp):
    tm = TaskManager()
    seen = {}
    tm.submit(lambda: threading.current_thread().name, lambda r: seen.update(worker=r, ui=threading.current_thread().name))
    assert pump(lambda: "worker" in seen)
    assert seen["ui"] == threading.main_thread().name and seen["worker"] != seen["ui"]
    dropped = []
    tid = tm.submit(lambda: time.sleep(0.2), lambda r: dropped.append(1))
    tm.cancel(tid)
    tm.wait_for_done(2000)
    settle(100)
    assert dropped == []
    errors = []
    tm.submit(lambda: 1 / 0, lambda r: None, errors.append)
    assert pump(lambda: errors)
    assert isinstance(errors[0], ZeroDivisionError)


def test_selftest_passes():
    from textextractor import selftest
    if not ocr.TesseractEngine().is_available() and not ocr.RapidOcrEngine().is_available():
        pytest.skip("no OCR engine installed")
    assert selftest.run() == 0
