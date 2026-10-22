"""Design tokens, light/dark palettes, global stylesheet and the ThemeManager."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    surface: str
    surface_alt: str
    sidebar: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    on_accent: str
    accent_soft: str
    accent_soft_text: str
    danger: str
    danger_soft: str
    success: str
    highlight: str
    highlight_current: str
    scrim: str


LIGHT = Palette(
    name="light", bg="#F5F6FA", surface="#FFFFFF", surface_alt="#F0F2F7", sidebar="#FFFFFF", border="#E3E6EE",
    text="#141824", muted="#667085", accent="#4F46E5", accent_hover="#4338CA", accent_pressed="#3730A3",
    on_accent="#FFFFFF", accent_soft="#EEF0FF", accent_soft_text="#3F37C9", danger="#D92D20", danger_soft="#FEF3F2",
    success="#12805C", highlight="#FFE69A", highlight_current="#FFB020", scrim="#0B1020",
)
DARK = Palette(
    name="dark", bg="#0E1015", surface="#171A22", surface_alt="#1E222C", sidebar="#12151C", border="#2A2F3B",
    text="#E7E9EF", muted="#9AA3B5", accent="#818CF8", accent_hover="#9AA3FF", accent_pressed="#6D78E8",
    on_accent="#0B0E1F", accent_soft="#232852", accent_soft_text="#B7BEFF", danger="#F97066", danger_soft="#3A1A18",
    success="#4ADE9A", highlight="#5C4B10", highlight_current="#B7791F", scrim="#000000",
)


class ThemeManager(QObject):
    """mode: 'system' | 'light' | 'dark'. Emits changed(Palette) whenever the effective palette changes."""
    changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._mode = "system"
        self._palette = LIGHT

    @property
    def palette(self) -> Palette:
        return self._palette

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in ("system", "light", "dark") else "system"
        self.refresh()

    def refresh(self) -> None:
        if self._mode == "system":
            hints = QGuiApplication.styleHints()
            dark = hints.colorScheme() == Qt.ColorScheme.Dark
        else:
            dark = self._mode == "dark"
        new = DARK if dark else LIGHT
        self._palette = new
        self.apply()
        self.changed.emit(new)

    def apply(self) -> None:
        app = QGuiApplication.instance()
        if app is None:
            return
        p = self._palette
        qp = QPalette()
        roles = {
            QPalette.ColorRole.Window: p.bg, QPalette.ColorRole.WindowText: p.text,
            QPalette.ColorRole.Base: p.surface, QPalette.ColorRole.AlternateBase: p.surface_alt,
            QPalette.ColorRole.Text: p.text, QPalette.ColorRole.Button: p.surface,
            QPalette.ColorRole.ButtonText: p.text, QPalette.ColorRole.ToolTipBase: p.surface,
            QPalette.ColorRole.ToolTipText: p.text, QPalette.ColorRole.Highlight: p.accent,
            QPalette.ColorRole.HighlightedText: p.on_accent, QPalette.ColorRole.PlaceholderText: p.muted,
            QPalette.ColorRole.Link: p.accent,
        }
        for role, color in roles.items():
            qp.setColor(role, QColor(color))
        qp.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(p.muted))
        qp.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(p.muted))
        app.setPalette(qp)
        app.setStyleSheet(build_qss(p, _arrow_image(p.muted)))


theme = ThemeManager()


def _arrow_image(color: str) -> str:
    """QSS can only reference images by file, so render the combo-box chevron to a small temp PNG."""
    from . import icons
    folder = Path(tempfile.gettempdir()) / "textextractor-ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"chevron-{color.lstrip('#')}.png"
    if not path.exists():
        icons.pixmap("chevron-down", color, 14).save(str(path), "PNG")
    return path.as_posix()


def build_qss(p: Palette, arrow: str = "") -> str:
    return f"""
* {{ font-size: 13px; }}
QWidget {{ color: {p.text}; }}
QWidget#page, QStackedWidget#pages {{ background: {p.bg}; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 8px; border-radius: 6px; }}

QFrame#sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
QFrame#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; }}
QFrame#cardFlat {{ background: {p.surface_alt}; border: none; border-radius: 12px; }}
QFrame#dropzone {{ background: {p.surface}; border: 2px dashed {p.border}; border-radius: 18px; }}
QFrame#dropzone[active="true"] {{ border-color: {p.accent}; background: {p.accent_soft}; }}
QFrame#toast {{ background: {p.text}; border-radius: 10px; }}
QLabel#toastText {{ color: {p.bg}; font-weight: 500; background: transparent; }}

QLabel {{ background: transparent; }}
QLabel[role="h1"] {{ font-size: 24px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: 16px; font-weight: 650; }}
QLabel[role="h3"] {{ font-size: 13px; font-weight: 650; }}
QLabel[role="muted"] {{ color: {p.muted}; }}
QLabel[role="small"] {{ color: {p.muted}; font-size: 12px; }}
QLabel[role="appname"] {{ font-size: 15px; font-weight: 700; }}
QLabel[role="badge"] {{ background: {p.accent_soft}; color: {p.accent_soft_text}; border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
QLabel[role="error"] {{ color: {p.danger}; }}

QPushButton {{ border-radius: 9px; padding: 8px 14px; font-weight: 600; border: 1px solid {p.border}; background: {p.surface}; }}
QPushButton:hover {{ background: {p.surface_alt}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:focus {{ border: 1px solid {p.accent}; }}
QPushButton:disabled {{ color: {p.muted}; background: {p.surface_alt}; border-color: {p.surface_alt}; }}
QPushButton[variant="primary"] {{ background: {p.accent}; color: {p.on_accent}; border: 1px solid {p.accent}; }}
QPushButton[variant="primary"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {p.accent_pressed}; }}
QPushButton[variant="primary"]:disabled {{ background: {p.surface_alt}; color: {p.muted}; border-color: {p.surface_alt}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[variant="ghost"]:hover {{ background: {p.surface_alt}; }}
QPushButton[variant="danger"] {{ color: {p.danger}; }}
QPushButton[variant="danger"]:hover {{ background: {p.danger_soft}; border-color: {p.danger_soft}; }}
QPushButton[variant="chip"] {{ background: {p.accent_soft}; color: {p.accent_soft_text}; border: none; border-radius: 14px; padding: 5px 12px; font-weight: 500; }}
QPushButton[variant="chip"]:hover {{ background: {p.border}; }}
QPushButton[variant="nav"] {{ background: transparent; border: none; text-align: left; padding: 10px 14px; border-radius: 10px; color: {p.muted}; font-weight: 600; }}
QPushButton[variant="nav"]:hover {{ background: {p.surface_alt}; color: {p.text}; }}
QPushButton[variant="nav"]:checked {{ background: {p.accent_soft}; color: {p.accent_soft_text}; }}
QPushButton[variant="icon"] {{ padding: 6px; border: 1px solid transparent; background: transparent; border-radius: 8px; }}
QPushButton[variant="icon"]:hover {{ background: {p.surface_alt}; }}
QPushButton[variant="toast"] {{ background: transparent; color: {p.accent_hover}; border: none; font-weight: 700; padding: 4px 10px; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

QLineEdit {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 9px; padding: 8px 12px; selection-background-color: {p.accent}; selection-color: {p.on_accent}; }}
QLineEdit:focus {{ border: 1px solid {p.accent}; }}
QPlainTextEdit {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; padding: 10px; selection-background-color: {p.accent}; selection-color: {p.on_accent}; font-size: 14px; }}
QPlainTextEdit:focus {{ border: 1px solid {p.accent}; }}

QRadioButton {{ spacing: 10px; padding: 6px 2px; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 9px; border: 2px solid {p.muted}; background: {p.surface}; }}
QRadioButton::indicator:hover {{ border-color: {p.accent}; }}
QRadioButton::indicator:checked {{ width: 8px; height: 8px; border: 5px solid {p.accent}; background: {p.surface}; border-radius: 9px; }}
QComboBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 9px; padding: 7px 12px; min-width: 160px; }}
QComboBox:focus {{ border: 1px solid {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: url("{arrow}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border}; selection-background-color: {p.accent_soft}; selection-color: {p.accent_soft_text}; outline: 0; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {p.muted}; padding: 7px 14px; margin-right: 4px; border-radius: 8px; font-weight: 600; }}
QTabBar::tab:selected {{ background: {p.accent_soft}; color: {p.accent_soft_text}; }}
QTabBar::tab:hover:!selected {{ background: {p.surface_alt}; }}

QProgressBar {{ background: {p.surface_alt}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 16px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.accent_soft}; color: {p.accent_soft_text}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}
QMessageBox, QDialog {{ background: {p.surface}; }}
"""
