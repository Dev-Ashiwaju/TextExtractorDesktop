"""`python -m textextractor --selftest` – headless smoke test used to verify an installed/frozen build:
real OCR on a generated image + constructing and rendering the whole UI offscreen."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def run() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image, ImageDraw, ImageFont

    from .core.ocr import resolve_engine

    img = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(img).text((30, 60), "Self test 12345", fill="black", font=ImageFont.load_default(size=56))
    engine = resolve_engine("auto")
    if not engine.is_available():
        print("FAIL: no OCR engine available:", engine.unavailable_hint())
        return 2
    text = engine.recognize(img).text
    if "12345" not in text.replace(" ", ""):
        print(f"FAIL: OCR returned unexpected text from {engine.label}")
        return 3
    print(f"OK  ocr engine={engine.label}")

    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    from .context import AppContext, AppSettings
    from .data.database import HistoryRepository
    from .ui.main_window import MainWindow
    from .ui.theme import theme
    from .workers import TaskManager

    QCoreApplication.setApplicationName("TextExtractorSelfTest")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    with tempfile.TemporaryDirectory() as tmp:
        ctx = AppContext(HistoryRepository(Path(tmp) / "h.db"), AppSettings(), TaskManager())
        theme.set_mode("light")
        win = MainWindow(ctx)
        win.show()
        app.processEvents()
        pix = win.grab()
        ok = not pix.isNull() and pix.width() > 400
        ctx.repo.close()
    print("OK  ui rendered" if ok else "FAIL ui")
    return 0 if ok else 4
