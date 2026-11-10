"""Run all 585 regular games and six three-stage specials in a disposable save."""
from collections import Counter
from contextlib import closing
from itertools import count
from pathlib import Path
import hashlib
import json
import random
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.config import load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.squads import SquadService
from idol_manager.calendar_service import CalendarService,CalendarError
from idol_manager.match_service import MatchService
from idol_manager.special_service import SpecialService


def digest(c,sql):
    return hashlib.sha256(json.dumps([tuple(r) for r in c.execute(sql)],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def main(destination=None):
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='idol_special_full_season_') as folder:
        db=Database(Path(folder)/'simulation.sqlite3')
        people=tuple(Person(f'sim-{i}',f'가상 선수{i}',f'가상 선수{i}',f'missing/{i}.png') for i in range(310))
        db.create_game(people,load_settings(),random.Random(55))
        draft=DraftEngine(db);DraftSession(draft).select_agency('ador');draft.start(rng=random.Random(6))
        for number,p in enumerate(draft.available_candidates()[:160],1):draft.pick(draft.state().next_turn.agency_id,p.id,expected_pick_number=number)
        from idol_manager.market_service import MarketService
        market=MarketService(db)
        for n in market.negotiations('ador'):
            if n['purpose']=='founding' and n['status']=='open':
                p=next(p for p in market.public_people() if p['id']==n['person_id'])
                market.offer(n['id'],p['market']*11//10,1,request_id='verify:'+n['id'])
        squads=SquadService(db);squads.confirm_initial(tuple(m.id for m in squads.snapshot().members[:5]))
        with closing(db.connect()) as c,c:c.execute("UPDATE condition_runtime SET seed='20261028'")
        for role in ('first_team','second_team'):
            state=squads.snapshot();squads.set_leader(role,next(m.id for m in state.members if m.squad==role),expected_revision=state.revision)
        calendar=CalendarService(db,rng=random.Random(88))
        for day in range(-7,0):calendar.advance_day(expected_absolute_day=day)
        calendar.ensure_current_schedule()
        seeds=count(20261028);special_seeds=count(1827)
        matches=MatchService(db,seed_factory=lambda:next(seeds));specials=SpecialService(db,seed_factory=lambda:next(special_seeds))
        with closing(db.connect()) as c:
            protected={t:digest(c,f'SELECT * FROM {t} ORDER BY 1') for t in ('people','draft_picks','draft_turns')}
            potentials=digest(c,'SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')
            schedule=digest(c,'SELECT id,season,week,weekday,day_order,match_order,content_id,content_name,main_abilities_json,participants_min,participants_max FROM scheduled_matches ORDER BY id')
            special_schedule=digest(c,'SELECT id,season,week,weekday,event_type FROM special_events ORDER BY id')
        special_log=[];requeries=0
        while calendar.state().date.absolute_day<168:
            day=calendar.state().date
            if day.weekday()==0:
                for squad in ('first_team','second_team'):
                    snapshot=squads.snapshot()
                    if not dict(snapshot.leaders).get(squad):
                        p=next(m.id for m in snapshot.members if m.squad==squad)
                        squads.set_leader(squad,p,expected_revision=snapshot.revision)
            for fixture in matches.fixtures():
                result=matches.play(fixture.id)
                assert result==matches.play(fixture.id);requeries+=1
            for event in specials.events():
                if not event['today']:continue
                with closing(db.connect()) as c:
                    regular_before={t:digest(c,f'SELECT * FROM {t} ORDER BY 1') for t in ('match_runs','match_results','match_events','match_player_stats','match_team_stats','match_ability_stats')}
                try:calendar.advance_day(expected_absolute_day=day.absolute_day)
                except CalendarError:pass
                else:raise AssertionError('Unfinished special was skipped')
                specials.start(event['id'])
                for stage in ('upper','lower','final'):
                    row=next(r for r in specials.state(event['id'])['rounds'] if r['stage']==stage)
                    result=specials.play(row['id'])
                    assert result==SpecialService(Database(db.path)).play(row['id']);requeries+=1
                    assert all(p['base_attempts']==(60 if stage=='final' else 30) for p in result.players)
                with closing(db.connect()) as c:
                    for table,old in regular_before.items():assert old==digest(c,f'SELECT * FROM {table} ORDER BY 1'),table
                    assert all(tuple(r)==(5,11) for r in c.execute("SELECT SUM(career_status='first_team'),SUM(career_status='second_team') FROM roster_memberships WHERE agency_id IS NOT NULL GROUP BY agency_id"))
                    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
                special_log.append({'week':event['week'],'type':event['event_type'],'status':specials.state(event['id'])['status']})
                print(f"Special week {event['week']} completed",flush=True)
            calendar.advance_day(expected_absolute_day=day.absolute_day)
        with closing(db.connect()) as c:
            assert c.execute("SELECT COUNT(*) FROM scheduled_matches WHERE status='completed'").fetchone()[0]==585
            assert c.execute("SELECT COUNT(*) FROM special_events WHERE status='completed'").fetchone()[0]==6
            assert c.execute("SELECT COUNT(*) FROM special_rounds WHERE status='completed'").fetchone()[0]==18
            for table,old in protected.items():assert old==digest(c,f'SELECT * FROM {table} ORDER BY 1'),table
            assert potentials==digest(c,'SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')
            assert c.execute('SELECT 1 FROM abilities WHERE value<0 OR value>potential LIMIT 1').fetchone() is None
            assert schedule==digest(c,'SELECT id,season,week,weekday,day_order,match_order,content_id,content_name,main_abilities_json,participants_min,participants_max FROM scheduled_matches ORDER BY id')
            assert special_schedule==digest(c,'SELECT id,season,week,weekday,event_type FROM special_events ORDER BY id')
            league=matches.standings(1);assert all(r['played']==117 for r in league)
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            report={'regular_games':585,'special_events':special_log,'special_rounds':18,'final_date':str(calendar.state().date),
                'saved_result_requeries':requeries,'individual_special_appearances':c.execute('SELECT COUNT(*) FROM special_player_stats').fetchone()[0],
                'special_judgments':c.execute('SELECT COUNT(*) FROM special_judgments').fetchone()[0],
                'injuries_by_source':[dict(kind=r[0],trials=r[1],injuries=r[2]) for r in c.execute("SELECT kind,COUNT(*),SUM(occurred) FROM condition_events WHERE kind IN('match','first_rest','second') GROUP BY kind")],
                'league_standings':league,'protected_data_preserved':True,'all_specials_preserve_existing_regular_results':True,
                'regular_schedule_preserved':True,'special_schedule_preserved':True,'sqlite_integrity':'ok','foreign_keys':'ok',
                'seconds':round(time.monotonic()-started,3),'actual_save_modified':False}
        output=ROOT/'.test-artifacts/special_full_season.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if destination:
            import sqlite3
            with closing(db.connect()) as src,closing(sqlite3.connect(destination)) as dst:src.backup(dst)
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
