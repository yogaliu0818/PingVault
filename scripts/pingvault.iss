; Inno Setup script for PingVault
; Built by scripts\build_installer.ps1

#define MyAppName "PingVault"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PingVault"
#define MyAppExeName "PingVault.exe"
#define MyAppURL "https://github.com/"

[Setup]
AppId={{8F3C2A1E-9B4D-4E7A-A6C1-2D5F8E0B1A93}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
; Keep the asset name stable so README's latest-download URL survives upgrades.
OutputBaseFilename=PingVault-Setup
SetupIconFile=..\pingvault\assets\pingvault.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
UsedUserAreasWarning=no

[Languages]
Name: "chinesetraditional"; MessagesFile: "innosetup\ChineseTraditional.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Entire PyInstaller one-folder build
Source: "..\dist\PingVault\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\PingVault"

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  // Best-effort: ask running app to exit so ledgers can restore.
  Exec('taskkill.exe', '/IM PingVault.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
