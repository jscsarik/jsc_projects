"""Separate-process CPU/RSS observations for the identical read-only databases."""
from pathlib import Path
from types import SimpleNamespace
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.release_qa import Monitor
from tools.release27_probe import ro
OUT=ROOT/'reports/release27'
if len(sys.argv)==3:
    phase,season=sys.argv[1],int(sys.argv[2]);path=ROOT/'diagnostics'/{3:'followup_b',10:'followup_perf_10',20:'followup_a'}[season]/'simulation.sqlite3'
    if phase=='before':
        ns={'__package__':'idol_manager'};source=OUT/'records_service_before.py.txt';exec(compile(source.read_text(encoding='utf8'),str(source),'exec'),ns);service_class=ns['RecordsService']
    else:
        from idol_manager.records_service import RecordsService as service_class
    service=service_class(SimpleNamespace(path=path,connect=lambda:ro(path)))
    with Monitor() as monitor:rows=service.players(season=season)
    result=monitor.result();result.update(phase=phase,season=season,players=len(rows),equal=rows==json.loads((OUT/f'before_{season}_rows.json').read_text(encoding='utf8')))
    (OUT/f'resource_{phase}_{season}.json').write_text(json.dumps(result,indent=2),encoding='utf8')
else:
    values=[]
    for season in (3,10,20):
        for phase in ('before','after'):
            subprocess.run([sys.executable,str(Path(__file__).resolve()),phase,str(season)],check=True)
            values.append(json.loads((OUT/f'resource_{phase}_{season}.json').read_text(encoding='utf8')))
    (OUT/'resource_comparison.json').write_text(json.dumps(values,indent=2),encoding='utf8')
