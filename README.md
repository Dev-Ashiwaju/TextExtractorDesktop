# TextExtractor Desktop

**A Windows desktop application for extracting text from screenshots and images using optical character recognition (OCR).**

TextExtractor Desktop provides a convenient graphical interface for converting image-based text into editable content. It supports Tesseract OCR and RapidOCR, offering a practical solution for extracting text from screenshots, scanned documents, and other supported image files.

The application is designed for local, offline OCR processing, without requiring users to install Python or configure OCR engines separately when using the packaged Windows installer.

## Features

- **Image-to-text extraction:** Extract text from screenshots and image files.
- **Tesseract OCR:** Use the established open-source Tesseract recognition engine.
- **RapidOCR:** An alternative OCR engine powered by ONNX Runtime.
- **Desktop interface:** Built with Python and Qt (PySide6).
- **Image processing:** Uses Pillow for image handling.
- **Offline operation:** Perform local OCR without a cloud OCR service.
- **Standalone Windows distribution:** Package Python and OCR dependencies with the application.

## Application Screenshots

Screenshots are stored in [`docs/screenshots/`](docs/screenshots/).

### Main Application Interface

![TextExtractor Desktop main interface](docs/screenshots/main-window.png)

### Text Extraction

![Text extraction interface](docs/screenshots/text-extraction.png)

### OCR Engine Selection

![OCR engine configuration](docs/screenshots/ocr-settings.png)

> Replace these example filenames with the actual screenshots in your project. Remove any section that does not correspond to an implemented feature.

## Download and Installation

For regular Windows users, the recommended installation method is the prebuilt application.

1. Visit the [GitHub Releases](../../releases) page.
2. Download the latest Windows installer.
3. Run the installer and follow the installation instructions.
4. Launch TextExtractor Desktop from the Start menu or desktop shortcut.
5. Open an image and use the available OCR controls to extract its text.

The packaged installer is intended to include the required Python runtime, OCR engine binaries, and language data.

## Installation from Source

### Prerequisites

- Windows operating system
- Python 3.10 or later, subject to the project's configured Python requirements
- Git
- Tesseract OCR for development, if using the Tesseract engine

### Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/TextExtractorDesktop.git
cd TextExtractorDesktop
```

### Create a Virtual Environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Configure Tesseract OCR

Install the Windows Tesseract distribution from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).

If necessary, set the `TEXTEXTRACTOR_TESSERACT` environment variable to the full path of `tesseract.exe`.

### Run the Application

Use the application entry point defined in `pyproject.toml` or the project's source documentation.

## Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| Desktop GUI | PySide6 / Qt |
| Primary OCR engine | Tesseract OCR |
| Alternative OCR engine | RapidOCR |
| Inference runtime | ONNX Runtime |
| Image processing | Pillow |
| Windows packaging | PyInstaller |
| Windows installer | Inno Setup, if configured |

## Project Structure

```text
TextExtractorDesktop/
├── .github/
├── docs/
│   └── screenshots/
├── installer/
├── packaging/
├── scripts/
├── src/
├── tests/
├── .gitignore
├── LICENSE.txt
├── pyproject.toml
├── README.md
├── requirements.txt
└── THIRD_PARTY_NOTICES.md
```

Generated build directories, local Python environments, and bundled third-party binaries are excluded from Git version control.

## Building the Windows Application

The project includes directories for packaging and installer configuration.

For development builds, install the required packaging tools:

```bash
pip install pyinstaller
```

Use the project's maintained build scripts or packaging configuration to create the executable.

When preparing a standalone distribution, ensure that the Tesseract executable, supporting DLLs, language data, and required RapidOCR models are included.

Do not assume that installing Python dependencies automatically installs the native Tesseract engine.

## Testing

Run the automated tests, where applicable:

```bash
python -m pytest
```

Install `pytest` in the development environment if it is not already available.

Before publishing a Windows release, test the packaged application on a clean machine without Python or Tesseract installed.

## Contributing

Contributions, bug reports, and suggestions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make and test your changes.
4. Submit a pull request explaining your changes.

## License

See [LICENSE.txt](LICENSE.txt) for the project's license terms.

Third-party software and dependency notices are available in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Support

Use the repository's GitHub Issues page to report reproducible bugs, request enhancements, or suggest improvements.
