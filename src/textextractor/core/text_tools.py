"""Pure text helpers: statistics, find-in-text, link/contact detection."""
from __future__ import annotations

import re
from dataclasses import dataclass


def word_count(text: str) -> int:
    return len(text.split())


def char_count(text: str) -> int:
    return len(text)


def find_all(text: str, query: str) -> list[tuple[int, int]]:
    """Case-insensitive, non-overlapping matches as (start, end_exclusive)."""
    if not query:
        return []
    return [(m.start(), m.end()) for m in re.finditer(re.escape(query), text, flags=re.IGNORECASE)]


@dataclass(frozen=True)
class DetectedEntity:
    kind: str   # 'url' | 'email' | 'phone'
    value: str


_URL = re.compile(r"""(?i)\b(?:https?://|www\.)[^\s<>"']*[^\s<>"'.,;:!?)\]]""")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<![\w+])\+?\d[\d ().-]{7,}\d")
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}[/.]\d{1,2}[/.]\d{2,4}$")


def detect_entities(text: str) -> list[DetectedEntity]:
    """Heuristic detection. Bare domains without a scheme or 'www.' are deliberately not treated as links."""
    found: dict[DetectedEntity, None] = {}
    for m in _URL.finditer(text):
        found[DetectedEntity("url", m.group())] = None
    for m in _EMAIL.finditer(text):
        found[DetectedEntity("email", m.group())] = None
    remaining = _EMAIL.sub(" ", _URL.sub(" ", text))  # digits inside URLs/e-mails are not phone numbers
    for m in _PHONE.finditer(remaining):
        value = m.group().strip()
        digits = sum(c.isdigit() for c in value)
        if 9 <= digits <= 15 and not _DATE_LIKE.match(value):
            found[DetectedEntity("phone", value)] = None
    return list(found)
