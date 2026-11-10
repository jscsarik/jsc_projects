from pathlib import Path
from contextlib import closing
import json,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.database import Database
from idol_manager.records_service import RecordsService
out=ROOT/'reports/release27';target=out/'indexed20.sqlite3'
if target.exists():raise ValueError('Do not overwrite an experiment')
with closing(sqlite3.connect((ROOT/'diagnostics/followup_a/simulation.sqlite3').as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(target)) as b:a.backup(b)
before=target.stat().st_size;t=time.perf_counter()
with closing(sqlite3.connect(target)) as c,c:c.execute('CREATE INDEX release27_event_cover ON match_events(match_id,person_id,phase,skill,success)')
build=time.perf_counter()-t;t=time.perf_counter();rows=RecordsService(Database(target)).players();elapsed=time.perf_counter()-t
expected=json.loads((out/'career_before_rows.json').read_text(encoding='utf8'));assert rows==expected
result=dict(bytes_before=before,bytes_after=target.stat().st_size,index_build_seconds=build,query_seconds=elapsed,rows=len(rows),equal=True)
(out/'index_experiment.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(result)
