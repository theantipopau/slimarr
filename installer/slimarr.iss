; Slimarr Windows Installer
; Built with Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; Run build-installer.ps1 to generate this automatically.

#define MyAppName "Slimarr"
#define MyAppVersion "1.1.2.0"
#define MyAppPublisher "Slimarr"
#define MyAppURL "https://github.com/theantipopau/slimarr"
#define MyAppExeName "Slimarr.exe"
#define MyAppId "{{A7F3D2E1-4B8C-4F9A-B1D2-6E3A9F0C2D45}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Per-user install avoids UAC and Program Files permission issues.
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=SlimarrSetup-{#MyAppVersion}
SetupIconFile=..\images\icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
CloseApplications=yes
RestartApplications=no
; Show license if present
; LicenseFile=..\LICENSE
; Minimum Windows version: Windows 10
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Start Slimarr automatically when Windows starts"; GroupDescription: "Windows Startup:"; Flags: unchecked

[Files]
; Main application (PyInstaller output)
Source: "..\dist\Slimarr\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs restartreplace

[Dirs]
Name: "{userappdata}\Slimarr"
Name: "{userappdata}\Slimarr\data"
Name: "{userappdata}\Slimarr\data\logs"
Name: "{userappdata}\Slimarr\data\MediaCover"
Name: "{userappdata}\Slimarr\data\recycling"

[Icons]
; Start Menu
Name: "{group}\Open {#MyAppName}"; Filename: "{app}\start.bat"; WorkingDir: "{app}"
Name: "{group}\{#MyAppName} (Tray Only)"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Slimarr Data Folder"; Filename: "{win}\explorer.exe"; Parameters: """{userappdata}\Slimarr"""
Name: "{group}\Slimarr Startup Log"; Filename: "{userappdata}\Slimarr\data\logs\startup.log"; Check: FileExists(ExpandConstant('{userappdata}\Slimarr\data\logs\startup.log'))
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\start.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; Windows startup (optional task)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
; Launch Slimarr after install (checkbox is checked by default)
Filename: "{app}\start.bat"; WorkingDir: "{app}"; Description: "Do you want to open Slimarr?"; Flags: nowait postinstall skipifsilent shellexec runminimized

[UninstallRun]
; Kill any running instance before uninstall
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyAppExeName}"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillSlimarr"

[Code]
// Optional: warn user that config/data in AppData won't be removed
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDataPath := ExpandConstant('{userappdata}\Slimarr');
    if DirExists(AppDataPath) then
    begin
      if MsgBox('Your Slimarr configuration and database are stored in:' + #13#10 +
                AppDataPath + #13#10 + #13#10 +
                'Do you want to delete them as well?',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(AppDataPath, True, True, True);
    end;
  end;
end;
