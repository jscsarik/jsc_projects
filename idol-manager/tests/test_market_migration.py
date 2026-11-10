"""V12 -> V13 preservation and failure recovery on temporary DBs."""
from contextlib import closing
from unittest.mock import patch
import sqlite3,unittest
from tests import test_market as fixture
from tests.migration_fixtures import drop_market
from idol_manager.database import Database
from idol_manager.market_schema import V13_STATEMENTS

class MarketMigrationTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    setUp=fixture.MarketTests.setUp
    day=fixture.MarketTests.day
    dump=fixture.MarketTests.dump
    def old(self):
        with closing(self.db.connect()) as c,c:drop_market(c);c.execute('PRAGMA user_version=12')
    def test_migration_keeps_all_finance_contracts_money_payroll_and_existing_rows(self):
        self.old()
        with closing(self.db.connect()) as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            old={t:sorted(tuple(r) for r in c.execute('SELECT * FROM "'+t+'"')) for t in tables}
        upgraded=Database(self.path);self.assertTrue(upgraded.last_backup_path.is_file())
        with closing(upgraded.connect()) as c:
            for t,rows in old.items():self.assertEqual(rows,sorted(tuple(r) for r in c.execute('SELECT * FROM "'+t+'"')),t)
            self.assertFalse(c.execute('SELECT 1 FROM market_terms WHERE end_season IS NOT NULL').fetchone())
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        before=self.dump();self.assertIsNone(Database(self.path).last_backup_path);self.assertEqual(before,self.dump())
    def test_rebuild_failure_rolls_back_every_parent_and_child_row(self):
        self.old();before=self.dump()
        with patch('idol_manager.migrations.V13_STATEMENTS',V13_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):Database(self.path)
        self.assertEqual(before,self.dump())
