"""Fatigue/injury tests use disposable SQLite saves exclusively."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import json
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.condition_rules import (PublicCondition,fatigue_penalty,injury_probability,
    projected_streak,registration_multiplier,recovery_day)
from idol_manager.conditions import (public_condition,record_appearance,finish_day,enter_day,
    risk_event,promotion_allowed,repair_ai_leaders)
from idol_manager.condition_schema import CONDITION_TABLES,V7_STATEMENTS
from idol_manager.config import SKILLS
from idol_manager.database import Database
from idol_manager.calendar_service import CalendarService,CalendarError
from idol_manager.match_service import MatchService
from idol_manager.match_types import MatchError,MatchPlayer
from idol_manager.lineup_planning import ScheduleAwareLineup,PublicFixture,expected_success
from idol_manager.squads import SquadService,SquadError
from tests import test_matches as fixture


class RuleTests(unittest.TestCase):
    def test_fatigue_days_one_to_five_and_probability_floor(self):
        self.assertEqual([fatigue_penalty(i) for i in range(1,6)],[0,0,.1,.2,.3])
        self.assertEqual(fatigue_penalty(200),1)
        self.assertEqual(projected_streak(2,1,2),1)
        self.assertEqual(projected_streak(2,1,3),2)
        self.assertEqual(projected_streak(2,1,4),1)

    def test_representative_uses_effective_main_skill_and_keeps_five_player_leader_rule(self):
        from idol_manager.match_policy import choose_representative
        players=(MatchPlayer('a','team','a',100,(100,)*8),MatchPlayer('b','team','b',100,(80,)*8))
        self.assertEqual(choose_representative(players,('vocal','dance'),2,'a',penalties={'a':.3}),'b')
        self.assertEqual(choose_representative(players,('vocal','dance'),5,'a',penalties={'a':.3}),'a')

    def test_exact_injury_percentages_and_registration_steps(self):
        self.assertEqual([registration_multiplier(i) for i in range(1,7)],[1,1,10,20,30,40])
        self.assertAlmostEqual(injury_probability(80,1,'match'),.002)
        self.assertAlmostEqual(injury_probability(80,1,'first_rest'),.001)
        self.assertAlmostEqual(injury_probability(80,1,'second'),.002/3)
        for week,mult in ((3,10),(4,20),(5,30),(6,40)):
            self.assertAlmostEqual(injury_probability(80,week,'match'),.002*mult)
        self.assertEqual(injury_probability(0,100,'match'),1)
        self.assertEqual(injury_probability(100,100,'match'),0)
        self.assertEqual(recovery_day(2),8)
        self.assertEqual(recovery_day(6),8)

    def test_ai_can_rest_a_player_for_public_future_fixtures(self):
        players=tuple(MatchPlayer(str(i),'agency',str(i),100,(value,)*8) for i,value in enumerate((100,96,90,85,80)))
        conditions={p.id:PublicCondition(1,2,3,.1,1,False,None,None,0) for p in players}
        # Three consecutive days: reserving a high-value performer for the
        # later two five-player fixtures can beat today's greedy choice.
        future=tuple(PublicFixture(day,('vocal','dance'),5) for day in range(3,7))
        policy=ScheduleAwareLineup()
        chosen=policy.select_for_match(players,1,('vocal','dance'),None,conditions,2,future)
        self.assertNotEqual(chosen[0].id,'0')
        self.assertEqual(chosen,policy.select_for_match(players,1,('vocal','dance'),None,conditions,2,future))


class ConditionServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MatchServiceTests.setUpClass.__func__(cls)

    setUp=fixture.MatchServiceTests.setUp
    rows=fixture.MatchServiceTests.rows

    def execute(self,sql,args=()):
        with closing(self.db.connect()) as c,c:c.execute(sql,args)

    def first(self):
        return self.rows("SELECT person_id FROM roster_memberships WHERE career_status='first_team' ORDER BY person_id LIMIT 1")[0]['person_id']

    def dump_conditions(self):
        return {table:self.rows(f'SELECT * FROM {table} ORDER BY 1') for table in CONDITION_TABLES}

    def test_appearance_same_day_once_rest_and_restart(self):
        person=self.first()
        with closing(self.db.connect()) as c,c:
            for day in (2,2,3,4,5,6):
                record_appearance(c,person,day)
            self.assertEqual(public_condition(c,person,6).streak,5)
            self.assertEqual(public_condition(c,person,6).penalty,.3)
            finish_day(c,7)
            self.assertEqual(public_condition(c,person,8).streak,0)
            self.assertEqual(public_condition(c,person,8).penalty,0)
        restarted=Database(self.path)
        with closing(restarted.connect()) as c:
            self.assertEqual(public_condition(c,person,8).last_day,6)
        self.assertEqual(len(self.rows('SELECT * FROM appearance_days WHERE person_id=?',(person,))),5)

    def test_probability_snapshot_all_skills_leader_and_resume(self):
        self.execute('UPDATE player_conditions SET last_appearance_day=1,consecutive_days=2')
        originals=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        match,seed=self.service._prepare(self.identity,None,None)
        self.assertTrue(all(abs(match.probabilities[p.id][skill]-p.value(skill)/100*.9)<1e-12
        for team in match.teams for p in team.players for skill in SKILLS))
        self.execute('UPDATE player_conditions SET consecutive_days=8')
        result=self.service.play(self.identity)
        for event in result.events:
            self.assertEqual(event.probability,match.probabilities[event.person_id][event.skill])
        self.assertEqual(originals,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertEqual(result,MatchService(Database(self.path)).play(self.identity))
        self.assertEqual(sum(p['base_attempts'] for p in result.players),len(result.players)*60)

    def test_match_injury_is_atomic_post_match_and_idempotent(self):
        self.execute('UPDATE idols SET health=0')
        self.execute('UPDATE player_conditions SET registration_weeks=103,registration_week=0')
        result=self.service.play(self.identity)
        self.assertTrue(result.events)
        injured={r['person_id'] for r in self.rows('SELECT person_id FROM player_conditions WHERE injured=1')}
        self.assertEqual(injured,{p['person_id'] for p in result.players})
        before=self.dump_conditions()
        self.assertEqual(result,self.service.play(self.identity))
        self.assertEqual(before,self.dump_conditions())
        self.assertTrue(all(r['health']==0 for r in self.rows('SELECT health FROM idols')))
        self.assertEqual(before,{table:fixture.MatchServiceTests.rows(self,f'SELECT * FROM {table} ORDER BY 1') for table in CONDITION_TABLES})
        restarted=Database(self.path)
        with closing(restarted.connect()) as c:
            self.assertEqual({r[0] for r in c.execute('SELECT person_id FROM player_conditions WHERE injured=1')},injured)

    def test_injury_rejects_manual_lineup_and_ai_uses_eligible_only(self):
        agency=self.rows('SELECT agency_id FROM match_participants WHERE match_id=? ORDER BY agency_id',(self.identity,))[0]['agency_id']
        self.execute("UPDATE player_conditions SET injured=1,recovery_day=8 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team')",(agency,))
        forbidden=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team' LIMIT 1",(agency,))[0]['person_id']
        with self.assertRaises(MatchError):self.service.play(self.identity,lineups={agency:(forbidden,)})
        result=self.service.play(self.identity)
        self.assertEqual(result.resolution,'forfeit')
        self.assertEqual(result.loser_id,agency)
        self.assertFalse(self.rows('SELECT * FROM appearance_days'))

    def test_injured_short_roster_uses_only_remaining_first_team(self):
        agency=self.rows('SELECT agency_id FROM match_participants WHERE match_id=? ORDER BY agency_id',(self.identity,))[0]['agency_id']
        members=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team' ORDER BY person_id",(agency,))
        for row in members[1:]:
            self.execute('UPDATE player_conditions SET injured=1,recovery_day=8 WHERE person_id=?',(row['person_id'],))
        result=self.service.play(self.identity)
        selected={p['person_id'] for p in result.players}
        self.assertEqual([p['person_id'] for p in result.players if p['agency_id']==agency],[members[0]['person_id']])
        firsts={r['person_id'] for r in self.rows("SELECT person_id FROM roster_memberships WHERE career_status='first_team'")}
        self.assertTrue(selected<=firsts)

    def test_save_failure_rolls_back_injury_and_appearance_with_results(self):
        before=self.dump_conditions()
        from idol_manager.conditions import commit_match_conditions as real
        def fail(*args):
            real(*args)
            raise sqlite3.OperationalError('injected condition failure')
        with patch('idol_manager.match_service.commit_match_conditions',side_effect=fail):
            with self.assertRaises(MatchError):self.service.play(self.identity)
        self.assertEqual(before,self.dump_conditions())
        self.assertEqual(self.rows('SELECT * FROM match_results'),[])
        self.service.play(self.identity)

    def test_concurrent_completion_condition_events_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.service.play(self.identity),range(2)))
        self.assertEqual(results[0],results[1])
        n=len(results[0].players)
        self.assertEqual(len(self.rows("SELECT * FROM condition_events WHERE kind='match'")),n)
        self.assertEqual(len(self.rows('SELECT * FROM appearance_days')),n)

    def test_daily_risk_applies_only_nonparticipants_and_repeated_close_is_noop(self):
        result=self.service.play(self.identity)
        self.execute('UPDATE idols SET health=80')
        with closing(self.db.connect()) as c,c:
            finish_day(c,2)
        before=self.dump_conditions()
        with closing(self.db.connect()) as c,c:
            finish_day(c,2)
        self.assertEqual(before,self.dump_conditions())
        rows=self.rows("SELECT * FROM condition_events WHERE kind IN ('first_rest','second') AND absolute_day=2")
        self.assertEqual(len(rows),160-len(result.players))
        self.assertTrue(all(r['person_id'] not in {p['person_id'] for p in result.players} for r in rows))
        for r in rows:
            self.assertAlmostEqual(r['probability'],.001 if r['kind']=='first_rest' else .002/3)

    def test_week_charge_rest_reset_and_high_risk_one_week_retained(self):
        second=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='second_team' LIMIT 3")
        for person,weeks in zip(second,(3,4,6)):
            self.execute('UPDATE player_conditions SET registration_weeks=?,squad_since=0 WHERE person_id=?',(weeks,person['person_id']))
        with closing(self.db.connect()) as c,c:
            enter_day(c,7)
            self.assertEqual([public_condition(c,p['person_id'],7).registration_weeks for p in second],[0,4,6])
            enter_day(c,14)
            self.assertEqual([public_condition(c,p['person_id'],14).registration_weeks for p in second],[0,0,0])
            person=self.first()
            finish_day(c,14)
            weeks=public_condition(c,person,14).registration_weeks
            finish_day(c,15)
            self.assertEqual(public_condition(c,person,15).registration_weeks,weeks)

    def test_partial_second_team_week_does_not_reset_risk(self):
        person=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='second_team' LIMIT 1")[0]['person_id']
        self.execute('UPDATE player_conditions SET registration_weeks=3,squad_since=1 WHERE person_id=?',(person,))
        with closing(self.db.connect()) as c,c:
            enter_day(c,7)
            self.assertEqual(public_condition(c,person,7).registration_weeks,3)

    def test_monday_forced_down_recovery_and_return_lock(self):
        person=self.rows("SELECT person_id FROM squad_leaders WHERE agency_id='ador' AND squad='first_team'")[0]['person_id']
        with closing(self.db.connect()) as c,c:
            risk_event(c,key='test-injury',person=person,day=2,kind='match',probability=1,rng=random.Random(1))
            enter_day(c,7)
            self.assertTrue(public_condition(c,person,7).injured)
            self.assertFalse(promotion_allowed(c,person,14))
            self.assertTrue(promotion_allowed(c,person,21))
            enter_day(c,8)
            self.assertFalse(public_condition(c,person,8).injured)
            enter_day(c,8)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM condition_events WHERE person_id=? AND kind='recovery'",(person,)).fetchone()[0],1)
            self.assertEqual(c.execute('SELECT career_status FROM roster_memberships WHERE person_id=?',(person,)).fetchone()[0],'second_team')
            self.assertFalse(c.execute("SELECT 1 FROM squad_leaders WHERE agency_id='ador' AND squad='first_team'").fetchone())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team'").fetchone()[0],5)
        self.execute('UPDATE game_clock SET absolute_day=14')
        squads=SquadService(self.db);state=squads.snapshot()
        first=next(p.id for p in state.members if p.squad=='first_team')
        with self.assertRaisesRegex(SquadError,'복귀 제한'):squads.swap(first,person,expected_revision=state.revision)
        self.execute('UPDATE game_clock SET absolute_day=21')
        squads.swap(first,person,expected_revision=state.revision)

    def test_all_injured_capacity_and_no_false_recovery(self):
        self.execute('UPDATE player_conditions SET injured=1,injury_day=2,recovery_day=8')
        with closing(self.db.connect()) as c,c:enter_day(c,7)
        self.assertEqual(self.rows('SELECT COUNT(*) n FROM player_conditions WHERE injured=1')[0]['n'],310)
        for r in self.rows("SELECT agency_id,career_status,COUNT(*) n FROM roster_memberships WHERE agency_id IS NOT NULL AND career_status IN ('first_team','second_team') GROUP BY 1,2"):
            self.assertEqual(r['n'],5 if r['career_status']=='first_team' else 11)

    def test_ai_leader_vacancies_repaired_with_public_values_after_monday_swap(self):
        person=self.rows("SELECT person_id FROM squad_leaders WHERE agency_id!='ador' AND squad='first_team' LIMIT 1")[0]['person_id']
        self.execute('UPDATE player_conditions SET injured=1,injury_day=2,recovery_day=8 WHERE person_id=?',(person,))
        with closing(self.db.connect()) as c,c:
            enter_day(c,7)
            c.execute('UPDATE game_clock SET absolute_day=7')
            def authorize(action,table,column,*_):
                if action==sqlite3.SQLITE_READ and (table,column) in (('abilities','potential'),('idols','archetype')):return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize)
            repair_ai_leaders(c,7)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM squad_leaders WHERE agency_id!='ador'").fetchone()[0],18)
            self.assertFalse(c.execute('''SELECT 1 FROM squad_leaders l JOIN roster_memberships r ON r.person_id=l.person_id
                WHERE r.career_status!=l.squad OR r.agency_id!=l.agency_id''').fetchone())

    def test_first_doubleheader_injury_prevents_second_game_appearance(self):
        day=self.rows('SELECT week,weekday FROM scheduled_matches GROUP BY week,weekday HAVING COUNT(*)=10 LIMIT 1')[0]
        absolute=(day['week']-1)*7+day['weekday']
        self.execute('UPDATE game_clock SET absolute_day=?',(absolute,))
        self.calendar.ensure_current_schedule()
        self.execute('UPDATE idols SET health=0')
        self.execute('UPDATE player_conditions SET registration_weeks=200,registration_week=?',(absolute//7,))
        rows=self.rows('SELECT id,day_order FROM scheduled_matches WHERE week=? AND weekday=? ORDER BY day_order,match_order',(day['week'],day['weekday']))
        first=set();second=set()
        for row in rows:
            result=self.service.play(row['id'])
            (first if row['day_order']==1 else second).update(p['person_id'] for p in result.players)
        self.assertTrue(first)
        self.assertFalse(first&second)

    def test_calendar_cas_and_failure_roll_back_daily_risks(self):
        self.execute('UPDATE game_clock SET absolute_day=0')
        before=self.dump_conditions()
        with patch('idol_manager.calendar_service.enter_day',side_effect=ValueError('test rollback')):
            with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=0)
        self.assertEqual(before,self.dump_conditions())
        self.calendar.advance_day(expected_absolute_day=0)
        saved=self.dump_conditions()
        with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=0)
        self.assertEqual(saved,self.dump_conditions())

    def test_doubleheader_same_day_streak_but_two_match_injury_rolls(self):
        # Find an existing doubleheader; no real schedules are modified.
        day=self.rows('SELECT week,weekday FROM scheduled_matches GROUP BY week,weekday HAVING COUNT(*)=10 LIMIT 1')[0]
        absolute=(day['week']-1)*7+day['weekday']
        self.execute('UPDATE game_clock SET absolute_day=?',(absolute,))
        self.calendar.ensure_current_schedule()
        matches=self.rows('SELECT id FROM scheduled_matches WHERE week=? AND weekday=? ORDER BY day_order,match_order',(day['week'],day['weekday']))
        class First:
            def select(self,players,required,*_):return players[:required]
        service=MatchService(self.db,lineup_policy=First(),seed_factory=lambda:42)
        results=[service.play(m['id']) for m in matches]
        self.assertTrue(all(r['consecutive_days']==1 for r in self.rows('SELECT consecutive_days FROM player_conditions WHERE last_appearance_day=?',(absolute,))))
        self.assertEqual(self.rows("SELECT COUNT(*) n FROM condition_events WHERE kind='match'")[0]['n'],sum(len(r.players) for r in results))
        self.assertTrue(self.rows("SELECT person_id FROM condition_events WHERE kind='match' GROUP BY person_id HAVING COUNT(*)=2"))

    def test_old_prepared_game_resumes_without_new_probabilities_or_injuries(self):
        match,seed=self.service._prepare(self.identity,None,None)
        self.execute('UPDATE match_runs SET condition_json=NULL WHERE match_id=?',(self.identity,))
        self.execute('UPDATE player_conditions SET last_appearance_day=1,consecutive_days=10,registration_weeks=200')
        self.execute('UPDATE idols SET health=0')
        result=self.service.play(self.identity)
        self.assertTrue(all(e.probability==match.probabilities[e.person_id][e.skill] for e in result.events))
        self.assertEqual(self.rows("SELECT * FROM condition_events WHERE kind='match'"),[])

