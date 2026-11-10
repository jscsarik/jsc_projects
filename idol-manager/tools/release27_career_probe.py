from pathlib import Path
from types import SimpleNamespace
import json,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.records_service import RecordsService
out=ROOT/'reports/release27';path=ROOT/'diagnostics/followup_a/simulation.sqlite3'
def connect():
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
namespace={'__package__':'idol_manager'};source=out/'records_service_before.py.txt'
exec(compile(source.read_text(encoding='utf8'),str(source),'exec'),namespace)
results=[];old=None
for label,cls in [('before',namespace['RecordsService']),('after',RecordsService)]:
    t=time.perf_counter();rows=cls(SimpleNamespace(path=path,connect=connect)).players();elapsed=time.perf_counter()-t
    if label=='before':old=rows
    else:assert rows==old
    results.append(dict(label=label,seconds=elapsed,rows=len(rows),equal=rows==old));print(results[-1],flush=True)
    (out/f'career_{label}_rows.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf8')
(out/'career_performance.json').write_text(json.dumps(results,indent=2),encoding='utf8')
