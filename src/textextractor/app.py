"""Application entry point."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from . import APP_NAME, ORG_NAME, __version__


def _setup_logging(directory: Path) -> None:
    handler = logging.handlers.RotatingFileHandler(directory / "textextractor.log", maxBytes=512_000, backupCount=2,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)  # NOTE: never log image contents or recognized text


def asset_path(name: str) -> Path:
    here = Path(__file__).resolve().parent / "assets" / name
    if here.exists():
        return here
    from .core.ocr import app_root
    return app_root() / "textextractor" / "assets" / name


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(f"{APP_NAME} {__version__}")
        return 0
    if "--selftest" in argv:
        from .selftest import run
        return run()

    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QApplication

    from .context import AppContext, AppSettings, data_dir
    from .data.database import HistoryRepository
    from .ui.main_window import MainWindow
    from .ui.theme import theme
    from .workers import TaskManager

    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationVersion(__version__)
    app = QApplication(argv)
    app.setStyle("Fusion")  # consistent base for our palette/QSS on every OS
    icon_file = asset_path("icon.png")
    logo = QPixmap(str(icon_file)) if icon_file.exists() else None
    if logo is not None and not logo.isNull():
        app.setWindowIcon(QIcon(logo))

    folder = data_dir()
    _setup_logging(folder)
    settings = AppSettings()
    repo = HistoryRepository(folder / "history.db")
    ctx = AppContext(repo=repo, settings=settings, tasks=TaskManager())

    theme.set_mode(settings.theme)
    app.styleHints().colorSchemeChanged.connect(lambda *_: theme.refresh() if theme.mode == "system" else None)

    if settings.auto_clear_days > 0:
        try:
            repo.delete_older_than_days(settings.auto_clear_days)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("auto-clear failed")

    window = MainWindow(ctx, logo)
    window.show()
    for arg in argv[1:]:
        if not arg.startswith("-") and Path(arg).is_file():
            window.open_path(arg)
            break

    # Pre-load the fallback engine's model in the background so the first extraction is fast.
    from .core.ocr import resolve_engine
    engine = resolve_engine(settings.engine)
    if hasattr(engine, "warm_up") and engine.is_available():
        ctx.tasks.submit(engine.warm_up, lambda _r: None, lambda _e: None)

    code = app.exec()
    repo.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
