import unittest
from contextlib import closing
from tests import test_season32 as fixture
from idol_manager.conditions import reset_registration,enter_day,finish_day,public_condition
from idol_manager.condition_rules import required_rest_weeks,registration_multiplier
from unittest.mock import patch

class SeasonEndRegistrationTests(unittest.TestCase):
    setUpClass=classmethod(fixture.Season32Tests.setUpClass.__func__)
    setUp=fixture.Season32Tests.setUp
    day=fixture.Season32Tests.day
    def seed(self):
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE player_conditions SET registration_weeks=9,registration_week=28,complete_rest_weeks=1')
            first=c.execute("SELECT person_id FROM player_conditions WHERE squad='first_team' LIMIT 1").fetchone()[0]
            second=c.execute("SELECT person_id FROM player_conditions WHERE squad='second_team' LIMIT 1").fetchone()[0]
            c.execute('UPDATE player_conditions SET injured=1,injury_day=200,recovery_day=220,return_not_before=224 WHERE person_id=?',(second,))
        return first,second
    def test_offseason_entry_zero_counters_without_changing_injury_or_protected_data(self):
        first,second=self.seed();self.day(203)
        with closing(self.db.connect()) as c,c:
            protected={t:list(c.execute('SELECT * FROM '+t)) for t in ('idols','abilities','roster_memberships','squad_leaders','finance_contracts','agencies','draft_picks','scheduled_matches')}
            injury=tuple(c.execute('SELECT injured,injury_day,recovery_day,return_not_before FROM player_conditions WHERE person_id=?',(second,)).fetchone())
            enter_day(c,203)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM player_conditions WHERE registration_weeks!=0 OR complete_rest_weeks!=0').fetchone()[0],0)
            self.assertEqual(injury,tuple(c.execute('SELECT injured,injury_day,recovery_day,return_not_before FROM player_conditions WHERE person_id=?',(second,)).fetchone()))
            for t,rows in protected.items():self.assertEqual(rows,list(c.execute('SELECT * FROM '+t)))
            self.assertEqual(public_condition(c,first,203).registration_weeks,0)
    def test_repeat_and_reopen_do_not_reset_again(self):
        first,_=self.seed()
        with closing(self.db.connect()) as c,c:
            enter_day(c,203)
            count=c.execute("SELECT COUNT(*) FROM condition_events WHERE event_key LIKE 'season-end-registration:1:%'").fetchone()[0]
            c.execute('UPDATE player_conditions SET registration_weeks=2 WHERE person_id=?',(first,))
        with closing(self.db.connect()) as c,c:
            enter_day(c,203)
            self.assertEqual(c.execute('SELECT registration_weeks FROM player_conditions WHERE person_id=?',(first,)).fetchone()[0],2)
            self.assertEqual(count,c.execute("SELECT COUNT(*) FROM condition_events WHERE event_key LIKE 'season-end-registration:1:%'").fetchone()[0])
    def test_no_registration_accumulation_offseason_preparation_next_regular_resumes(self):
        first,_=self.seed()
        with closing(self.db.connect()) as c,c:
            enter_day(c,203)
            for day in range(203,231):
                self.assertEqual(public_condition(c,first,day).registration_weeks,0)
                with patch('idol_manager.conditions.risk_event',return_value=False):finish_day(c,day)
            self.assertEqual(public_condition(c,first,231).registration_weeks,1)
    def test_manual_reset_current_week_and_next_season(self):
        first,_=self.seed();self.day(231)
        with closing(self.db.connect()) as c,c:
            reset_registration(c,231,event_prefix='test-manual',reason='manual_registration_reset')
            condition=public_condition(c,first,231)
            self.assertEqual(condition.registration_weeks,1);self.assertEqual(required_rest_weeks(condition.registration_weeks),0);self.assertEqual(registration_multiplier(condition.registration_weeks),1)
            c.execute('UPDATE player_conditions SET registration_weeks=8')
            enter_day(c,427)
            self.assertEqual(public_condition(c,first,427).registration_weeks,0)
    def test_reset_rolls_back_completely_on_failure(self):
        self.seed()
        with closing(self.db.connect()) as c:before=[tuple(r) for r in c.execute('SELECT * FROM player_conditions')]
        with self.assertRaises(RuntimeError):
            with closing(self.db.connect()) as c,c:
                reset_registration(c,203,event_prefix='rollback',reason='test');raise RuntimeError('fail')
        with closing(self.db.connect()) as c:
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM player_conditions')])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM condition_events WHERE event_key LIKE 'rollback:%'").fetchone()[0],0)

    def test_active_week_reset_counts_first_week_and_persists_next_weeks_once(self):
        first,_=self.seed();self.day(231)
        with closing(self.db.connect()) as c,c:
            reset_registration(c,231,event_prefix='manual-registration-reset:legacy-fixture',reason='user_requested_slot1_registration_reset')
            for day,expected in ((231,1),(232,1),(237,1),(238,2),(241,2),(245,3)):
                self.assertEqual(public_condition(c,first,day).registration_weeks,expected)
                with patch('idol_manager.conditions.risk_event',return_value=False):finish_day(c,day)
                self.assertEqual(public_condition(c,first,day).registration_weeks,expected)
        with closing(self.db.connect()) as c:
            self.assertEqual(public_condition(c,first,245).registration_weeks,3)
    def test_legacy_missing_first_week_restored_only_for_uninterrupted_first_team(self):
        first,second=self.seed()
        with closing(self.db.connect()) as c,c:
            reset_registration(c,231,event_prefix='manual-registration-reset:legacy-fixture',reason='user_requested_slot1_registration_reset')
            c.execute('UPDATE player_conditions SET registration_weeks=1,registration_week=34 WHERE person_id=?',(first,))
            before=tuple(c.execute('SELECT * FROM player_conditions WHERE person_id=?',(first,)).fetchone())
            self.assertEqual(public_condition(c,first,241).registration_weeks,2)
            self.assertEqual(before,tuple(c.execute('SELECT * FROM player_conditions WHERE person_id=?',(first,)).fetchone()))
            c.execute('UPDATE player_conditions SET squad_since=239 WHERE person_id=?',(first,))
            self.assertEqual(public_condition(c,first,241).registration_weeks,1)
            c.execute("UPDATE player_conditions SET squad='first_team',registration_weeks=0,registration_week=34,squad_since=239 WHERE person_id=?",(second,))
            self.assertEqual(public_condition(c,second,241).registration_weeks,1)
    def test_legacy_correction_does_not_bridge_maintenance_or_new_season(self):
        first,_=self.seed()
        with closing(self.db.connect()) as c,c:
            reset_registration(c,231,event_prefix='manual-registration-reset:legacy-fixture',reason='user_requested_slot1_registration_reset')
            enter_day(c,315)
            self.assertEqual(public_condition(c,first,315).registration_weeks,0)
            self.assertEqual(public_condition(c,first,322).registration_weeks,1)
            enter_day(c,427)
            self.assertEqual(public_condition(c,first,427).registration_weeks,0)
            c.execute('UPDATE player_conditions SET registration_week=64 WHERE person_id=?',(first,))
            self.assertEqual(public_condition(c,first,455).registration_weeks,1)
