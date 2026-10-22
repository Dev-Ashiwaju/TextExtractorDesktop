"""Reusable themed widgets."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QLayoutItem, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import icons
from .theme import Palette, theme


def make_label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    lab.setWordWrap(wrap)
    return lab


def make_card(flat: bool = False) -> QFrame:
    f = QFrame()
    f.setObjectName("cardFlat" if flat else "card")
    return f


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class ThemedButton(QPushButton):
    """Button whose icon is re-coloured when the theme changes.
    variant: primary | secondary | ghost | danger | chip | nav | icon | toast"""

    def __init__(self, text: str = "", icon_name: str | None = None, variant: str = "secondary",
                 icon_size: int = 18, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._variant = variant
        self._accent_icon = False
        self.setProperty("variant", variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(icon_size, icon_size))
        theme.changed.connect(self._refresh_icon)
        self._refresh_icon()

    def set_icon_name(self, name: str | None) -> None:
        self._icon_name = name
        self._refresh_icon()

    def set_accent_icon(self, on: bool) -> None:
        self._accent_icon = on
        self._refresh_icon()

    def _icon_colors(self, p: Palette) -> tuple[str, str]:
        v = self._variant
        if self._accent_icon:
            return p.accent, p.muted
        if v == "primary":
            return p.on_accent, p.muted
        if v == "danger":
            return p.danger, p.muted
        if v == "chip":
            return p.accent_soft_text, p.muted
        if v == "nav":
            return (p.accent_soft_text if self.isChecked() else p.muted), p.muted
        if v in ("ghost", "icon"):
            return p.muted, p.border
        return p.text, p.muted

    def _refresh_icon(self, *_: object) -> None:
        if not self._icon_name:
            self.setIcon(QIcon())
            return
        normal, disabled = self._icon_colors(theme.palette)
        pad = 8 if self.text() else 0  # breathing room between icon and label
        self.setIconSize(QSize(self._icon_size + pad, self._icon_size))
        self.setIcon(icons.icon(self._icon_name, normal, disabled, self._icon_size, pad_right=pad))
        self.style().unpolish(self)
        self.style().polish(self)


class NavButton(ThemedButton):
    def __init__(self, text: str, icon_name: str, parent: QWidget | None = None):
        super().__init__(text, icon_name, "nav", 20, parent)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.toggled.connect(lambda _c: self._refresh_icon())
        self.setMinimumHeight(42)


class IconLabel(QLabel):
    """A QLabel showing a themed icon."""

    def __init__(self, name: str, size: int = 24, color_role: str = "muted", parent: QWidget | None = None):
        super().__init__(parent)
        self._name, self._size, self._role = name, size, color_role
        self.setFixedSize(size, size)
        theme.changed.connect(self._refresh)
        self._refresh()

    def _refresh(self, *_: object) -> None:
        p = theme.palette
        color = {"muted": p.muted, "accent": p.accent, "text": p.text, "danger": p.danger}.get(self._role, p.muted)
        self.setPixmap(icons.pixmap(self._name, color, self._size))


class FlowLayout(QLayout):
    """Wraps child widgets onto new lines (used for chips)."""

    def __init__(self, parent: QWidget | None = None, hspacing: int = 8, vspacing: int = 8):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h, self._v = hspacing, vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > eff.right() + 1 and line_h > 0:
                x = eff.x()
                y += line_h + self._v
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


class Toast(QFrame):
    """Small transient message at the bottom of the window, with an optional action (e.g. Undo)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 8, 8)
        lay.setSpacing(8)
        self._text = QLabel()
        self._text.setObjectName("toastText")
        self._action = ThemedButton("", None, "toast")
        self._action.clicked.connect(self._on_action)
        lay.addWidget(self._text)
        lay.addWidget(self._action)
        self._callback: Callable[[], None] | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, action_text: str | None = None,
                     action: Callable[[], None] | None = None, timeout_ms: int = 4500) -> None:
        self._text.setText(text)
        self._callback = action
        self._action.setVisible(bool(action_text and action))
        self._action.setText(action_text or "")
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(timeout_ms)

    def reposition(self) -> None:
        p = self.parentWidget()
        if p is None:
            return
        self.adjustSize()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 28)

    def _on_action(self) -> None:
        cb, self._callback = self._callback, None
        self.hide()
        if cb:
            cb()


def v_box(*widgets: QWidget, spacing: int = 12, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        lay.addWidget(w)
    return lay


def expanding(w: QWidget) -> QWidget:
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return w
