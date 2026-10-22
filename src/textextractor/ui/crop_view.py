"""Image viewer with an interactive crop rectangle (drag to create, drag edges/corners to resize, drag inside to move)."""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ..core.imaging import CropRect
from .qt_images import pil_to_qpixmap
from .theme import theme

_HANDLE = 6.0      # drawn handle half-size
_HIT = 10.0        # hit-test tolerance (px)
_MIN = CropRect.MIN_SIZE


class CropView(QWidget):
    cropChanged = Signal(object)  # CropRect

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 260)
        self._pixmap: QPixmap | None = None
        self._crop = CropRect()
        self._placeholder = "No image"
        self._drag_mode: str | None = None
        self._drag_anchor = QPointF()
        self._drag_start_crop = CropRect()
        theme.changed.connect(lambda *_: self.update())

    # ---- public API ------------------------------------------------------
    def set_image(self, image: Image.Image | None, placeholder: str = "No image") -> None:
        self._pixmap = pil_to_qpixmap(image) if image is not None else None
        self._placeholder = placeholder
        self._crop = CropRect()
        self.update()

    def set_placeholder(self, text: str) -> None:
        self._pixmap = None
        self._placeholder = text
        self.update()

    def crop(self) -> CropRect:
        return self._crop

    def reset_crop(self) -> None:
        self._set_crop(CropRect())

    # ---- geometry --------------------------------------------------------
    def _image_rect(self) -> QRectF:
        if not self._pixmap or self._pixmap.isNull():
            return QRectF()
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        pw, ph = self._pixmap.width(), self._pixmap.height()
        scale = min(area.width() / pw, area.height() / ph)
        w, h = pw * scale, ph * scale
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def _crop_rect_px(self) -> QRectF:
        r = self._image_rect()
        c = self._crop
        return QRectF(r.left() + c.left * r.width(), r.top() + c.top * r.height(),
                      (c.right - c.left) * r.width(), (c.bottom - c.top) * r.height())

    def _to_frac(self, pos: QPointF) -> QPointF:
        r = self._image_rect()
        return QPointF(min(1.0, max(0.0, (pos.x() - r.left()) / r.width())),
                       min(1.0, max(0.0, (pos.y() - r.top()) / r.height())))

    def _hit(self, pos: QPointF) -> str:
        if self._crop.is_full:
            return "new"
        c = self._crop_rect_px()
        near = lambda a, b: abs(a - b) <= _HIT  # noqa: E731
        x, y = pos.x(), pos.y()
        in_x = c.left() - _HIT <= x <= c.right() + _HIT
        in_y = c.top() - _HIT <= y <= c.bottom() + _HIT
        left, right, top, bottom = near(x, c.left()) and in_y, near(x, c.right()) and in_y, \
            near(y, c.top()) and in_x, near(y, c.bottom()) and in_x
        if top and left: return "tl"
        if top and right: return "tr"
        if bottom and left: return "bl"
        if bottom and right: return "br"
        if left: return "l"
        if right: return "r"
        if top: return "t"
        if bottom: return "b"
        if c.contains(pos): return "move"
        return "new"

    _CURSORS = {"tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                "move": Qt.CursorShape.SizeAllCursor, "new": Qt.CursorShape.CrossCursor}

    # ---- interaction -----------------------------------------------------
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton or self._image_rect().isEmpty():
            return
        pos = e.position()
        if not self._image_rect().adjusted(-_HIT, -_HIT, _HIT, _HIT).contains(pos):
            return
        self._drag_mode = self._hit(pos)
        self._drag_anchor = self._to_frac(pos)
        self._drag_start_crop = self._crop
        if self._drag_mode == "new":
            a = self._drag_anchor
            self._crop = CropRect(a.x(), a.y(), a.x(), a.y())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        pos = e.position()
        if self._image_rect().isEmpty():
            return
        if self._drag_mode is None:
            self.setCursor(QCursor(self._CURSORS[self._hit(pos)]))
            return
        f = self._to_frac(pos)
        s = self._drag_start_crop
        mode = self._drag_mode
        if mode == "new":
            a = self._drag_anchor
            c = CropRect(min(a.x(), f.x()), min(a.y(), f.y()), max(a.x(), f.x()), max(a.y(), f.y()))
        elif mode == "move":
            dx, dy = f.x() - self._drag_anchor.x(), f.y() - self._drag_anchor.y()
            w, h = s.right - s.left, s.bottom - s.top
            left = min(1 - w, max(0.0, s.left + dx))
            top = min(1 - h, max(0.0, s.top + dy))
            c = CropRect(left, top, left + w, top + h)
        else:
            left, top, right, bottom = s.left, s.top, s.right, s.bottom
            if "l" in mode: left = min(f.x(), right - _MIN)
            if "r" in mode: right = max(f.x(), left + _MIN)
            if "t" in mode: top = min(f.y(), bottom - _MIN)
            if "b" in mode: bottom = max(f.y(), top + _MIN)
            c = CropRect(left, top, right, bottom)
        self._crop = c
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._drag_mode is None:
            return
        c = self._crop
        if self._drag_mode == "new" and ((c.right - c.left) < _MIN or (c.bottom - c.top) < _MIN):
            c = CropRect()  # a click (no real drag) clears the selection
        self._drag_mode = None
        self._set_crop(c)

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self.reset_crop()

    def _set_crop(self, c: CropRect) -> None:
        self._crop = c
        self.update()
        self.cropChanged.emit(c)

    # ---- painting --------------------------------------------------------
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = theme.palette
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.surface_alt))
        painter.drawRoundedRect(QRectF(self.rect()), 14, 14)

        r = self._image_rect()
        if self._pixmap is None or r.isEmpty():
            painter.setPen(QColor(p.muted))
            f = QFont(self.font())
            f.setPointSizeF(f.pointSizeF() + 1)
            painter.setFont(f)
            painter.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self._placeholder)
            return

        clip = QPainterPath()
        clip.addRoundedRect(r, 6, 6)
        painter.save()
        painter.setClipPath(clip)
        painter.drawPixmap(r, self._pixmap, QRectF(self._pixmap.rect()))
        painter.restore()
        painter.setPen(QPen(QColor(p.border), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r, 6, 6)

        if self._crop.is_full and self._drag_mode != "new":
            return
        c = self._crop_rect_px()
        scrim = QColor(p.scrim)
        scrim.setAlpha(140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(scrim)
        outer = QPainterPath()
        outer.addRoundedRect(r, 6, 6)
        inner = QPainterPath()
        inner.addRect(c)
        painter.drawPath(outer.subtracted(inner))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.drawRect(c)
        painter.setPen(QPen(QColor(p.accent), 1))
        painter.drawRect(c.adjusted(-1, -1, 1, 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor(p.accent), 2))
        for pt in (c.topLeft(), c.topRight(), c.bottomLeft(), c.bottomRight(),
                   QPointF(c.center().x(), c.top()), QPointF(c.center().x(), c.bottom()),
                   QPointF(c.left(), c.center().y()), QPointF(c.right(), c.center().y())):
            painter.drawRoundedRect(QRectF(pt.x() - _HANDLE / 2, pt.y() - _HANDLE / 2, _HANDLE, _HANDLE), 2, 2)
