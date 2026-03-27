; Inno Setup configuration for ykt-cli (Windows amd64)
; Build with: iscc /DMyAppVersion=x.y.z ykt-cli.iss

#define MyAppName "ykt-cli"
#define MyAppExeName "ykt.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\ykt-cli
OutputDir=..\dist
OutputBaseFilename=ykt-cli-windows-amd64-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin

[Files]
Source: "..\dist\ykt-cli-windows-amd64\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Code]
const
  EnvironmentKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

procedure AddToPath();
var
  CurrentPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', CurrentPath) then
    CurrentPath := '';
  if Pos(';' + ExpandConstant('{app}') + ';', ';' + CurrentPath + ';') = 0 then
  begin
    if (CurrentPath <> '') and (CurrentPath[Length(CurrentPath)] <> ';') then
      CurrentPath := CurrentPath + ';';
    CurrentPath := CurrentPath + ExpandConstant('{app}');
    RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', CurrentPath);
  end;
end;

procedure RemoveFromPath();
var
  CurrentPath, AppDir, NewPath: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', CurrentPath) then
    Exit;
  AppDir := ExpandConstant('{app}');
  P := Pos(';' + AppDir + ';', ';' + CurrentPath + ';');
  if P = 0 then
    Exit;
  { P is the position in ';' + CurrentPath + ';', adjust for original string }
  Dec(P);
  if P = 0 then
  begin
    { AppDir is at the very start }
    NewPath := Copy(CurrentPath, Length(AppDir) + 1, MaxInt);
    if (NewPath <> '') and (NewPath[1] = ';') then
      NewPath := Copy(NewPath, 2, MaxInt);
  end
  else
  begin
    { AppDir is in the middle or at the end; remove preceding semicolon + AppDir }
    NewPath := Copy(CurrentPath, 1, P - 1) + Copy(CurrentPath, P + Length(AppDir) + 1, MaxInt);
  end;
  RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', NewPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    AddToPath();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath();
end;
