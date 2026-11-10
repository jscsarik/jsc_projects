# PyInstaller onedir. Only owned code/config; user photos/music and QA data excluded.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
root=Path(SPECPATH)
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=[],
    datas=[(str(root/'config'),'config')],hiddenimports=collect_submodules('idol_manager'),
    hookspath=[],runtime_hooks=[],excludes=['apsw','unittest','pytest','tkinter'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='IDOL_Manager_Debug',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=True,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='IDOL_Manager_Debug')
