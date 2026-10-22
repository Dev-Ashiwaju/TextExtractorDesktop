# Third-party notices

This product bundles or depends on the following open-source components. Review each licence's current text and
obligations with your legal advisor before commercial distribution.

| Component | Use | Licence | Notes |
|---|---|---|---|
| Qt for Python (PySide6) / Qt 6 | UI | LGPL-3.0 (Essentials modules) | Distribute as dynamically-linked libraries (PyInstaller *onedir* does this), include the LGPL text, tell users how to obtain the Qt sources / relink. Do **not** switch to a single-file (onefile) build without reviewing LGPL implications. A commercial Qt licence is also available. |
| Pillow | Image decoding | HPND | |
| Tesseract OCR + tessdata | Primary OCR engine (called as a separate process) | Apache-2.0 | Include licence and NOTICE with the bundled binaries. |
| RapidOCR (rapidocr-onnxruntime), ONNX Runtime, OpenCV, NumPy | Optional fallback OCR engine | Apache-2.0 / MIT / Apache-2.0 / BSD | Bundled PaddleOCR-derived models are Apache-2.0. |
| Feather-style icons | UI icons (re-drawn inline SVG paths) | MIT | Inspired by Feather Icons (MIT). |
| PyInstaller | Packaging only | GPL-2.0 with bootloader exception | Permits distributing the bundled apps under any licence. |
