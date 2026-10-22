
#define AppName "Text Extractor"
#define AppVersion "1.0.0"
#define AppPublisher "Text Extractor"
#define AppExeName "TextExtractor.exe"

[Setup]
AppId={{392438B2-B5B1-4FB3-95AE-695B8A68982C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}

DefaultDirName={localappdata}\Programs\TextExtractor
DefaultGroupName={#AppName}

OutputDir=..\installer
OutputBaseFilename=TextExtractor-Setup-{#AppVersion}

SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
LicenseFile=..\LICENSE.txt

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

PrivilegesRequired=lowest
UsePreviousAppDir=no

CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\TextExtractor\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; \
    Description: "Create a desktop shortcut"; \
    Flags: unchecked

[Icons]
Name: "{group}\{#AppName}"; \
    Filename: "{app}\{#AppExeName}"; \
    WorkingDir: "{app}"

Name: "{autodesktop}\{#AppName}"; \
    Filename: "{app}\{#AppExeName}"; \
    WorkingDir: "{app}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
    WorkingDir: "{app}"; \
    Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent
