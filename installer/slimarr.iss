; Slimarr Windows Installer
; Built with Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; Run build-installer.ps1 to generate this automatically.

#define MyAppName "Slimarr"
#define MyAppVersion "1.0.0.3"
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
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Require admin to install to Program Files
PrivilegesRequired=admin
OutputDir=..\dist\installer
OutputBaseFilename=SlimarrSetup-{#MyAppVersion}
SetupIconFile=..\images\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
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
Source: "..\dist\Slimarr\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; Windows startup (optional task)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
; Launch Slimarr after install (skippable)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill any running instance before uninstall
Filename: "taskkill.exe"; Parameters: "/f /im {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillSlimarr"

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
