#define AppVersion "1.1.0"

[Setup]
AppId=Frommer-droid.VK-message-history
AppName=Конвертер истории сообщений ВК
AppVersion={#AppVersion}
AppPublisher=Frommer-droid
AppPublisherURL=https://github.com/Frommer-droid/VK-message-history
DefaultDirName={localappdata}\Programs\VK Message History
DefaultGroupName=VK Message History
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=VK-message-history_v{#AppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\logo.ico
UninstallDisplayIcon={app}\VK-message-history.exe
LicenseFile=..\LICENSE

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: unchecked

[Files]
Source: "..\VK-message-history\*"; DestDir: "{app}"; Excludes: "ChatConverter_settings.json"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\VK Message History"; Filename: "{app}\VK-message-history.exe"; WorkingDir: "{app}"; IconFilename: "{app}\logo.ico"
Name: "{autodesktop}\VK Message History"; Filename: "{app}\VK-message-history.exe"; WorkingDir: "{app}"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\VK-message-history.exe"; Description: "Запустить приложение"; Flags: nowait postinstall skipifsilent
