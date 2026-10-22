from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .widgets import IconLabel, make_card, make_label

POINTS = [
    ("On-device processing",
     "Text recognition runs entirely on your computer. Your images and the text found in them are never uploaded, "
     "and the app makes no network connections."),
    ("No accounts, ads or analytics",
     "There is no sign-in, no advertising and no tracking or telemetry of any kind."),
    ("Your images stay where they are",
     "The app reads the image you choose and works on a copy in memory. Your original file is never changed. "
     "Screenshots and clipboard images are processed in memory and are not written to disk."),
    ("Saved text is local",
     "When you click Save, the text (and the path of the image file, if any) is stored in a private database in "
     "your user profile, readable only by your account. Delete single items, clear everything, or have old items "
     "deleted automatically in Settings."),
    ("Sharing is always your choice",
     "Text only leaves the app when you copy it, save it to a file, or choose Send by email."),
    ("Logs",
     "The app keeps a small diagnostic log of errors. It never contains image content or recognized text."),
    ("Screen capture",
     "Capture screen only takes a picture when you click it, and you choose the region. Nothing runs in the background."),
]


class PrivacyPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.addWidget(make_label("Privacy", "h1"))
        outer.addWidget(make_label("Your documents are yours. Here is exactly what the app does with them.", "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("page")
        host.setMaximumWidth(760)
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 12, 8, 12)
        col.setSpacing(12)
        for title, body in POINTS:
            card = make_card()
            lay = QVBoxLayout(card)
            lay.setContentsMargins(20, 16, 20, 16)
            lay.setSpacing(4)
            lay.addWidget(make_label(title, "h3"))
            lay.addWidget(make_label(body, "muted", wrap=True))
            col.addWidget(card)
        col.addStretch(1)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)
