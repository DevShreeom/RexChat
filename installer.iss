[Setup]
AppName=Rex Chat
AppVersion=1.0
DefaultDirName={localappdata}\RexChat
PrivilegesRequired=lowest
SetupIconFile=icon.ico
OutputDir=installer_output
OutputBaseFilename=RexChat-Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\RexChat\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "config.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Rex Chat"; Filename: "{app}\RexChat.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autoprograms}\Rex Chat"; Filename: "{app}\RexChat.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\RexChat.exe"; Description: "Launch Rex Chat"; Flags: nowait postinstall skipifsilent
