from pathlib import Path
from types import SimpleNamespace
import json,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import idol_manager.records_service as m
out=ROOT/'reports/release27';expected=json.loads((out/'career_before_rows.json').read_text(encoding='utf8'))
m.FACTS=m.FACTS.replace("FROM chosen x JOIN match_events e ON x.kind='regular' AND x.match_id=e.match_id AND x.person_id=e.person_id",'FROM match_events e')
for name,path in [('direct_original',ROOT/'diagnostics/followup_a/simulation.sqlite3'),('direct_indexed',out/'indexed20.sqlite3')]:
    def connect():
        c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
    t=time.perf_counter();rows=m.RecordsService(SimpleNamespace(path=path,connect=connect)).players();elapsed=time.perf_counter()-t
    assert rows==expected
    result=dict(seconds=elapsed,equal=True,rows=len(rows));(out/(name+'.json')).write_text(json.dumps(result),encoding='utf8');print(name,result,flush=True)
