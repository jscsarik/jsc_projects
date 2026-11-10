"""Instrument the existing bounded runner, without replacing game logic."""
from contextlib import ExitStack
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import argparse,time,sys,statistics,math,inspect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.release_qa import Monitor,save,OUT,protect_connections
from tools.simulate_game import Simulation,csvfile
from idol_manager import database,calendar_service,match_service,development_service,finance_service,annual_recruitment

def run(name,seed,resume=False):
    protect_connections();measurements=defaultdict(list)
    def wrap(label,fn):
        def call(*a,**kw):
            start=time.perf_counter()
            try:return fn(*a,**kw)
            finally:measurements[label].append(time.perf_counter()-start)
        return call
    targets=[(database.Database,'create_game','new_game'),(calendar_service.CalendarService,'advance_day','advance_day'),
        (calendar_service.CalendarService,'_ensure_season','schedule_ensure'),(match_service.MatchService,'play','match_play'),
        (match_service.MatchService,'_store_result','match_store'),(development_service,'settle_week','weekly_growth'),
        (development_service,'settle_aging','aging'),(development_service,'settle_birthday','birthday'),
        (finance_service,'settle_payroll','payroll'),(annual_recruitment,'intake','intake70')]
    with Monitor() as monitor,ExitStack() as stack:
        for obj,key,label in targets:
            replacement=wrap(label,getattr(obj,key))
            if isinstance(inspect.getattr_static(obj,key),staticmethod):replacement=staticmethod(replacement)
            stack.enter_context(patch.object(obj,key,replacement))
        args=SimpleNamespace(output=ROOT/'diagnostics'/name,seed=seed,seasons=1,budget_seconds=900,resume=resume,allow_long_run=False)
        status=Simulation(args).run()
    metrics=[]
    for operation,v in measurements.items():
        s=sorted(v);metrics.append(dict(operation=operation,count=len(v),mean=statistics.mean(v),median=statistics.median(v),p95=s[math.ceil(len(s)*.95)-1],maximum=max(v),p95_limit='small n' if len(v)<20 else 'nearest rank'))
    csvfile(OUT/(name+'_timings.csv'),metrics);save(name+'_resources.json',monitor.result())
    return status

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--seed',type=int,default=260029);p.add_argument('--resume',action='store_true');a=p.parse_args()
    raise SystemExit(0 if run(a.name,a.seed,a.resume)=='completed' else 1)
