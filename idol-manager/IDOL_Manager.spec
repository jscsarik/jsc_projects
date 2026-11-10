# PyInstaller onedir. Only owned code/config; user photos/music and QA data excluded.
from pathlib import Path
import os,sys
# Avoid collecting incompatible DLLs from unrelated developer tools (Poppler ICU).
os.environ['PATH']=os.pathsep.join([str(Path(sys.executable).parent),sys.base_prefix,
    str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot']])
from PyInstaller.utils.hooks import collect_submodules
root=Path(SPECPATH)
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=[],
    datas=[(str(root/'config'),'config')]+[(str(root/folder),folder) for folder in ('assets/agencies','assets/title','assets/audio/bgm/title') if (root/folder).is_dir()],hiddenimports=collect_submodules('idol_manager'),
    hookspath=[],runtime_hooks=[],excludes=['apsw','unittest','pytest','tkinter'],noarchive=False)
# The game does not render PDF or provide a virtual keyboard. Avoid unrelated
# image/input plugins and their optional Qt modules in the redistributable.
unused={'qpdf.dll','qt6pdf.dll','qtvirtualkeyboardplugin.dll','qt6virtualkeyboard.dll'}
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in unused]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='IDOL_Manager',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,
    version=str(root/'packaging/windows_version.txt'),icon=str(root/'assets/title/logo.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='IDOL_Manager')
