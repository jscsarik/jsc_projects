from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import json
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.config import ROOT,SKILLS
from idol_manager.database import Database
from idol_manager.calendar_service import CalendarService,CalendarError
from idol_manager.match_service import MatchService
from idol_manager.match_types import MatchError
from idol_manager.special_service import SpecialService
from idol_manager.special_schema import SPECIAL_TABLES,V8_STATEMENTS
from tests import test_matches as fixture


class SpecialServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MatchServiceTests.setUpClass.__func__(cls)
        db=Database(cls.template);calendar=CalendarService(db,rng=random.Random(88));matches=MatchService(db,seed_factory=lambda:73)
        # Real regular results through the first special Sunday, not raw status edits.
        with patch('idol_manager.conditions.injury_probability',return_value=0),patch('idol_manager.match_service.injury_probability',return_value=0):
            while calendar.state().date.absolute_day<27:
                for match in matches.fixtures():matches.play(match.id)
                calendar.advance_day(expected_absolute_day=calendar.state().date.absolute_day)

    setUp=fixture.MatchServiceTests.setUp
    rows=fixture.MatchServiceTests.rows

    def setup_special(self):
        self.specials=SpecialService(self.db,seed_factory=lambda:1827)
        self.event=self.specials.events()[0]['id']
        self.specials.start(self.event)
        return self.specials.state(self.event)

    def execute(self,sql,args=()):
        with closing(self.db.connect()) as c,c:c.execute(sql,args)

    def protected(self):
        tables=('people','idols','abilities','agencies','roster_memberships','squad_leaders','draft_picks','draft_turns',
                'scheduled_matches','match_runs','match_results','match_team_stats','match_player_stats','match_ability_stats','match_events')
        return {t:self.rows(f'SELECT * FROM {t} ORDER BY 1') for t in tables}

    def play_groups(self):
        for r in self.specials.state(self.event)['rounds']:
            if r['stage'] in ('upper','lower'):self.specials.play(r['id'])
        return next(r for r in self.specials.state(self.event)['rounds'] if r['stage']=='final')

    def test_six_preserved_types_dates_and_frozen_groups(self):
        before=self.rows('SELECT * FROM special_events ORDER BY week');state=self.setup_special()
        self.assertEqual([r['week'] for r in before],[4,8,12,16,20,24])
        order=[r['agency_id'] for r in self.service.standings(1)]
        self.assertEqual(state['groups'],{'upper':order[:5],'lower':order[5:]})
        self.specials.play(state['rounds'][0]['id'])
        self.specials.start(self.event)
        self.assertEqual(self.specials.state(self.event)['groups'],state['groups'])
        after=self.rows('SELECT * FROM special_events ORDER BY week')
        self.assertEqual([{k:v for k,v in r.items() if k!='status'} for r in before],[{k:v for k,v in r.items() if k!='status'} for r in after])

    def test_ten_each_priority_and_30_records_without_regular_changes(self):
        protected=self.protected();state=self.setup_special()
        result=self.specials.play(state['rounds'][0]['id'])
        self.assertEqual(len(result.players),50)
        self.assertTrue(all(p['base_attempts']==30 and p['main_attempts']==p['support_attempts']==15 for p in result.players))
        for agency in state['rounds'][0]['agencies']:
            first={r['person_id'] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team'",(agency,))}
            self.assertTrue(first<={p['person_id'] for p in result.players if p['agency_id']==agency})
        self.assertEqual(self.protected(),protected)

    def test_manual_priority_duplicate_and_injured_selection_validation(self):
        state=self.setup_special();own=next(r for r in state['rounds'] if 'ador' in r['agencies'])
        selection=self.specials.selection(own['id'])
        self.assertEqual(selection['count'],10);self.assertEqual(selection['first_count'],5)
        second=[o['player'].id for o in selection['options'] if o['squad']=='second_team']
        with self.assertRaises(MatchError):self.specials.play(own['id'],lineups={'ador':second[:10]})
        first=[o['player'].id for o in selection['options'] if o['squad']=='first_team']
        with self.assertRaises(MatchError):self.specials.play(own['id'],lineups={'ador':first+second[:4]+[first[0]]})
        injured=first[0]
        self.execute('UPDATE player_conditions SET injured=1,recovery_day=29 WHERE person_id=?',(injured,))
        with self.assertRaises(MatchError):self.specials.play(own['id'],lineups={'ador':first+second[:5]})
        result=self.specials.play(own['id'])
        self.assertNotIn(injured,{p['person_id'] for p in result.players})

    def test_followup_four_qualifiers_common_count_initial_pool_and_full_completion(self):
        protected=self.protected();self.setup_special();final=self.play_groups()
        groups=self.specials.state(self.event)['groups']
        expected=self.rows("SELECT t.agency_id FROM special_team_results t JOIN special_rounds r ON r.id=t.round_id WHERE r.event_id=? AND ((r.stage='upper' AND t.rank IN(4,5)) OR (r.stage='lower' AND t.rank IN(1,2)))",(self.event,))
        self.assertEqual(set(final['agencies']),{r['agency_id'] for r in expected})
        origin={r['person_id'] for r in self.rows('SELECT person_id FROM special_player_stats')}
        result=self.specials.play(final['id'])
        self.assertTrue({p['person_id'] for p in result.players}<=origin)
        self.assertTrue(all(p['base_attempts']==60 for p in result.players))
        self.assertEqual(self.specials.state(self.event)['status'],'completed')
        self.assertEqual(self.protected(),protected)
        potentials=self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')
        self.assertEqual(self.calendar.advance_day(expected_absolute_day=27).absolute_day,28)
        # The completed special itself preserves CA; the following Monday now
        # legitimately applies weekly development. Past results/PA stay fixed.
        after=self.protected()
        for table,rows in protected.items():
            if table not in ('idols','abilities','agencies','roster_memberships','squad_leaders'):self.assertEqual(after[table],rows,table)
        for row in self.rows('SELECT id,funds_krw FROM agencies'):
            total=self.rows('SELECT COALESCE(SUM(cash_delta),0) AS delta FROM finance_ledger WHERE agency_id=?',(row['id'],))[0]['delta']
            self.assertEqual(row['funds_krw'],1000000000+total)
        self.assertEqual(potentials,self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill'))
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_incomplete_special_blocks_day_even_after_two_groups(self):
        self.setup_special()
        with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=27)
        self.play_groups()
        with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=27)

    def test_standings_separate_points_negative_allowed_regular_wins_unchanged(self):
        before=self.service.standings(1);self.setup_special();final=self.play_groups();self.specials.play(final['id'])
        after=self.service.standings(1)
        for row in after:
            original=next(r for r in before if r['agency_id']==row['agency_id'])
            self.assertEqual((row['played'],row['wins'],row['losses'],row['regular_points']),(original['played'],original['wins'],original['losses'],original['regular_points']))
            self.assertEqual(row['points'],row['regular_points']+row['special_points'])
        self.assertTrue(any(r['special_points']<0 for r in after))
        summary=self.specials.final_summary(self.event)
        self.assertEqual(len(summary),10)
        self.assertEqual(sum(r['followup_rank'] is not None for r in summary),4)
        self.assertTrue(all(r['points']==r['group_points']+r['followup_points'] for r in summary))
        for row in summary:self.assertEqual(row['points'],next(r['special_points'] for r in after if r['agency_id']==row['agency_id']))

    def test_prepare_restart_completed_requery_idempotent(self):
        self.setup_special();identity=self.specials.state(self.event)['rounds'][0]['id']
        prepared=self.specials._prepare(identity,None)
        original=self.rows('SELECT * FROM special_rounds ORDER BY id')
        other=SpecialService(Database(self.path),seed_factory=lambda:9999)
        self.assertEqual(prepared,other._prepare(identity,None));self.assertEqual(original,self.rows('SELECT * FROM special_rounds ORDER BY id'))
        result=other.play(identity)
        with closing(self.db.connect()) as c:before=list(c.iterdump())
        with patch('idol_manager.special_service.calculate_contest',side_effect=AssertionError('reroll')):
            self.assertEqual(result,SpecialService(Database(self.path)).play(identity))
        with closing(self.db.connect()) as c:self.assertEqual(before,list(c.iterdump()))

    def test_concurrent_same_stage_commits_once(self):
        self.setup_special();identity=self.specials.state(self.event)['rounds'][0]['id']
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.specials.play(identity),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(len(self.rows('SELECT * FROM special_points')),5)
        self.assertEqual(len(self.rows("SELECT * FROM condition_events WHERE event_key LIKE 'special:%'")),50)

    def test_concurrent_start_and_distinct_groups_freeze_one_session_and_one_final(self):
        self.specials=SpecialService(self.db,seed_factory=lambda:1827);self.event=self.specials.events()[0]['id']
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:self.specials.start(self.event),range(2)))
        self.assertEqual(len(self.rows('SELECT * FROM special_sessions')),1)
        rows=self.specials.state(self.event)['rounds']
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda r:self.specials.play(r['id']),rows))
        self.assertEqual(len(self.rows("SELECT * FROM special_rounds WHERE stage='final'")),1)
        self.assertEqual(len(self.rows('SELECT * FROM special_points')),10)

    def test_followup_uses_original_second_team_and_rejects_new_reserves(self):
        self.setup_special();final=self.play_groups();agency=final['agencies'][0]
        original={r['person_id'] for r in self.rows('SELECT person_id FROM special_player_stats WHERE agency_id=?',(agency,))}
        outside=next(r['person_id'] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team'",(agency,)) if r['person_id'] not in original)
        self.execute("UPDATE player_conditions SET injured=1,recovery_day=29 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team')",(agency,))
        row=next(r for r in self.specials.state(self.event)['rounds'] if r['stage']=='final')
        # Original five reserves remain eligible after all first-team players
        # are injured. An unused reserve cannot be brought into this event.
        valid=sorted(original & {r['person_id'] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team'",(agency,))})[:row['required']]
        with self.assertRaises(MatchError):self.specials.play(row['id'],lineups={agency:(outside,*valid[1:])})
        result=self.specials.play(row['id'],lineups={agency:valid})
        actual={p['person_id'] for p in result.players if p['agency_id']==agency}
        self.assertEqual(actual,set(valid));self.assertTrue(actual<=original)

    def test_result_injury_points_and_final_creation_rollback_together(self):
        self.setup_special();identity=self.specials.state(self.event)['rounds'][0]['id']
        before=self.rows('SELECT * FROM player_conditions ORDER BY person_id')
        from idol_manager.special_service import commit_appearance_conditions as real
        def fail(*args,**kwargs):real(*args,**kwargs);raise sqlite3.OperationalError('injected')
        with patch('idol_manager.special_service.commit_appearance_conditions',side_effect=fail):
            with self.assertRaises(MatchError):self.specials.play(identity)
        self.assertEqual(self.rows('SELECT * FROM special_points'),[])
        self.assertEqual(self.rows('SELECT * FROM special_team_results'),[])
        self.assertEqual(self.rows('SELECT * FROM player_conditions ORDER BY person_id'),before)
        self.assertEqual(self.rows('SELECT status FROM special_rounds WHERE id=?',(identity,))[0]['status'],'prepared')
        self.specials.play(identity)

    def test_process_exit_during_prepare_or_final_commit_resumes_without_partial_records(self):
        self.setup_special();stages=self.specials.state(self.event)['rounds']
        for row,phase in zip(stages,('prepare','commit')):
            conditions=self.rows('SELECT * FROM player_conditions ORDER BY person_id')
            points=self.rows('SELECT * FROM special_points ORDER BY 1,2,3')
            code='''import os,sys
from pathlib import Path
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.special_service import SpecialService
from idol_manager.conditions import commit_appearance_conditions
def crash(*args,**kwargs):
    if sys.argv[3]=='commit':commit_appearance_conditions(*args,**kwargs)
    os._exit(23)
target='idol_manager.special_service.'+('calculate_contest' if sys.argv[3]=='prepare' else 'commit_appearance_conditions')
with patch(target,side_effect=crash):SpecialService(Database(Path(sys.argv[1]))).play(sys.argv[2])
'''
            child=subprocess.run([sys.executable,'-c',code,str(self.path),row['id'],phase],cwd=ROOT,capture_output=True,timeout=20)
            self.assertEqual(child.returncode,23,child.stderr)
            self.assertEqual(self.rows('SELECT status FROM special_rounds WHERE id=?',(row['id'],))[0]['status'],'prepared')
            self.assertEqual(conditions,self.rows('SELECT * FROM player_conditions ORDER BY person_id'))
            self.assertEqual(points,self.rows('SELECT * FROM special_points ORDER BY 1,2,3'))
            result=SpecialService(Database(self.path)).play(row['id'])
            self.assertEqual(result,self.specials.play(row['id']))

    def test_followup_creation_failure_rolls_back_second_group_and_its_points(self):
        self.setup_special();rows=self.specials.state(self.event)['rounds']
        self.specials.play(rows[0]['id']);points=self.rows('SELECT * FROM special_points ORDER BY agency_id')
        before=self.rows('SELECT * FROM player_conditions ORDER BY person_id')
        real=SpecialService._create_final
        def fail(c,event):real(c,event);raise sqlite3.OperationalError('after final content draw')
        with patch.object(SpecialService,'_create_final',side_effect=fail):
            with self.assertRaises(MatchError):self.specials.play(rows[1]['id'])
        self.assertEqual(points,self.rows('SELECT * FROM special_points ORDER BY agency_id'))
        self.assertEqual(before,self.rows('SELECT * FROM player_conditions ORDER BY person_id'))
        self.assertFalse(self.rows("SELECT * FROM special_rounds WHERE stage='final'"))
        self.specials.play(rows[1]['id'])
        self.assertEqual(len(self.rows("SELECT * FROM special_rounds WHERE stage='final'")),1)

    def test_fatigue_snapshot_injury_after_groups_excluded_from_followup(self):
        self.execute('UPDATE player_conditions SET last_appearance_day=26,consecutive_days=2,registration_weeks=200,registration_week=3')
        self.execute('UPDATE idols SET health=0')
        self.setup_special();state=self.specials.state(self.event)
        first=self.specials.play(state['rounds'][0]['id'])
        data=json.loads(self.rows('SELECT input_json FROM special_rounds WHERE id=?',(first.round_id,))[0]['input_json'])
        for team in data['teams']:
            for p in team['players']:
                for i,s in enumerate(SKILLS):
                    self.assertAlmostEqual(data['probabilities'][p['id']][s],p['skills'][i]/100*.9)
        second=self.specials.play(state['rounds'][1]['id'])
        final=next(r for r in self.specials.state(self.event)['rounds'] if r['stage']=='final')
        result=self.specials.play(final['id'])
        self.assertFalse(result.players)
        self.assertTrue(all(t['forfeit'] for t in result.teams))
        self.assertEqual(self.specials.state(self.event)['status'],'completed')
        for p in first.players+second.players:
            state=self.rows('SELECT consecutive_days FROM player_conditions WHERE person_id=?',(p['person_id'],))[0]
            self.assertEqual(state['consecutive_days'],3)

    def test_two_stages_same_day_no_extra_fatigue_and_daily_risk_not_duplicated(self):
        self.setup_special();final=self.play_groups();self.specials.play(final['id'])
        twice=self.rows('SELECT person_id,COUNT(*) n FROM special_player_stats GROUP BY person_id HAVING COUNT(*)=2')
        self.assertTrue(twice)
        for p in twice:
            rows=self.rows('SELECT consecutive_days FROM player_conditions WHERE person_id=?',(p['person_id'],))
            # Some players appeared Saturday: Sunday adds one day, never two.
            self.assertLessEqual(rows[0]['consecutive_days'],5)
            self.assertEqual(len(self.rows('SELECT * FROM appearance_days WHERE person_id=? AND absolute_day=27',(p['person_id'],))),1)
            self.assertEqual(len(self.rows("SELECT * FROM condition_events WHERE event_key LIKE 'special:%' AND person_id=?",(p['person_id'],))),2)
        self.calendar.advance_day(expected_absolute_day=27)
        actual={r['person_id'] for r in self.rows('SELECT person_id FROM special_player_stats')}
        rest={r['person_id'] for r in self.rows("SELECT person_id FROM condition_events WHERE absolute_day=27 AND event_key LIKE 'day:%'")}
        self.assertFalse(actual&rest)

    def test_sql_privacy_both_stages_no_potential_or_archetype(self):
        original=self.db.connect;reads=[]
        def connect():
            c=original()
            def authorize(action,table,column,*_):
                if action==sqlite3.SQLITE_READ:
                    reads.append((table,column))
                    if (table,column) in (('abilities','potential'),('idols','archetype')):return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize);return c
        with patch.object(self.db,'connect',side_effect=connect):
            self.setup_special();final=self.play_groups();self.specials.play(final['id'])
        self.assertNotIn(('abilities','potential'),reads)

    def test_start_other_day_rejected_without_group_changes(self):
        specials=SpecialService(self.db)
        before=self.rows('SELECT * FROM special_events ORDER BY id')
        with self.assertRaises(MatchError):specials.start(specials.events()[1]['id'])
        self.assertEqual(before,self.rows('SELECT * FROM special_events ORDER BY id'))
