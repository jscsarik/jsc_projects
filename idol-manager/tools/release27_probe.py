"""Read-only release27 oracle, profiling, SQL plans and dbstat."""
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
import argparse,cProfile,hashlib,json,pstats,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.records_service import RecordsService
OUT=ROOT/'reports/release27';OUT.mkdir(exist_ok=True)
def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf8')
def ro(path):
    c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('before','after'));a=p.parse_args();all_results=[]
    if a.phase=='before':
        source=ROOT/'idol_manager/records_service.py';(OUT/'records_service_before.py.txt').write_bytes(source.read_bytes())
        files=[p for folder in ('assets','config') for p in (ROOT/folder).rglob('*') if p.is_file()]
        files.extend((ROOT/'reports/release_qa').glob('*.md'))
        dump('protected_before.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
        with closing(ro(ROOT/'data/idol_manager.sqlite3')) as src,closing(sqlite3.connect(OUT/'user_before.sqlite3')) as dst:src.backup(dst)
    for season,relative in ((3,'followup_b'),(10,'followup_perf_10'),(20,'followup_a')):
        path=ROOT/'diagnostics'/relative/'simulation.sqlite3';queries=[]
        def connect():
            c=ro(path);c.set_trace_callback(queries.append);return c
        service=RecordsService(SimpleNamespace(path=path,connect=connect));profile=cProfile.Profile();cpu=time.process_time();t=time.perf_counter()
        rows=profile.runcall(service.players,season=season);elapsed=time.perf_counter()-t
        dump(f'{a.phase}_{season}_rows.json',rows)
        with (OUT/f'{a.phase}_{season}_profile.txt').open('w',encoding='utf8') as f:pstats.Stats(profile,stream=f).sort_stats('cumulative').print_stats(35)
        plans=[]
        with closing(ro(path)) as c:
            for sql in dict.fromkeys(q for q in queries if q.lstrip().upper().startswith(('SELECT','WITH'))):
                plans.append(dict(sql=sql,plan=[tuple(r) for r in c.execute('EXPLAIN QUERY PLAN '+sql)]))
        dump(f'{a.phase}_{season}_plans.json',plans)
        equal=None
        if a.phase=='after':equal=rows==json.loads((OUT/f'before_{season}_rows.json').read_text(encoding='utf8'))
        all_results.append(dict(season=season,seconds=elapsed,cpu_seconds=time.process_time()-cpu,queries=len(queries),players=len(rows),equal=equal,path=str(path)))
        print(all_results[-1],flush=True)
    dump(a.phase+'_performance.json',all_results)
    if a.phase=='before':
        with closing(ro(ROOT/'diagnostics/followup_a/simulation.sqlite3')) as c:
            try:sizes=[dict(r) for r in c.execute('SELECT name,SUM(pgsize) bytes,COUNT(*) pages FROM dbstat GROUP BY name ORDER BY bytes DESC')]
            except sqlite3.Error as e:sizes=[dict(unavailable=str(e))]
            dump('db_sizes.json',sizes)
if __name__=='__main__':main()
