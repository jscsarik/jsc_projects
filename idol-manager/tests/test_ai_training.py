"""Focused AI training checks on disposable fixture saves only."""
import unittest,json,sqlite3
from contextlib import closing
from unittest.mock import patch
from idol_manager.ai_training import plan,available_budget
from idol_manager.training_service import TrainingService,FOCUS_COST
from idol_manager.training_policy import choose,priorities
from idol_manager.config import SKILLS
from idol_manager.database import Database
from tests import test_training as fixture

class AITrainingTests(unittest.TestCase):
    setUpClass=classmethod(fixture.TrainingTests.setUpClass.__func__)
    setUp=fixture.TrainingTests.setUp
    day=fixture.TrainingTests.day;rows=fixture.TrainingTests.rows;dump=fixture.TrainingTests.dump
    settle=fixture.TrainingTests.settle

    def run_ai(self,deny_private=False):
        with closing(self.db.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE')
            if deny_private:
                c.set_authorizer(lambda action,table,column,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and column in ('potential','archetype','special_prospect') else sqlite3.SQLITE_OK)
            plan(c,self.base)

    def test_all_nine_train_second_only_public_data_reload_and_once(self):
        self.day(1)
        before=self.rows('SELECT * FROM abilities')
        funds=self.rows("SELECT funds_krw FROM agencies WHERE id='jyp'")[0][0]
        self.run_ai(deny_private=True)
        self.assertEqual(self.rows('SELECT * FROM abilities'),before)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM training_sheets WHERE confirmed=1'),[(9,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM training_choices WHERE agency_id='ador'"),[(0,)])
        expected=self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id!='ador' AND career_status='second_team'")[0][0]
        self.assertEqual(self.rows('SELECT COUNT(*) FROM training_choices WHERE skill IS NOT NULL'),[(expected,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM training_choices t JOIN roster_memberships r ON r.person_id=t.person_id WHERE r.career_status!='second_team' OR r.agency_id!=t.agency_id"),[(0,)])
        self.assertEqual(funds-self.rows("SELECT funds_krw FROM agencies WHERE id='jyp'")[0][0],11*FOCUS_COST)
        saved=self.dump();self.run_ai();self.assertEqual(saved,self.dump())
        loaded=TrainingService(Database(self.path));self.assertTrue(loaded.state('jyp')['confirmed'])
        self.assertEqual(sum(p['focus'] is not None for p in loaded.state('jyp')['players']),11)

    def test_limited_cash_preserves_obligations_and_uses_priority(self):
        self.day(1)
        with closing(self.db.connect()) as c,c:
            d=self.service.calendar.state().date
            balance=c.execute("SELECT funds_krw FROM agencies WHERE id='jyp'").fetchone()[0]
            reserve=balance-available_budget(c,'jyp',d,'balanced')
            c.execute("UPDATE agencies SET funds_krw=? WHERE id='jyp'",(reserve+2*FOCUS_COST,))
        players=[dict(id=p['id'],skills=p['skills'],career_status=p['career_status']) for p in self.service.training.state('jyp')['players']]
        expected=choose(players,2*FOCUS_COST)
        self.run_ai()
        self.assertEqual(dict(self.rows("SELECT person_id,skill FROM training_choices WHERE agency_id='jyp'")),expected)
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='jyp'"),[(reserve,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE agency_id='jyp' AND kind='focus_training'"),[(2,)])

    def test_insufficient_cash_debt_and_wrong_day_skip(self):
        before=self.dump();self.run_ai();self.assertEqual(before,self.dump())
        self.day(1)
        with patch('idol_manager.ai_training.debt',return_value=1):self.run_ai()
        self.assertEqual(self.rows('SELECT COUNT(*) FROM training_sheets WHERE confirmed=1'),[(9,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM training_choices'),[(0,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE kind='focus_training'"),[(0,)])
        self.day(8)
        with closing(self.db.connect()) as c,c:c.execute("UPDATE agencies SET funds_krw=149999 WHERE id!='ador'")
        self.run_ai();self.assertEqual(self.rows('SELECT COUNT(*) FROM training_choices'),[(0,)])

    def test_calendar_tuesday_hook_monday_results_and_no_duplicate(self):
        self.day(0)
        self.service.calendar.advance_day(expected_absolute_day=0)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM training_sheets WHERE confirmed=1'),[(9,)])
        self.service.calendar.advance_day(expected_absolute_day=1)
        choices=self.rows("SELECT person_id,skill FROM training_choices WHERE agency_id='jyp'")
        self.assertEqual(len(choices),11)
        self.settle()
        for person,skill in choices:
            records=self.service.training.details('jyp',person)
            self.assertTrue(any(r['kind']=='집중 훈련' and r['skill']==skill for r in records))
        before=self.dump();self.service.development.settle_current();self.assertEqual(before,self.dump())
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE agency_id='jyp' AND kind='focus_training'"),[(11,)])

    def test_team_distribution_style_and_caps_change_priority(self):
        player=dict(id='target',career_status='second_team',skills=[60,65,65,65,65,65,65,65])
        def team(weak):
            values=[90]*8;values[weak]=30
            return [player]+[dict(id=str(i),career_status='first_team',skills=values) for i in range(5)]
        self.assertEqual(choose(team(0),FOCUS_COST)['target'],'vocal')
        self.assertEqual(choose(team(1),FOCUS_COST)['target'],'dance')
        self.assertNotEqual(priorities(team(0),'stable')[0][0],priorities(team(0),'aggressive')[0][0])
        full=dict(id='cap',career_status='second_team',skills=[100]*8)
        self.assertEqual(choose([full],FOCUS_COST),{})

    def test_calendar_failure_rolls_back_all_ai_plans_and_payments(self):
        self.day(0);before=self.dump()
        from idol_manager.training_service import journal
        calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise ValueError('test write failure')
            return journal(*args,**kwargs)
        with patch('idol_manager.training_service.journal',side_effect=fail_second):
            with self.assertRaises(ValueError):self.service.calendar.advance_day(expected_absolute_day=0)
        self.assertEqual(before,self.dump())
