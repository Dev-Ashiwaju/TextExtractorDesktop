"""PyInstaller entry point (the package itself uses relative imports)."""
import sys

from textextractor.app import main

if __name__ == "__main__":
    sys.exit(main())
