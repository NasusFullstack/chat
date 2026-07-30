; 춥채팅 설치 프로그램 (Inno Setup)
; 빌드: ISCC.exe installer.iss (/DAppVersion=X.Y.Z로 버전 지정, 안 주면 기본값 사용)
; PyInstaller --onedir 결과물(dist\FriendChat_GUI\)이 미리 만들어져 있어야 함
#define AppName "춥채팅"
#define AppExeName "FriendChat_GUI.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{88F53095-0ABC-4EC3-A353-F16DBE62EB53}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 관리자 권한 없이 현재 사용자 계정에만 설치 - 친구들에게 나눠주는 프로그램이라
; UAC 승인창 없이 바로 설치되게 하는 게 사용성이 훨씬 좋음
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=FriendChat_Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "dist\FriendChat_GUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "지금 실행하기"; Flags: nowait postinstall skipifsilent unchecked
