"""Final read-only save/assets/report audit against the pre-work snapshot."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release27'
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
def fingerprint(c):
    result={}
    for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        rows=sorted(c.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall(),key=repr)
        result[name]=dict(rows=len(rows),sha256=hashlib.sha256(repr(rows).encode()).hexdigest())
    return result
def main():
    expected=json.loads((OUT/'protected_before.json').read_text(encoding='utf8'))
    mismatches=[name for name,digest in expected.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    with closing(ro(OUT/'user_before.sqlite3')) as before,closing(ro(ROOT/'data/idol_manager.sqlite3')) as after:
        a,b=fingerprint(before),fingerprint(after)
        live=dict(all_tables_equal=a==b,tables=b,version=after.execute('PRAGMA user_version').fetchone()[0],absolute_day=after.execute('SELECT absolute_day FROM game_clock').fetchone()[0],integrity=after.execute('PRAGMA integrity_check').fetchone()[0],foreign_keys=after.execute('PRAGMA foreign_key_check').fetchall())
    source=ROOT/'diagnostics/followup_a/simulation.sqlite3'
    with closing(ro(source)) as c:
        long=dict(bytes=source.stat().st_size,integrity=c.execute('PRAGMA integrity_check').fetchone()[0],foreign_keys=c.execute('PRAGMA foreign_key_check').fetchall(),matches=c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],absolute_day=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0])
    old=json.loads((ROOT/'reports/release_qa/environment.json').read_text(encoding='utf8')).get('source',{})
    changed=[str(p.relative_to(ROOT)) for folder in ('idol_manager','tests','tools','config') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and old.get(str(p.relative_to(ROOT)))!=hashlib.sha256(p.read_bytes()).hexdigest()]
    result=dict(protected_count=len(expected),protected_mismatches=mismatches,live=live,long_qa=long,changed_from_26_inventory=changed,default_appdata_save_exists=(Path.home()/'AppData/Local/IDOL_Manager/saves/idol_manager.sqlite3').exists())
    (OUT/'preservation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(dict(protected_count=len(expected),mismatches=mismatches,live_equal=a==b,long_qa=long))
    if mismatches or a!=b or live['integrity']!='ok' or long['integrity']!='ok':raise SystemExit(2)
if __name__=='__main__':main()
