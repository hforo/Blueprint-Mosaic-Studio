# PyInstaller build definition for the fully offline Windows application.
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "data"), "data"),
        (str(root / "images"), "images"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="BlueprintMosaicStudio", console=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=True,
    name="BlueprintMosaicStudio",
)
