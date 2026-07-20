$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean BlueprintMosaicStudio.spec

$Archive = Join-Path $ProjectRoot "dist\BlueprintMosaicStudio-offline.zip"
if (Test-Path $Archive) { Remove-Item -LiteralPath $Archive }
Compress-Archive -Path (Join-Path $ProjectRoot "dist\BlueprintMosaicStudio\*") -DestinationPath $Archive
Write-Host "Offline package created: $Archive"
Write-Host "Run installer.iss with Inno Setup to create the optional Windows installer."
