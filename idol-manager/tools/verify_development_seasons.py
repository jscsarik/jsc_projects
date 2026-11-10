"""Real multi-season simulation, including growth, aging, trainees and playoffs."""
from collections import Counter
from contextlib import closing
from itertools import count
from pathlib import Path
import json,random,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.config import load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.squads import SquadService
from idol_manager.calendar_service import CalendarService
from idol_manager.match_service import MatchService
from idol_manager.special_service import SpecialService
from idol_manager.finals_service import FinalsService
from idol_manager.conditions import sync_rosters
from idol_manager.game_clock import GameDate,DAYS_PER_SEASON


def main(seasons=3):
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='idol_development_seasons_') as folder:
        db=Database(Path(folder)/'simulation.sqlite3')
        people=tuple(Person(str(i),f'시뮬 인물{i}',f'시뮬 인물{i}',f'missing/{i}.png') for i in range(310))
        db.create_game(people,load_settings(),random.Random(55))
        draft=DraftEngine(db);DraftSession(draft).select_agency('ador');draft.start(rng=random.Random(6))
        for number,p in enumerate(draft.available_candidates()[:160],1):draft.pick(draft.state().next_turn.agency_id,p.id,expected_pick_number=number)
        squads=SquadService(db);squads.confirm_initial(tuple(m.id for m in squads.snapshot().members[:5]))
        with closing(db.connect()) as c,c:
            c.execute("UPDATE condition_runtime SET seed='growth-real-injuries'")
            c.execute("UPDATE development_runtime SET seed='growth-multi-season'")
            candidates=[r[0] for r in c.execute("SELECT person_id FROM roster_memberships WHERE career_status='unassigned' ORDER BY person_id LIMIT 10")]
            agencies=[r[0] for r in c.execute('SELECT id FROM agencies ORDER BY id')]
            c.executemany("UPDATE roster_memberships SET career_status='trainee',agency_id=? WHERE person_id=?",list(zip(agencies,candidates)))
            sync_rosters(c,0,'simulation_trainee_fixture')
            original={r['person_id']:r['age'] for r in c.execute('SELECT person_id,age FROM idols')}
            potentials=[tuple(r) for r in c.execute('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')]
            initial={(r[0],r[1]):r[2] for r in c.execute('SELECT person_id,skill,value FROM abilities')}
            funds=[tuple(r) for r in c.execute('SELECT * FROM agencies ORDER BY id')]
            estimates=[tuple(r) for r in c.execute('SELECT * FROM draft_estimates ORDER BY person_id,skill')]
        calendar=CalendarService(db,rng=random.Random(88));calendar.ensure_current_schedule()
        seeds=count(100);matches=MatchService(db,seed_factory=lambda:next(seeds));specials=SpecialService(db,seed_factory=lambda:next(seeds));finals=FinalsService(db,seed_factory=lambda:next(seeds))
        while calendar.state().date.absolute_day<seasons*DAYS_PER_SEASON:
            day=calendar.state().date
            for r in finals.rows():
                if r['status']!='completed':finals.play(r['id'])
            if day.weekday()==0:
                for squad in ('first_team','second_team'):
                    state=squads.snapshot()
                    if not dict(state.leaders).get(squad):
                        members=[p for p in state.members if p.squad==squad]
                        squads.set_leader(squad,max(members,key=lambda p:p.leadership).id,expected_revision=state.revision)
            for f in matches.fixtures():matches.play(f.id)
            for event in specials.events():
                if not event['today']:continue
                specials.start(event['id'])
                for stage in ('upper','lower','final'):
                    specials.play(next(r['id'] for r in specials.state(event['id'])['rounds'] if r['stage']==stage))
            calendar.advance_day(expected_absolute_day=day.absolute_day)
            if day.day_in_season==216:print(f'Season {day.season} completed',flush=True)
        with closing(db.connect()) as c:
            assert potentials==[tuple(r) for r in c.execute('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')]
            assert [(r[0],r[1],r[2]) for r in funds]==[tuple(r) for r in c.execute('SELECT id,name,logo_path FROM agencies ORDER BY id')]
            for agency,_,_,opening in funds:
                delta=c.execute('SELECT COALESCE(SUM(cash_delta),0) FROM finance_ledger WHERE agency_id=?',(agency,)).fetchone()[0]
                assert c.execute('SELECT funds_krw FROM agencies WHERE id=?',(agency,)).fetchone()[0]==opening+delta
            assert estimates==[tuple(r) for r in c.execute('SELECT * FROM draft_estimates ORDER BY person_id,skill')]
            assert all(r['age']==original[r['person_id']]+seasons for r in c.execute('SELECT person_id,age FROM idols'))
            assert c.execute('SELECT 1 FROM abilities WHERE value<0 OR value>potential LIMIT 1').fetchone() is None
            totals=Counter()
            for r in c.execute('SELECT person_id,deltas_json FROM development_results'):
                for skill,delta in zip(('vocal','dance','rap','entertainment','appearance','physique','intelligence','leadership'),json.loads(r[1])):totals[(r[0],skill)]+=delta
            assert all(initial[(r[0],r[1])]+totals[(r[0],r[1])]==r[2] for r in c.execute('SELECT person_id,skill,value FROM abilities'))
            assert c.execute("SELECT COUNT(*) FROM roster_memberships WHERE career_status='trainee'").fetchone()[0]==10
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
            report={'seasons':seasons,'date':str(calendar.state().date),'regular_games':c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],
                'specials':c.execute("SELECT COUNT(*) FROM special_events WHERE status='completed'").fetchone()[0],
                'final_games':c.execute("SELECT COUNT(*) FROM final_contests WHERE status='completed'").fetchone()[0],
                'trophies':c.execute("SELECT COUNT(*) FROM season_honors WHERE kind='champion'").fetchone()[0],
                'settlements':[tuple(r) for r in c.execute('SELECT kind,COUNT(*) FROM development_settlements GROUP BY kind')],
                'result_rows':c.execute('SELECT COUNT(*) FROM development_results').fetchone()[0],
                'injury_events':c.execute("SELECT COUNT(*) FROM condition_events WHERE kind='match' AND occurred=1").fetchone()[0],
                'trainees_remain_trainees':True,'ca_pa_valid':True,'potential_estimates_preserved':True,'funds_match_finance_ledger':True,'ledger_balances':True,
                'annual_age_increase_exact':True,'sqlite_integrity':'ok','actual_save_modified':False,'seconds':round(time.monotonic()-started,3)}
            assert report['regular_games']==585*seasons and report['specials']==6*seasons and report['trophies']==seasons
        (ROOT/'.test-artifacts/growth_multi_season.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
