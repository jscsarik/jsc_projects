"""Upgrade the captured v6 save, never the actual user save."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.config import ROOT
from idol_manager.database import Database
from idol_manager.condition_schema import V7_STATEMENTS
from idol_manager.match_service import MatchService
from idol_manager.migrations import SCHEMA_VERSION


class ConditionMigrationTests(unittest.TestCase):
    def setUp(self):
        source=ROOT/'.test-artifacts/fatigue_live_copy.sqlite3'
        if not source.is_file():self.skipTest('Captured version 6 save is not packaged')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'upgrade.sqlite3'
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(self.path)) as b:a.backup(b)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as c:
            return {table:(tuple(row[1] for row in c.execute(f'PRAGMA table_info("{table}")')),
                           sorted(c.execute(f'SELECT * FROM "{table}"').fetchall()))
                    for table, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}

    def test_v6_backup_backfill_preserves_all_80_results_and_every_old_column(self):
        before=self.snapshot()
        self.assertEqual(len(before['match_results'][1]),80)
        db=Database(self.path)
        self.assertTrue(db.last_backup_path.is_file())
        with closing(db.connect()) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            for table,(columns,rows) in before.items():
                columns_sql=','.join(f'"{column}"' for column in columns)
                from tests.migration_fixtures import current_rows
                self.assertEqual(sorted(tuple(r) for r in c.execute(f'SELECT {columns_sql} FROM "{table}"')),current_rows(table,rows),table)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM condition_events').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT SUM(injured) FROM player_conditions').fetchone()[0],0)
            proven=c.execute('''SELECT COUNT(*) FROM (SELECT DISTINCT p.person_id,(m.season-1)*196+(m.week-1)*7+m.weekday
                FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id)''').fetchone()[0]
            self.assertEqual(c.execute('SELECT COUNT(*) FROM appearance_days').fetchone()[0],proven)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            identity=c.execute('SELECT match_id FROM match_results LIMIT 1').fetchone()[0]
        with patch('idol_manager.match_service.calculate_match',side_effect=AssertionError('old result reroll')):
            self.assertIsNotNone(MatchService(db).play(identity))
        self.assertEqual(Database(self.path).last_backup_path,None)
        with closing(sqlite3.connect(db.last_backup_path)) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],6)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],80)

    def test_failed_schema_extension_rolls_back_entire_migration(self):
        before=self.snapshot()
        with patch('idol_manager.migrations.V7_STATEMENTS',V7_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):Database(self.path)
        self.assertEqual(before,self.snapshot())
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],6)

