#!/usr/bin/env bash
# Build a distributable folder (macOS: .app) with PyInstaller and smoke-test it.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -e ".[rapidocr,dev]"
python scripts/make_icons.py
pyinstaller packaging/textextractor.spec --noconfirm --clean
BIN="dist/TextExtractor/TextExtractor"
[ -d "dist/Text Extractor.app" ] && BIN="dist/Text Extractor.app/Contents/MacOS/TextExtractor"
QT_QPA_PLATFORM=offscreen "$BIN" --selftest
echo "Built OK: dist/"
