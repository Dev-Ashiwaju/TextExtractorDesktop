"""Copy a Tesseract installation into ./vendor/tesseract so installers can bundle it.

  Windows:  install the UB Mannheim build, then
            python packaging/vendor_tesseract.py "C:\\Program Files\\Tesseract-OCR"
  macOS:    brew install tesseract; python packaging/vendor_tesseract.py "$(brew --prefix tesseract)" --macos
            (Homebrew binaries link to dylibs; prefer a relocatable build or require users to `brew install tesseract`.)
  Linux:    rely on the distro package (declare it as a dependency of your .deb/.rpm) or ship an AppImage.

Only English (+ osd) tessdata is copied by default; add --langs eng fra deu ... for more.
Tesseract is Apache-2.0 – keep its LICENSE in the bundle (copied automatically if present)."""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path, help="Tesseract install directory (contains tesseract[.exe] and tessdata/)")
    ap.add_argument("--langs", nargs="*", default=["eng", "osd"])
    ap.add_argument("--macos", action="store_true")
    args = ap.parse_args()
    src = args.source
    exe = src / ("tesseract.exe" if sys.platform == "win32" else "bin/tesseract" if args.macos else "tesseract")
    if not exe.is_file():
        print(f"tesseract executable not found under {src}")
        return 1
    dest = ROOT / "vendor" / "tesseract"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    # binaries and DLLs next to tesseract(.exe)
    for f in exe.parent.iterdir():
        if f.is_file() and (f.suffix.lower() in (".exe", ".dll", ".dylib", ".so") or f.name == "tesseract"):
            shutil.copy2(f, dest / f.name)
    tessdata = src / "tessdata"
    if not tessdata.is_dir():
        tessdata = src / "share" / "tessdata"
    (dest / "tessdata").mkdir()
    for lang in args.langs:
        f = tessdata / f"{lang}.traineddata"
        if f.is_file():
            shutil.copy2(f, dest / "tessdata" / f.name)
        else:
            print(f"warning: {f.name} not found")
    for name in ("LICENSE", "LICENSE.txt", "AUTHORS"):
        if (src / name).is_file():
            shutil.copy2(src / name, dest / name)
    print("vendored Tesseract ->", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
