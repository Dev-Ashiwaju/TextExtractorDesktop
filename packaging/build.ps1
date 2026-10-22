# Windows build: PyInstaller folder + (optional) Inno Setup installer.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m pip install -e ".[rapidocr,dev]"
python scripts/make_icons.py
pyinstaller packaging/textextractor.spec --noconfirm --clean
$env:QT_QPA_PLATFORM = "offscreen"
& "dist\TextExtractor\TextExtractor.exe" --selftest
if ($LASTEXITCODE -ne 0) { throw "self-test failed" }
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) { & $iscc packaging\installer.iss } else { Write-Host "Inno Setup not found - skipping installer" }
# Sign (recommended for commercial distribution), e.g.:
#   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\TextExtractor\TextExtractor.exe
