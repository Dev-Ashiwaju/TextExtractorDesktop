from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OcrBlock:
    """One paragraph / text block as returned by the engine."""
    text: str


@dataclass
class OcrResult:
    text: str
    blocks: list[OcrBlock] = field(default_factory=list)
    engine: str = ""
    elapsed: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class OcrError(Exception):
    """Recognition failed. The message is safe to show to the user (never contains image text)."""


class EngineUnavailable(OcrError):
    """The selected OCR engine is not installed."""
