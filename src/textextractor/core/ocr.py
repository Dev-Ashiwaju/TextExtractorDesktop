"""OCR engines behind one interface.

* TesseractEngine – preferred. Best accuracy on Latin-script prose and many languages. Needs the Tesseract
  binary (bundled in installers, or found on PATH / common install locations).
* RapidOcrEngine  – pip-only fallback (PaddleOCR models on ONNX Runtime). Zero configuration, but the
  bundled Chinese/English model is weaker at English word spacing; layout is reconstructed from boxes.
Images are passed in memory; nothing is written to disk and no network access is used.
"""
from __future__ import annotations

import io
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image

from .models import EngineUnavailable, OcrBlock, OcrError, OcrResult


# --------------------------------------------------------------------------- shared helpers
def blocks_to_result(blocks: Sequence[Sequence[str]], engine: str = "") -> OcrResult:
    """Lines are joined with \\n, blocks (paragraphs) with a blank line. Empty blocks are dropped."""
    texts = [
        "\n".join(line.strip() for line in lines if line.strip()).strip()
        for lines in blocks
    ]
    texts = [t for t in texts if t]
    return OcrResult("\n\n".join(texts), [OcrBlock(t) for t in texts], engine=engine)


class OcrEngine(ABC):
    name: str = ""
    label: str = ""

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def recognize(self, image: Image.Image, languages: Sequence[str] = ("eng",)) -> OcrResult: ...

    def languages(self) -> list[str]:
        return ["eng"]

    def unavailable_hint(self) -> str:
        return ""


# --------------------------------------------------------------------------- Tesseract
def app_root() -> Path:
    """Directory containing the app (or the PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]


def find_tesseract() -> str | None:
    exe = "tesseract.exe" if os.name == "nt" else "tesseract"
    candidates: list[str | None] = [
        os.environ.get("TEXTEXTRACTOR_TESSERACT"),
        str(app_root() / "vendor" / "tesseract" / exe),
        shutil.which("tesseract"),
    ]
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
    elif sys.platform == "darwin":
        candidates += ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


@dataclass
class _Word:
    block: int
    par: int
    line: int
    text: str


def parse_tesseract_tsv(tsv: str, engine: str = "tesseract") -> OcrResult:
    """Group Tesseract's word rows into lines (\\n) and paragraphs (blank line), in its reading order."""
    words: list[_Word] = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t", 11)
        if len(cols) < 12 or cols[0] != "5":  # level 5 = word
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            continue
        text = cols[11].strip()
        if conf < 0 or not text:
            continue
        words.append(_Word(int(cols[2]), int(cols[3]), int(cols[4]), text))

    paragraphs: dict[tuple[int, int], dict[int, list[str]]] = {}
    for w in words:
        paragraphs.setdefault((w.block, w.par), {}).setdefault(w.line, []).append(w.text)
    blocks = [[" ".join(ws) for ws in lines.values()] for lines in paragraphs.values()]
    return blocks_to_result(blocks, engine)


class TesseractEngine(OcrEngine):
    name = "tesseract"
    label = "Tesseract"

    def __init__(self, executable: str | None = None, timeout: float = 180.0):
        self._exe = executable or find_tesseract()
        self._timeout = timeout
        self._langs: list[str] | None = None

    @property
    def executable(self) -> str | None:
        return self._exe

    def is_available(self) -> bool:
        return self._exe is not None

    def unavailable_hint(self) -> str:
        return ("Tesseract was not found. Install it (Windows: UB Mannheim installer; macOS: `brew install tesseract`; "
                "Linux: `sudo apt install tesseract-ocr`) or set TEXTEXTRACTOR_TESSERACT to its path.")

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        bundled = app_root() / "vendor" / "tesseract" / "tessdata"
        if self._exe and Path(self._exe).parent == bundled.parent and bundled.is_dir():
            env["TESSDATA_PREFIX"] = str(bundled)
        return env

    @staticmethod
    def _flags() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flash on Windows

    def languages(self) -> list[str]:
        if self._langs is None:
            self._langs = ["eng"]
            if self._exe:
                try:
                    p = subprocess.run([self._exe, "--list-langs"], capture_output=True, text=True,
                                       timeout=20, env=self._env(), creationflags=self._flags())
                    found = [ln.strip() for ln in p.stdout.splitlines()[1:] if ln.strip() and ln.strip() != "osd"]
                    if found:
                        self._langs = sorted(found)
                except (OSError, subprocess.SubprocessError):
                    pass
        return self._langs

    @staticmethod
    def _prepare(image: Image.Image) -> Image.Image:
        """Tesseract does best with ~30 px text height; upscale small images (e.g. small screenshots)."""
        if max(image.size) < 1200:
            factor = min(2.0, 2800 / max(image.size))
            if factor > 1.0:
                return image.resize((round(image.width * factor), round(image.height * factor)), Image.Resampling.LANCZOS)
        return image

    def recognize(self, image: Image.Image, languages: Sequence[str] = ("eng",)) -> OcrResult:
        if not self._exe:
            raise EngineUnavailable(self.unavailable_hint())
        installed = set(self.languages())
        langs = [l for l in languages if l in installed] or ["eng"]
        buf = io.BytesIO()
        self._prepare(image).save(buf, "PNG")
        cmd = [self._exe, "stdin", "stdout", "-l", "+".join(langs), "--psm", "3", "-c", "tessedit_create_tsv=1"]
        started = time.perf_counter()
        try:
            proc = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, timeout=self._timeout,
                                  env=self._env(), creationflags=self._flags())
        except subprocess.TimeoutExpired as e:
            raise OcrError("Text recognition took too long and was stopped. Try a smaller or cropped image.") from e
        except OSError as e:
            raise OcrError("Tesseract could not be started.") from e
        if proc.returncode != 0:
            raise OcrError("Tesseract failed to process this image.")
        result = parse_tesseract_tsv(proc.stdout.decode("utf-8", "replace"), self.label)
        result.elapsed = time.perf_counter() - started
        return result


# --------------------------------------------------------------------------- RapidOCR
@dataclass(frozen=True)
class TextBox:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def layout_blocks(boxes: Sequence[TextBox]) -> list[list[str]]:
    """Reconstruct reading order from detected line boxes: columns left→right, rows top→bottom,
    paragraphs split at larger vertical gaps."""
    boxes = [b for b in boxes if b.text.strip()]
    if not boxes:
        return []
    med_h = statistics.median(max(1.0, b.y1 - b.y0) for b in boxes)

    columns: list[list[TextBox]] = []
    for b in sorted(boxes, key=lambda b: b.x0):
        for col in columns:
            cx0, cx1 = min(c.x0 for c in col), max(c.x1 for c in col)
            overlap = min(cx1, b.x1) - max(cx0, b.x0)
            if overlap > 0.3 * min(cx1 - cx0, b.x1 - b.x0):
                col.append(b)
                break
        else:
            columns.append([b])
    columns.sort(key=lambda col: min(c.x0 for c in col))

    blocks: list[list[str]] = []
    for col in columns:
        rows: list[list[TextBox]] = []
        for b in sorted(col, key=lambda b: b.cy):
            if rows and abs(b.cy - statistics.fmean(r.cy for r in rows[-1])) <= 0.5 * med_h:
                rows[-1].append(b)
            else:
                rows.append([b])
        current: list[str] = []
        prev_bottom: float | None = None
        for row in rows:
            top = min(r.y0 for r in row)
            if prev_bottom is not None and top - prev_bottom > 0.75 * med_h and current:
                blocks.append(current)
                current = []
            current.append(" ".join(r.text.strip() for r in sorted(row, key=lambda r: r.x0)))
            prev_bottom = max(r.y1 for r in row)
        if current:
            blocks.append(current)
    return blocks


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"
    label = "RapidOCR"

    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec("rapidocr_onnxruntime") is not None
        except (ImportError, ValueError):
            return False

    def unavailable_hint(self) -> str:
        return "RapidOCR is not installed. Install it with: pip install rapidocr-onnxruntime"

    def warm_up(self) -> None:
        self._get()

    def _get(self):
        with self._lock:
            if self._engine is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except ImportError as e:
                    raise EngineUnavailable(self.unavailable_hint()) from e
                self._engine = RapidOCR()
            return self._engine

    def recognize(self, image: Image.Image, languages: Sequence[str] = ("eng",)) -> OcrResult:
        import numpy as np
        engine = self._get()
        started = time.perf_counter()
        try:
            raw, _ = engine(np.asarray(image.convert("RGB")))
        except Exception as e:  # onnxruntime / opencv errors vary; never leak details or text
            raise OcrError("Text recognition failed. Please try again.") from e
        boxes = []
        for box, text, _score in raw or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            boxes.append(TextBox(min(xs), min(ys), max(xs), max(ys), str(text)))
        result = blocks_to_result(layout_blocks(boxes), self.label)
        result.elapsed = time.perf_counter() - started
        return result


# --------------------------------------------------------------------------- selection
_ENGINES: dict[str, OcrEngine] = {}


def get_engine(name: str) -> OcrEngine:
    if name not in _ENGINES:
        _ENGINES[name] = {"tesseract": TesseractEngine, "rapidocr": RapidOcrEngine}[name]()
    return _ENGINES[name]


def resolve_engine(preference: str = "auto") -> OcrEngine:
    """'auto' prefers Tesseract, then RapidOCR. An explicit choice is honoured even if unavailable
    (recognize() then raises EngineUnavailable with an install hint)."""
    if preference in ("tesseract", "rapidocr"):
        return get_engine(preference)
    for name in ("tesseract", "rapidocr"):
        engine = get_engine(name)
        if engine.is_available():
            return engine
    return get_engine("tesseract")
