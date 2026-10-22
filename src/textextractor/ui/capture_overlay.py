"""Full-screen region picker for capturing part of the screen."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QWidget


class CaptureOverlay(QWidget):
    """Shows a frozen screenshot of one screen; the user drags a rectangle. Esc / right-click cancels."""
    captured = Signal(QPixmap)
    cancelled = Signal()

    def __init__(self, screenshot: QPixmap, screen: QScreen):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._shot = screenshot
        self._screen = screen
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._done = False
        self.setGeometry(screen.geometry())

    def start(self) -> None:
        self.setScreen(self._screen)
        self.setGeometry(self._screen.geometry())
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()

    def _selection(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        # QRect(p1, p2) treats both corners as inclusive (+1 px); build it from the exact drag distance instead.
        x1, y1, x2, y2 = self._origin.x(), self._origin.y(), self._current.x(), self._current.y()
        return QRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.RightButton:
            self._cancel()
        elif e.button() == Qt.MouseButton.LeftButton:
            self._origin = self._current = e.position().toPoint()
            self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        sel = self._selection()
        if sel.width() < 6 or sel.height() < 6:
            self._origin = self._current = None
            self.update()
            return
        dpr = self._shot.devicePixelRatio()
        region = QRect(round(sel.x() * dpr), round(sel.y() * dpr), round(sel.width() * dpr), round(sel.height() * dpr))
        result = self._shot.copy(region)
        self._done = True
        self.close()
        self.captured.emit(result)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self._cancel()

    def _cancel(self) -> None:
        self._done = True
        self.close()
        self.cancelled.emit()

    def closeEvent(self, e) -> None:  # noqa: N802
        if not self._done:
            self._done = True
            self.cancelled.emit()
        super().closeEvent(e)

    def paintEvent(self, _e) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._shot)
        dim = QColor(0, 0, 0, 120)
        sel = self._selection()
        if sel.isNull():
            painter.fillRect(self.rect(), dim)
            painter.setPen(QColor("#FFFFFF"))
            f = QFont(self.font())
            f.setPointSize(14)
            painter.setFont(f)
            painter.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter,
                             "Drag to select the area to extract text from\nEsc to cancel")
            return
        for r in (QRect(0, 0, self.width(), sel.top()),
                  QRect(0, sel.bottom() + 1, self.width(), self.height() - sel.bottom() - 1),
                  QRect(0, sel.top(), sel.left(), sel.height()),
                  QRect(sel.right() + 1, sel.top(), self.width() - sel.right() - 1, sel.height())):
            painter.fillRect(r, dim)
        painter.setPen(QPen(QColor("#818CF8"), 2))
        painter.drawRect(sel)
        label = f"{sel.width()} × {sel.height()}"
        painter.setPen(QColor("#FFFFFF"))
        painter.fillRect(QRect(sel.left(), max(0, sel.top() - 24), 90, 22), QColor(0, 0, 0, 170))
        painter.drawText(QRect(sel.left() + 6, max(0, sel.top() - 24), 84, 22), Qt.AlignmentFlag.AlignVCenter, label)
