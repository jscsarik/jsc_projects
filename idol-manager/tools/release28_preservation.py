"""Compare the two real saves and protected files without opening writes."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release28'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for part in iter(lambda:f.read(1048576),b''):h.update(part)
    return h.hexdigest()
def fingerprint(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        data={}
        for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            rows=sorted(c.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall(),key=repr)
            data[name]=dict(count=len(rows),sha256=hashlib.sha256(repr(rows).encode()).hexdigest())
        return dict(tables=data,version=c.execute('PRAGMA user_version').fetchone()[0],day=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],integrity=c.execute('PRAGMA integrity_check').fetchone()[0],foreign_keys=c.execute('PRAGMA foreign_key_check').fetchall())
def main():
    before=json.loads((OUT/'baseline.json').read_text(encoding='utf8'));changed=[n for n,h in before['protected'].items() if not (ROOT/n).is_file() or sha(ROOT/n)!=h];saves=[]
    for item in before['saves']:
        if not item['exists']:continue
        a=fingerprint(Path(item['snapshot']));b=fingerprint(Path(item['path']))
        saves.append(dict(path=item['path'],identical=a==b,changed_tables=[n for n,v in a['tables'].items() if b['tables'].get(n)!=v],version=b['version'],day=b['day'],integrity=b['integrity'],foreign_keys=b['foreign_keys']))
    changes=[n for n,h in before['source'].items() if sha(ROOT/n)!=h]
    result=dict(protected_files=len(before['protected']),changed_protected_files=changed,real_saves=saves,changed_source=changes,new_source=[str(p.relative_to(ROOT)) for p in (ROOT/'idol_manager').rglob('*.py') if str(p.relative_to(ROOT)) not in before['source']])
    (OUT/'preservation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(result)
    if changed or not all(s['identical'] for s in saves):raise SystemExit(2)
if __name__=='__main__':main()
