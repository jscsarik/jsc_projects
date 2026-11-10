from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,sqlite3,unittest
from idol_manager.database import Database
from idol_manager.finance_schema import V12_STATEMENTS
from idol_manager.finance_service import FinanceService
from tests import test_finance as fixture
from tests.migration_fixtures import drop_finance

class FinanceMigrationTests(unittest.TestCase):
    setUpClass=classmethod(fixture.FinanceTests.setUpClass.__func__)
    setUp=fixture.FinanceTests.setUp
    rows=fixture.FinanceTests.rows
    dump=fixture.FinanceTests.dump
    week=fixture.FinanceTests.week
    def old(self,day=23):
        with closing(self.db.connect()) as c,c:
            drop_finance(c);c.execute('PRAGMA user_version=11');c.execute('UPDATE game_clock SET absolute_day=?',(day,))
            c.execute("UPDATE agencies SET funds_krw=123456789 WHERE id='ador'")
    def test_backup_additive_migration_all_old_tables_unchanged_no_retroactive_pay(self):
        self.old()
        with closing(self.db.connect()) as c:
            before={t:[tuple(r) for r in c.execute('SELECT * FROM "'+t+'" ORDER BY 1')] for t, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
        db=Database(self.path);self.assertTrue(db.last_backup_path.is_file());self.db=db;self.finance=FinanceService(db)
        with closing(db.connect()) as c:
            for t,rows in before.items():self.assertEqual(rows,[tuple(r) for r in c.execute('SELECT * FROM "'+t+'" ORDER BY 1')],t)
            from idol_manager.migrations import SCHEMA_VERSION
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM finance_ledger').fetchone()[0],10)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM finance_payroll').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT DISTINCT start_day FROM finance_contracts').fetchall()[0][0],23)
        self.week(4);self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_payroll'),[(0,)])
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'"),[(123456789,)])
        self.assertEqual(self.finance.dashboard('ador')['next_pay_week'],8)
        self.week(5);self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'"),[(132356789,)])
        before=self.dump();self.assertIsNone(Database(self.path).last_backup_path);self.assertEqual(before,self.dump())
    def test_failed_migration_rolls_back_version_cash_and_every_table(self):
        self.old();before=self.dump()
        with patch('idol_manager.migrations.V12_STATEMENTS',V12_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):Database(self.path)
        self.assertEqual(before,self.dump());self.assertEqual(self.rows('PRAGMA user_version'),[(11,)])
    def test_legacy_already_closed_season_does_not_receive_past_bonus(self):
        with closing(self.db.connect()) as c,c:c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (1,'completed','{}','[]')")
        self.old(195);self.db=Database(self.path)
        from idol_manager.finance_service import close_season
        with closing(self.db.connect()) as c,c:close_season(c,1,195)
        self.assertFalse(self.rows("SELECT 1 FROM finance_settlements WHERE kind='bonus'"))
