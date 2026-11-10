import json,unittest
from contextlib import closing
from unittest.mock import patch
from tests import test_season32 as fixture
from idol_manager.database import Database
from idol_manager.conditions import enter_day,finish_day,public_condition
from idol_manager.maintenance_conditions import apply_reset
from idol_manager.condition_rules import registration_multiplier

class MaintenanceConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day

    def seed(self):
        first=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' ORDER BY person_id LIMIT 1")[0][0]
        second=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' ORDER BY person_id LIMIT 2")
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE player_conditions SET registration_weeks=7,registration_week=12,complete_rest_weeks=1,squad_since=70 WHERE person_id IN (?,?,?)',(first,second[0][0],second[1][0]))
            c.execute('UPDATE player_conditions SET injured=1,injury_day=90,recovery_day=106,return_not_before=112 WHERE person_id=?',(second[0][0],))
            c.execute('UPDATE player_conditions SET injured=1,injury_day=89,recovery_day=92 WHERE person_id=?',(second[1][0],))
        return first,second[0][0],second[1][0]

    def test_entry_resets_both_squads_and_shortens_once(self):
        first,long,short=self.seed();self.day(90)
        before={t:self.rows('SELECT * FROM '+t+' ORDER BY 1') for t in ('abilities','idols','agencies','roster_memberships','draft_picks','scheduled_matches','special_events')}
        with closing(self.db.connect()) as c,c:
            enter_day(c,91)
            state=public_condition(c,first,91);self.assertEqual(state.registration_weeks,0)
            self.assertEqual(registration_multiplier(state.registration_weeks),1)
            self.assertEqual(tuple(c.execute('SELECT registration_weeks,complete_rest_weeks FROM player_conditions WHERE person_id=?',(long,)).fetchone()),(0,0))
            self.assertEqual(tuple(c.execute('SELECT injured,recovery_day,return_not_before FROM player_conditions WHERE person_id=?',(long,)).fetchone()),(1,99,112))
            self.assertEqual(tuple(c.execute('SELECT injured,recovery_day FROM player_conditions WHERE person_id=?',(short,)).fetchone()),(0,91))
            for d in (91,92,93,97):apply_reset(c,d)
            self.assertEqual(c.execute('SELECT recovery_day FROM player_conditions WHERE person_id=?',(long,)).fetchone()[0],99)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM maintenance_condition_resets').fetchone()[0],1)
        for t,data in before.items():self.assertEqual(data,self.rows('SELECT * FROM '+t+' ORDER BY 1'))

    def test_maintenance_does_not_reaccumulate_and_regular_count_resumes(self):
        first,long,short=self.seed()
        with closing(self.db.connect()) as c,c:
            for d in range(91,98):
                enter_day(c,d)
                with patch('idol_manager.conditions.risk_event',return_value=False):finish_day(c,d)
                self.assertEqual(public_condition(c,first,d).registration_weeks,0)
            enter_day(c,98)
            self.assertEqual(public_condition(c,first,98).registration_weeks,1)
            self.assertEqual(c.execute('SELECT complete_rest_weeks FROM player_conditions WHERE person_id=?',(short,)).fetchone()[0],0)
            enter_day(c,99);self.assertFalse(public_condition(c,long,99).injured)

    def test_next_season_gets_one_new_reset(self):
        first,long,short=self.seed()
        with closing(self.db.connect()) as c,c:
            self.assertFalse(apply_reset(c,90));self.assertTrue(apply_reset(c,91))
            c.execute('UPDATE player_conditions SET injured=1,recovery_day=340 WHERE person_id=?',(long,))
            self.assertTrue(apply_reset(c,315));self.assertFalse(apply_reset(c,316))
            self.assertEqual(c.execute('SELECT recovery_day FROM player_conditions WHERE person_id=?',(long,)).fetchone()[0],333)

    def test_existing_maintenance_save_backup_and_reload_no_repeat(self):
        first,long,short=self.seed();self.day(94)
        protected=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        with closing(self.db.connect()) as c,c:c.execute('DROP TABLE maintenance_condition_resets');c.execute('PRAGMA user_version=27')
        db=Database(self.path);self.assertTrue(db.last_backup_path.exists())
        self.assertEqual(self.rows('SELECT absolute_day FROM game_clock'),[(94,)])
        self.assertEqual(self.rows('SELECT recovery_day FROM player_conditions WHERE person_id=?',(long,)),[(99,)])
        self.assertEqual(protected,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertIsNone(Database(self.path).last_backup_path)
        self.assertEqual(self.rows('SELECT recovery_day FROM player_conditions WHERE person_id=?',(long,)),[(99,)])

    def test_failed_transaction_rolls_back_reset_and_recovery(self):
        self.seed();before=self.rows('SELECT * FROM player_conditions ORDER BY person_id')
        with self.assertRaises(RuntimeError):
            with closing(self.db.connect()) as c,c:
                apply_reset(c,91);raise RuntimeError('rollback fixture')
        self.assertEqual(before,self.rows('SELECT * FROM player_conditions ORDER BY person_id'))
        self.assertEqual(self.rows('SELECT COUNT(*) FROM maintenance_condition_resets'),[(0,)])
