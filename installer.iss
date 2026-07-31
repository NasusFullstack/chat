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

[Code]
// 서명 안 된 PyInstaller exe라 백신이 실행/업데이트를 오탐지로 막는 경우가 있어서,
// 설치 직후 Windows Defender 예외 등록을 도와줄지 물어봄. 설치 자체는 관리자 권한
// 없이(PrivilegesRequired=lowest) 진행되지만, Defender 예외 등록은 관리자 권한이
// 필요해서 이 부분만 따로 UAC 승인을 요청함 - 거부해도 설치 자체는 문제없이 끝남
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if MsgBox(
      'Windows Defender 예외 목록에 이 프로그램을 등록할까요?' + #13#10 +
      '(서명 안 된 프로그램이라 백신이 실행/업데이트를 오탐지로 막는 경우를 줄여줍니다.' + #13#10 +
      '다음 화면에서 관리자 권한 승인 창이 뜰 수 있어요)',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('runas', 'powershell.exe',
        '-NoProfile -WindowStyle Hidden -Command "Add-MpPreference -ExclusionPath ''' + ExpandConstant('{app}') + '''"',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
