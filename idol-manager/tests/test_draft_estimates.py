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
from idol_manager.draft import DraftEngine,DraftError
from idol_manager.draft_session import DraftSession
from idol_manager.draft_estimates import estimate,initialize_estimates,public_prospects,V9_STATEMENTS
from idol_manager.ai_policy import EstimatedDraftPolicy
from tests import test_draft_session as fixture
from tests import test_special_service as special_fixture


class EstimateRuleTests(unittest.TestCase):
    def test_all_values_always_contained_five_integers_and_boundaries(self):
        rng=random.Random(24)
        for value in range(101):
            for _ in range(20):
                e=estimate(value,rng)
                self.assertEqual(e.high-e.low+1,5)
                self.assertLessEqual(e.low,value);self.assertGreaterEqual(e.high,value)
                self.assertTrue(0<=e.low<=96 and e.high<=100)
        self.assertEqual(str(estimate(0,rng)),'0~4')
        self.assertEqual(str(estimate(100,rng)),'96~100')

    def test_min_max_middle_and_all_five_actual_positions(self):
        class Fixed:
            def __init__(self,value):self.value=value
            def randint(self,low,high):return self.value
        for low,position in ((74,4),(76,2),(78,0)):
            self.assertEqual(78-estimate(78,Fixed(low)).low,position)
        rng=random.Random(7)
        self.assertEqual({78-estimate(78,rng).low for _ in range(100)},set(range(5)))


class EstimateSessionTests(unittest.TestCase):
    setUp=fixture.DraftSessionTests.setUp

    def rows(self,sql,args=()):
        with closing(self.database.connect()) as c:return [tuple(r) for r in c.execute(sql,args)]

    def test_saved_stable_reloaded_and_estimated_overall_only_from_ranges(self):
        before=self.session.snapshot()
        self.assertEqual(len(before.prospects),200)
        self.assertEqual(len(self.rows('SELECT * FROM draft_estimates')),1600)
        self.assertEqual(before,DraftSession(DraftEngine(Database(self.path))).snapshot())
        for p in before.candidates:
            self.assertEqual(p.estimated_overall,round(sum((e.low+e.high)/2 for e in p.estimates)/8,1))
        original=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        for _ in range(5):self.assertEqual(before,self.session.snapshot())
        self.assertEqual(original,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        with closing(self.database.connect()) as c:
            with self.assertRaises(sqlite3.IntegrityError),c:c.execute('UPDATE draft_estimates SET low=low')

    def test_trusted_generation_ignores_pa_and_leaves_actuals_intact(self):
        original=self.rows('SELECT person_id,skill,value FROM abilities ORDER BY person_id,skill')
        with closing(self.database.connect()) as c,c:
            c.execute('DELETE FROM draft_estimates')
            def authorize(action,table,column,*_):
                if action==sqlite3.SQLITE_READ and (table,column) in (('abilities','potential'),('idols','archetype'),('idols','average')):return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize);initialize_estimates(c,rng=random.Random(3));c.set_authorizer(None)
            first=list(c.execute('SELECT * FROM draft_estimates ORDER BY person_id,skill'))
            c.execute('UPDATE abilities SET potential=100');c.execute('DELETE FROM draft_estimates')
            initialize_estimates(c,rng=random.Random(3))
            self.assertEqual([tuple(r) for r in first],[tuple(r) for r in c.execute('SELECT * FROM draft_estimates ORDER BY person_id,skill')])
        self.assertEqual(original,self.rows('SELECT person_id,skill,value FROM abilities ORDER BY person_id,skill'))

    def test_public_and_ai_reads_deny_actual_ca_pa_health_and_archetype(self):
        self.session.select_agency('ador');self.engine.start(rng=random.Random(4))
        turn=self.engine.state().next_turn
        if turn.agency_id=='ador':self.session.pick_player(self.session.snapshot().candidates[0].id,expected_pick_number=turn.pick_number)
        original=self.database.connect;reads=[]
        def connect():
            c=original()
            def authorize(action,table,column,*_):
                if action==sqlite3.SQLITE_READ:
                    reads.append((table,column))
                    if (table,column) in (('abilities','value'),('abilities','potential'),('idols','average'),('idols','health'),('idols','archetype')):return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize);return c
        self.session.policy=EstimatedDraftPolicy()
        with patch.object(self.database,'connect',side_effect=connect):
            candidates=self.session.snapshot().candidates
            expected=self.session.policy.choose(candidates)
            result=self.session.pick_ai_turn()
        self.assertEqual(result.person_id,expected)
        self.assertNotIn(('abilities','value'),reads)
        self.assertFalse(any(hasattr(candidates[0],key) for key in ('skills','potential','actual_average')))

    def test_exact_disclosure_only_after_owned_pick_never_pa(self):
        self.session.select_agency('ador');self.engine.start(rng=random.Random(4))
        person=self.session.snapshot().candidates[0].id
        with self.assertRaises(DraftError):self.session.revealed_player(person)
        other=None
        while self.engine.state().next_turn.agency_id!='ador':
            other=self.session.snapshot().candidates[0].id;turn=self.engine.state().next_turn
            self.engine.pick(turn.agency_id,other,expected_pick_number=turn.pick_number)
        if other:
            with self.assertRaises(DraftError):self.session.revealed_player(other)
        person=self.session.snapshot().candidates[0].id;turn=self.engine.state().next_turn
        expected=dict(self.rows('SELECT skill,value FROM abilities WHERE person_id=?',(person,)))
        self.session.pick_player(person,expected_pick_number=turn.pick_number)
        original=self.database.connect
        def connect():
            c=original();c.set_authorizer(lambda action,table,column,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table,column)==('abilities','potential') else sqlite3.SQLITE_OK);return c
        with patch.object(self.database,'connect',side_effect=connect):
            identity,skills,overall=self.session.revealed_player(person)
        self.assertEqual(skills,tuple(expected[s] for s in SKILLS));self.assertEqual(overall,round(sum(skills)/8,1))
        self.assertEqual(set(identity),{'id','name','age','photo_path'})

    def test_default_estimate_ai_completes_160_snake_and_preserves_40(self):
        self.session=DraftSession(self.engine);self.session.select_agency('ador');self.engine.start(rng=random.Random(4))
        original=self.rows('SELECT * FROM abilities ORDER BY person_id,skill');estimates=self.rows('SELECT * FROM draft_estimates ORDER BY person_id,skill')
        order=self.engine.turn_order()
        while self.engine.state().status!='completed':
            state=self.engine.state()
            if state.next_turn.agency_id=='ador':self.session.pick_player(self.session.snapshot().candidates[0].id,expected_pick_number=state.next_turn.pick_number)
            else:self.session.pick_ai_turn()
        self.session.validate_completion()
        self.assertEqual(self.engine.turn_order(),order);self.assertEqual(len(self.session.snapshot().candidates),40)
        self.assertEqual(original,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertEqual(estimates,self.rows('SELECT * FROM draft_estimates ORDER BY person_id,skill'))


class EstimateMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):special_fixture.SpecialServiceTests.setUpClass.__func__(cls)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'v8.sqlite3'
        special_fixture.fixture.copy_db(self.template,self.path)
        from idol_manager.special_service import SpecialService
        service=SpecialService(Database(self.path),seed_factory=lambda:1827);event=service.events()[0]['id'];service.start(event)
        for stage in ('upper','lower','final'):
            service.play(next(r['id'] for r in service.state(event)['rounds'] if r['stage']==stage))
        with closing(Database(self.path).connect()) as c,c:
            from tests.migration_fixtures import drop_finals
            drop_finals(c)
            c.execute('DROP TABLE draft_estimates');c.execute('PRAGMA user_version=8')

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as c:
            return {t:sorted(c.execute(f'SELECT * FROM "{t}"').fetchall()) for t, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}

    def test_completed_v8_regular_special_conditions_and_all_old_rows_preserved(self):
        before=self.snapshot();db=Database(self.path);after=self.snapshot()
        self.assertTrue(db.last_backup_path.is_file())
        self.assertEqual(len(before['draft_picks']),160);self.assertGreater(len(before['match_results']),0)
        self.assertEqual(len(before['special_rounds']),3)
        for table,rows in before.items():self.assertEqual(rows,after[table],table)
        self.assertEqual(len(after['draft_estimates']),1600)
        self.assertIsNone(Database(self.path).last_backup_path)
        self.assertEqual(after,self.snapshot())
        with closing(db.connect()) as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_failed_migration_rolls_back_ranges_schema_and_all_old_records(self):
        before=self.snapshot()
        with patch('idol_manager.migrations.V9_STATEMENTS',V9_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):Database(self.path)
        self.assertEqual(before,self.snapshot())
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],8)
