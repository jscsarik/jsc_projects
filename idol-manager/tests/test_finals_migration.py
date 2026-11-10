from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import tempfile,sqlite3,unittest,json
from idol_manager.database import Database
from idol_manager.config import ROOT,load_settings
from idol_manager.domain import Person
from idol_manager.conditions import public_condition
from idol_manager.finals_schema import V10_STATEMENTS
from tests.migration_fixtures import drop_finals
from tests.test_match_ui import copy_db


class FinalsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'old.sqlite3'
        db=Database(self.path);db.create_game(tuple(Person(str(i),str(i),str(i),f'absent/{i}.png') for i in range(310)),load_settings())
        with closing(db.connect()) as c,c:drop_finals(c);c.execute('PRAGMA user_version=9')

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as c:
            return {t:sorted(c.execute(f'SELECT * FROM "{t}"').fetchall()) for t, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}

    def test_real_v9_copy_ten_completed_games_and_all_old_rows_preserved(self):
        source=ROOT/'.test-artifacts/postseason_live_copy.sqlite3'
        if not source.is_file():self.skipTest('development save snapshot not present')
        copy_db(source,self.path);before=self.snapshot();db=Database(self.path);after=self.snapshot()
        self.assertTrue(db.last_backup_path.is_file());self.assertGreater(len(before['match_results']),0)
        from tests.migration_fixtures import current_rows
        for t,rows in before.items():self.assertEqual(current_rows(t,rows),after[t],t)
        self.assertIsNone(Database(self.path).last_backup_path)

    def test_old_offseason_display_and_future_injury_duration_and_streak_preserved(self):
        with closing(sqlite3.connect(self.path)) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=168')
            c.execute('UPDATE player_conditions SET last_appearance_day=167,consecutive_days=2,injured=1,recovery_day=170')
        db=Database(self.path)
        with closing(db.connect()) as c:
            self.assertEqual(c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],189)
            self.assertEqual(c.execute('SELECT recovery_day FROM player_conditions LIMIT 1').fetchone()[0],191)
            state=public_condition(c,'0',189);self.assertEqual(state.projected_days,3);self.assertEqual(state.penalty,.1)
            self.assertEqual(c.execute('SELECT status FROM season_finals').fetchone()[0],'legacy_closed')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM final_contests').fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_season_two_weekday_and_date_primary_keys_preserved(self):
        with closing(sqlite3.connect(self.path)) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=203')
            c.executemany("INSERT INTO appearance_days VALUES ('0',?)",[(167,),(168,),(196,)])
        db=Database(self.path)
        with closing(db.connect()) as c:
            self.assertEqual(c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],224)
            self.assertEqual([r[0] for r in c.execute("SELECT absolute_day FROM appearance_days WHERE person_id='0' ORDER BY absolute_day")],[167,189,217])

    def test_failed_schema_upgrade_rolls_back_all_rows_and_version(self):
        before=self.snapshot()
        with patch('idol_manager.migrations.V10_STATEMENTS',V10_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):Database(self.path)
        self.assertEqual(before,self.snapshot())
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],9)
