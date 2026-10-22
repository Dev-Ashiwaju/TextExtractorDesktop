"""Renders the main screens offscreen to PNG files (design review / README). Usage: python scripts/screenshots.py OUTDIR"""
import os, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QCoreApplication, QSettings, QEventLoop, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from textextractor.context import AppContext, AppSettings
from textextractor.core.imaging import CropRect
from textextractor.data.database import HistoryRepository
from textextractor.ui.main_window import MainWindow
from textextractor.ui.theme import theme
from textextractor.workers import TaskManager

out = Path(sys.argv[1] if len(sys.argv) > 1 else "shots"); out.mkdir(parents=True, exist_ok=True)
QCoreApplication.setApplicationName("TextExtractorShots")
app = QApplication(sys.argv[:1]); app.setStyle("Fusion")
tmp = Path(tempfile.mkdtemp())

def wait(ms=300):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

def wait_until(cond, timeout=20000):
    t = time.time()
    while not cond() and (time.time() - t) * 1000 < timeout:
        wait(100)

# a realistic sample document
font = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s)
doc = Image.new("RGB", (1000, 760), "white"); d = ImageDraw.Draw(doc)
d.text((50, 40), "INVOICE #2024-0187", fill="#111", font=font(34))
lines = ["Thank you for your purchase. Your order will be", "shipped within three business days. Please contact",
         "support@example.com if you have any questions.", "", "Visit https://example.com/orders to track it.",
         "Call us on +234 801 234 5678 (Mon-Fri).", "", "Total due: 12,500.00 NGN"]
for i, l in enumerate(lines): d.text((50, 120 + i * 52), l, fill="#222", font=font(26))
doc_path = tmp / "invoice-scan.png"; doc.save(doc_path)

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp / "cfg"))
settings = AppSettings(QSettings(str(tmp / "s.ini"), QSettings.Format.IniFormat))
repo = HistoryRepository(tmp / "h.db")
for t, txt in [("Receipt – Grocery", "Milk 2.50\nEggs 3.20\nBread 1.80\nTotal 7.50"),
               (None, "Meeting notes: project kickoff on Monday at 10:00. Bring the signed contract and ID."),
               ("Utility bill", "Electricity bill March 2024. Amount due 18,400.00. Pay by 30 March.")]:
    i = repo.insert(txt, None); repo.rename(i, t)
repo.set_favorite(3, True)
ctx = AppContext(repo, settings, TaskManager())

for mode in ("light", "dark"):
    settings.theme = mode; theme.set_mode(mode)
    win = MainWindow(ctx, QPixmap(str(Path(__file__).resolve().parents[1] / "src/textextractor/assets/icon.png")))
    win.resize(1280, 800); win.show(); wait(400)
    win.grab().save(str(out / f"{mode}_1_home.png"))
    ep = win.extract_page
    ep.load_path(str(doc_path)); wait_until(lambda: ep.in_workspace()); wait(300)
    ep.view._set_crop(CropRect(0.03, 0.08, 0.97, 0.9))
    win.grab().save(str(out / f"{mode}_2_workspace_crop.png"))
    ep.view.reset_crop(); ep.start_extract()
    wait_until(lambda: ep.results.is_editor_visible()); wait(500)
    ep.results._find.setText("example"); wait(300)
    win.show_toast("Copied to clipboard"); wait(200)
    win.grab().save(str(out / f"{mode}_3_result.png"))
    win.select_page(win.HISTORY); wait(400); win.grab().save(str(out / f"{mode}_4_history.png"))
    win.select_page(win.SETTINGS); wait(400); win.grab().save(str(out / f"{mode}_5_settings.png"))
    win.select_page(win.PRIVACY); wait(300); win.grab().save(str(out / f"{mode}_6_privacy.png"))
    win.ctx.settings.set_geometry(None); win.close() if False else win.hide()
print("done")
