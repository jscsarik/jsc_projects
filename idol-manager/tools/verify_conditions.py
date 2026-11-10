"""Deterministic partial-season simulation in a NEW disposable game only."""
from contextlib import closing
from pathlib import Path
import json
from itertools import count
import random
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from idol_manager.config import ROOT,load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.calendar_service import CalendarService,CalendarError
from idol_manager.match_service import MatchService
from idol_manager.squads import SquadService


def simulate(seed=20261027):
    with tempfile.TemporaryDirectory(prefix='idol_condition_simulation_') as folder:
        db=Database(Path(folder)/'simulation.sqlite3')
        db.create_game(tuple(Person(f'sim-{i}',f'가상{i}',f'가상{i}',f'not-present/{i}.png') for i in range(310)),load_settings(),random.Random(55))
        draft=DraftEngine(db);DraftSession(draft).select_agency('ador');draft.start(rng=random.Random(6))
        for number,person in enumerate(draft.available_candidates()[:160],1):
            draft.pick(draft.state().next_turn.agency_id,person.id,expected_pick_number=number)
        squads=SquadService(db);squads.confirm_initial(tuple(m.id for m in squads.snapshot().members[:5]))
        with closing(db.connect()) as c,c:c.execute('UPDATE condition_runtime SET seed=?',(str(seed),))
        calendar=CalendarService(db,rng=random.Random(88));calendar.ensure_current_schedule()
        seeds=count(seed)
        matches=MatchService(db,seed_factory=lambda:next(seeds))
        with closing(db.connect()) as c:
            immutable={t:sorted(tuple(r) for r in c.execute(f'SELECT * FROM {t}')) for t in ('people','idols','abilities','agencies','draft_picks','draft_turns')}
        played=0;max_streak=0;max_penalty=0;min_available=5
        while True:
            day=calendar.state().date
            # Leadership vacancies after mandatory injury swaps are filled
            # through the same player-facing Monday service, never raw SQL.
            if day.weekday()==0:
                for squad in ('first_team','second_team'):
                    snapshot=squads.snapshot()
                    if not dict(snapshot.leaders).get(squad):
                        person=next(m.id for m in snapshot.members if m.squad==squad)
                        squads.set_leader(squad,person,expected_revision=snapshot.revision)
            for match in matches.fixtures():
                result=matches.play(match.id);played+=1
                self_check=matches.play(match.id)
                assert result==self_check
                assert all(p['base_attempts']==60 for p in result.players)
                with closing(db.connect()) as c:
                    context=json.loads(c.execute('SELECT condition_json FROM match_runs WHERE match_id=?',(match.id,)).fetchone()[0])
                    for condition in context['public'].values():
                        assert not condition['injured']
                        max_streak=max(max_streak,condition['projected_days'])
                        max_penalty=max(max_penalty,condition['penalty'])
                    available=c.execute("SELECT MIN(n) FROM (SELECT r.agency_id,COUNT(*) n FROM roster_memberships r JOIN player_conditions p ON p.person_id=r.person_id WHERE r.career_status='first_team' AND p.injured=0 GROUP BY r.agency_id)").fetchone()[0]
                    min_available=min(min_available,available)
            try:calendar.advance_day(expected_absolute_day=day.absolute_day)
            except CalendarError as error:
                assert day.absolute_day==27 and '특별전' in str(error),str(error)
                break
        with closing(db.connect()) as c:
            for table,before in immutable.items():assert before==sorted(tuple(r) for r in c.execute(f'SELECT * FROM {table}')),table
            assert c.execute('SELECT COUNT(*) FROM scheduled_matches').fetchone()[0]==585
            assert c.execute("SELECT COUNT(*) FROM special_events WHERE status='scheduled'").fetchone()[0]==6
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            risk_rows=c.execute("SELECT kind,COUNT(*),SUM(occurred),SUM(probability) FROM condition_events WHERE kind IN('match','first_rest','second') GROUP BY kind").fetchall()
            report={'completed_matches':played,'final_date':str(calendar.state().date),'max_consecutive_appearance_days':max_streak,
                    'max_fatigue_penalty':max_penalty,'minimum_available_first_team':min_available,
                    'injury_rolls':{r[0]:{'trials':r[1],'injuries':r[2],'expected_injuries':round(r[3],4)} for r in risk_rows},
                    'recovered':c.execute("SELECT COUNT(*) FROM condition_events WHERE kind='recovery'").fetchone()[0],
                    'monday_roster_moves':c.execute("SELECT COUNT(*) FROM condition_events WHERE kind='roster' AND details_json LIKE '%injury_monday%'").fetchone()[0],
                    'regular_schedule':585,'special_events_still_pending':6,'original_data_preserved':True,'foreign_key_check':'ok'}
            return dict(report,seed=seed)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.runs<=20:parser.error('--runs must be 1..20')
    runs=[simulate(20261027+10000*i) for i in range(args.runs)]
    totals={kind:{field:round(sum(r['injury_rolls'][kind][field] for r in runs),4)
                  for field in ('trials','injuries','expected_injuries')} for kind in ('match','first_rest','second')}
    report={'runs':runs,'total_matches':sum(r['completed_matches'] for r in runs),'injury_roll_totals':totals}
    target=ROOT/'.test-artifacts/fatigue_simulation.json';target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
