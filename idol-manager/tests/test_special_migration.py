from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.config import ROOT
from idol_manager.database import Database
from idol_manager.special_schema import V8_STATEMENTS,SPECIAL_TABLES
from idol_manager.migrations import SCHEMA_VERSION
from tests import test_special_service as fixture


class SpecialMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.SpecialServiceTests.setUpClass.__func__(cls)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'migration.sqlite3'
        fixture.fixture.copy_db(self.template,self.path)
        with closing(Database(self.path).connect()) as c,c:
            from tests.migration_fixtures import drop_finals
            drop_finals(c)
            c.execute('DROP TABLE draft_estimates')
            for view in ('special_standings','idol_special_career_stats'):c.execute(f'DROP VIEW {view}')
            for table in SPECIAL_TABLES:c.execute(f'DROP TABLE {table}')
            c.execute('PRAGMA user_version=7')

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as c:
            return {t:sorted(c.execute(f'SELECT * FROM "{t}"').fetchall()) for t, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}

    def test_v7_migration_backs_up_preserves_every_existing_row_and_is_repeatable(self):
        before=self.snapshot();db=Database(self.path)
        self.assertTrue(db.last_backup_path.is_file())
        after=self.snapshot()
        from tests.migration_fixtures import current_rows
        for table,rows in before.items():self.assertEqual(current_rows(table,rows),after[table],table)
        for table in SPECIAL_TABLES:self.assertEqual(after[table],[])
        with closing(db.connect()) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with closing(sqlite3.connect(db.last_backup_path)) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],7)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],len(before['match_results']))
        self.assertIsNone(Database(self.path).last_backup_path)
        self.assertEqual(self.snapshot(),after)

    def test_failed_migration_or_backup_preserves_v7_all_rows_and_schema(self):
        before=self.snapshot()
        with patch('idol_manager.migrations.V8_STATEMENTS',V8_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):Database(self.path)
        self.assertEqual(before,self.snapshot())
        with patch('idol_manager.migrations.backup_database',side_effect=OSError('backup denied')):
            with self.assertRaises(OSError):Database(self.path)
        self.assertEqual(before,self.snapshot())
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],7)

    def test_actual_save_copy_migration_preserves_all_records_including_conditions(self):
        source=ROOT/'.test-artifacts/special_live_copy.sqlite3'
        if not source.is_file():self.skipTest('Captured actual v7 save not packaged')
        fixture.fixture.copy_db(source,self.path)
        before=self.snapshot();Database(self.path);after=self.snapshot()
        from tests.migration_fixtures import current_rows
        for table,rows in before.items():self.assertEqual(current_rows(table,rows),after[table],table)

