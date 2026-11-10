"""Final read-only audit and lookup timings of the completed QA run."""
from pathlib import Path
from contextlib import closing
import json,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.simulate_game import quick_audit
from idol_manager.database import Database
from idol_manager.records_service import RecordsService
from idol_manager.profile_service import ProfileService

def main():
    out=ROOT/'reports/release_qa/followup';path=ROOT/'diagnostics/followup_a/simulation.sqlite3'
    stages=json.loads((out/'long_stages.json').read_text(encoding='utf8'))
    if not any(r['target']==20 and r['status']=='completed' for r in stages):raise ValueError('20 seasons not completed')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        result=dict(integrity=c.execute('PRAGMA integrity_check').fetchone()[0],checks=quick_audit(c),regular=c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],completed_seasons=c.execute("SELECT COUNT(*) FROM season_finals WHERE status='completed'").fetchone()[0])
    db=Database(path);t=time.perf_counter();rows=RecordsService(db).players(season=20)
    result['records_players_seconds']=time.perf_counter()-t;result['records_players_rows']=len(rows)
    profile=ProfileService(db);person=next(r['id'] for r in profile.search() if r['exact']);t=time.perf_counter();profile.get(person,season=20)
    result['profile_seconds']=time.perf_counter()-t
    (out/'final_long_audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result))
if __name__=='__main__':main()
