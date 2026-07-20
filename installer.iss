[Setup]
AppName=Blueprint Mosaic Studio
AppVersion=1.0
DefaultDirName={autopf}\Blueprint Mosaic Studio
DefaultGroupName=Blueprint Mosaic Studio
OutputDir=dist
OutputBaseFilename=BlueprintMosaicStudio-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\BlueprintMosaicStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Blueprint Mosaic Studio"; Filename: "{app}\BlueprintMosaicStudio.exe"
Name: "{autodesktop}\Blueprint Mosaic Studio"; Filename: "{app}\BlueprintMosaicStudio.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\BlueprintMosaicStudio.exe"; Description: "Launch Blueprint Mosaic Studio"; Flags: nowait postinstall skipifsilent
