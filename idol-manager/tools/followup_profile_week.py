"""Measure seven real service days on a disposable historical QA snapshot."""
from pathlib import Path
from contextlib import closing
import argparse,cProfile,pstats,sqlite3,sys,time,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.service import GameService
from tools.release_qa import protect_connections,OUT,save

def main():
    p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('source',type=Path);a=p.parse_args()
    protect_connections();source=a.source.resolve()
    if not source.is_relative_to(ROOT/'diagnostics'):raise ValueError('QA sources only')
    folder=ROOT/'diagnostics'/('followup_perf_'+a.label)
    folder.mkdir(exist_ok=False);target=folder/'simulation.sqlite3'
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)
    service=GameService(ROOT/'diagnostics/followup_world',target);start=service.calendar.state().date.absolute_day
    def week():
        for _ in range(7):
            day=service.calendar.state().date
            for f in service.matches.fixtures():
                if f.status!='completed':service.matches.play(f.id)
            for event in service.specials.events():
                if event['today'] and event['status']!='completed':
                    service.specials.start(event['id'])
                    while True:
                        rounds=[r for r in service.specials.state(event['id'])['rounds'] if r['status']!='completed']
                        if not rounds:break
                        service.specials.play(rounds[0]['id'])
            service.calendar.advance_day(expected_absolute_day=day.absolute_day)
    profile=cProfile.Profile();t=time.perf_counter();profile.runcall(week);elapsed=time.perf_counter()-t
    profile.dump_stats(OUT/('profile_week_'+a.label+'.prof'))
    with (OUT/('profile_week_'+a.label+'.txt')).open('w',encoding='utf8') as out:pstats.Stats(profile,stream=out).sort_stats('cumulative').print_stats(35)
    save('profile_week_'+a.label+'.json',dict(day=start,elapsed_seconds=elapsed,source=str(source),scope='7 real days on separate DB; cProfile overhead included'))
    print(elapsed)
if __name__=='__main__':main()
