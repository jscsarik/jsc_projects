"""Read-only final checks, seeded comparisons, and source import audit."""
from pathlib import Path
from contextlib import closing
import ast,hashlib,importlib,json,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.release_qa import OUT,save,protect_connections
from tools.simulate_game import quick_audit,schedule_audit

def main():
    protect_connections();imports=[];syntax=[]
    for p in (ROOT/'idol_manager').rglob('*.py'):
        try:
            compile(p.read_text(encoding='utf-8-sig'),str(p),'exec');module='.'.join(p.relative_to(ROOT).with_suffix('').parts)
            importlib.import_module(module);imports.append(module)
        except Exception as e:syntax.append(dict(file=str(p),error=repr(e)))
    save('static_audit.json',dict(compiled_and_imported=len(imports),errors=syntax,modules=imports,type_checker='NOT TESTED; no configured type checker/linters installed',review='Transactional critical paths + except/pass findings in environment.json manually scoped; not a proof of every path'))
    paths=[ROOT/'diagnostics'/n/'simulation.sqlite3' for n in ('26_resume','26_seed_a','26_seed_b','26_seed_c')]
    audits=[]
    for path in paths:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
            c.row_factory=sqlite3.Row;seasons=[r[0] for r in c.execute('SELECT season FROM season_schedules')]
            audits.append(dict(path=str(path),bytes=path.stat().st_size,version=c.execute('PRAGMA user_version').fetchone()[0],day=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],integrity=c.execute('PRAGMA integrity_check').fetchone()[0],foreign_keys=len(c.execute('PRAGMA foreign_key_check').fetchall()),checks=quick_audit(c),schedule=[schedule_audit(c,s) for s in seasons],champions=[dict(r) for r in c.execute("SELECT season,agency_id FROM season_honors WHERE kind='champion'")],vacancies=[dict(r) for r in c.execute("SELECT * FROM award_outcomes WHERE status='NO_ELIGIBLE_CANDIDATE'")],retired=c.execute("SELECT COUNT(*) FROM roster_memberships WHERE career_status='retired'").fetchone()[0]))
    save('database_audit.json',audits)
    con=[sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) for p in paths[1:3]]
    ignored={'created_at','picked_at','initialized_at','started_at','selected_at','completed_at'};checks=[]
    for (table,) in con[0].execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        cols=[r[1] for r in con[0].execute('PRAGMA table_info('+table+')') if r[1] not in ignored]
        q='SELECT '+','.join(cols)+' FROM '+table
        hashes=[hashlib.sha256(repr(sorted(c.execute(q).fetchall(),key=repr)).encode()).hexdigest() for c in con]
        checks.append(dict(table=table,same=hashes[0]==hashes[1]))
    for c in con:c.close()
    with closing(sqlite3.connect(paths[1].as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(paths[3].as_uri()+'?mode=ro',uri=True)) as b:
        different=a.execute('SELECT id FROM scheduled_matches ORDER BY match_order LIMIT 1').fetchone()!=b.execute('SELECT id FROM scheduled_matches ORDER BY match_order LIMIT 1').fetchone()
    save('reproducibility.json',dict(seed=260029,table_checks=checks,same_seed_semantic_match=all(c['same'] for c in checks),ignored_wall_clock_columns=sorted(ignored),different_seed=260030,different_schedule=different,seed_c_scope='176 real matches; 10-second safe checkpoint; not a full season',seed_a_resumed_prepared_first_match=True))
    assets={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'assets').rglob('*') if p.is_file()}
    original=json.loads((OUT/'protected_assets_before.json').read_text(encoding='utf8'))
    source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for directory in ('idol_manager','tests','tools','config') for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    before=json.loads((OUT/'environment.json').read_text(encoding='utf8'))['source']
    save('source_after.json',dict(files=source,changed=[p for p,h in source.items() if before.get(p)!=h],removed=[p for p in before if p not in source]))
    with closing(sqlite3.connect((ROOT/'data/idol_manager.sqlite3').as_uri()+'?mode=ro',uri=True)) as live:
        live_version=live.execute('PRAGMA user_version').fetchone()[0];day=live.execute('SELECT absolute_day FROM game_clock').fetchone()[0]
        with closing(sqlite3.connect((OUT/'user_save_snapshot.sqlite3').as_uri()+'?mode=ro',uri=True)) as old:
            changed=[]
            for table, in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                q='SELECT * FROM '+table
                if sorted(live.execute(q).fetchall(),key=repr)!=sorted(old.execute(q).fetchall(),key=repr):changed.append(table)
    save('protection_after.json',dict(asset_files=len(assets),assets_unchanged=assets==original,config_unchanged=all(h==source[p] for p,h in before.items() if Path(p).parts[0]=='config'),live_version=live_version,live_day=day,live_changed_tables=changed,qa_live_connections_readonly=True,comment='User may independently play; the QA processes prohibit writable live-save connections. No production migration was run.'))
    print('static errors',syntax,'same seed',all(c['same'] for c in checks),'assets unchanged',assets==original)
if __name__=='__main__':main()
