"""Read-only baseline and strict extraction of the preserved release ZIP."""
from pathlib import Path,PurePosixPath
from contextlib import closing
import hashlib,json,os,platform,sqlite3,sys,zipfile,ctypes
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release28'
BASE=Path(r'C:\Users\Public\Documents\ESTsoft\CreatorTemp\IDOL_Manager28_한글 공백')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf8')
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'baseline.json').exists():raise ValueError('Preserve earlier baseline')
    files=[p for folder in ('assets','config') for p in (ROOT/folder).rglob('*') if p.is_file()]
    files += [p for folder in ('reports/release_qa','reports/release27') for p in (ROOT/folder).glob('*.md')]
    files += [ROOT/'dist/IDOL_Manager-0.27.0-Windows-x64.zip',ROOT/'dist/ZIP_SHA256.txt']
    protected={str(p.relative_to(ROOT)):digest(p) for p in files}
    sources=[ROOT/'data/idol_manager.sqlite3',Path(os.environ['LOCALAPPDATA'])/'IDOL_Manager/saves/idol_manager.sqlite3']
    saves=[]
    for n,p in enumerate(sources):
        if not p.exists():saves.append(dict(path=str(p),exists=False));continue
        snapshot=OUT/f'original_{n}.sqlite3'
        with closing(ro(p)) as c,closing(sqlite3.connect(snapshot)) as d:
            c.backup(d)
            saves.append(dict(path=str(p),exists=True,snapshot=str(snapshot),version=c.execute('PRAGMA user_version').fetchone()[0],day=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],bytes=p.stat().st_size))
    save('baseline.json',dict(protected=protected,saves=saves,environment=dict(windows=platform.platform(),python=sys.version,admin=bool(ctypes.windll.shell32.IsUserAnAdmin())),source={str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'idol_manager').rglob('*.py')}))
    archive=ROOT/'dist/IDOL_Manager-0.27.0-Windows-x64.zip';expected=json.loads((ROOT/'reports/release27/archive.json').read_text(encoding='utf8'))
    if digest(archive)!=expected['sha256']:raise ValueError('ZIP differs from release27 final hash')
    if BASE.exists():raise ValueError('Use a new isolated extraction directory')
    BASE.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        for name in names:
            path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or path.parts[0]!='IDOL_Manager':raise ValueError('Unsafe ZIP path')
            if path.suffix.lower() in ('.sqlite3','.db','.mp3','.wav','.py','.png','.jpg','.jpeg','.webp') or any(v in path.parts for v in ('reports','tests','diagnostics','__pycache__','user_assets')):raise ValueError('Unexpected development/private payload: '+name)
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        z.extractall(BASE)
    install=BASE/'IDOL_Manager';checked=[]
    for line in (install/'SHA256SUMS.txt').read_text(encoding='utf8').splitlines():
        expected_hash,name=line.split('  ',1);p=install/name
        if not p.resolve().is_relative_to(install.resolve()) or digest(p)!=expected_hash:raise ValueError('Extracted file mismatch: '+name)
        checked.append(name)
    required=['IDOL_Manager.exe','_internal/python313.dll','_internal/PySide6/plugins/platforms/qwindows.dll','README_실행안내.txt']
    if not all((install/p).is_file() for p in required):raise ValueError('Required runtime missing')
    save('package_audit.json',dict(archive=str(archive),sha256=digest(archive),zip_entries=len(names),verified_files=len(checked),crc='PASS',install=str(install),required=required,source_project_independent_location=True,clean_windows=False))
    print(dict(install=str(install),saves=saves,files=len(checked)))
if __name__=='__main__':main()
