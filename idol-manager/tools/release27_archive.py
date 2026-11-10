"""Archive only the audited release directory, never the project tree."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1];folder=ROOT/'dist/IDOL_Manager';out=ROOT/'reports/release27'
manifest=json.loads((out/'distribution_manifest.json').read_text(encoding='utf8'))
expected={r['path']:r for r in manifest['files']}
actual={p.relative_to(folder).as_posix():p for p in folder.rglob('*') if p.is_file()}
assert set(actual)==set(expected)|{'SHA256SUMS.txt'}
for name,r in expected.items():
    assert hashlib.sha256(actual[name].read_bytes()).hexdigest()==r['sha256'],name
archive=ROOT/'dist/IDOL_Manager-0.27.0-Windows-x64.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,p in actual.items():z.write(p,'IDOL_Manager/'+name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(ROOT/'dist/ZIP_SHA256.txt').write_text(digest+'  '+archive.name+'\n',encoding='utf8')
result=dict(path=str(archive),bytes=archive.stat().st_size,sha256=digest,files=len(actual),archive_crc='PASS')
(out/'archive.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(result)
