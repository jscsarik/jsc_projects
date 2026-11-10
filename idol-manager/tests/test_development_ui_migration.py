from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import gc,json,os,sqlite3,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from idol_manager.database import Database
from idol_manager.development_schema import V11_STATEMENTS
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from tests import test_development as fixture
from tests.migration_fixtures import drop_development


class DevelopmentMigrationTests(unittest.TestCase):
    setUp=fixture.DevelopmentServiceTests.setUp
    rows=fixture.DevelopmentServiceTests.rows
    dump=fixture.DevelopmentServiceTests.dump

    def old(self):
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=3')
            drop_development(c);c.execute('PRAGMA user_version=10')

    def test_additive_backup_migration_preserves_ca_pa_ages_all_original_rows(self):
        self.old()
        with closing(self.db.connect()) as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before={t:sorted(tuple(r) for r in c.execute(f'SELECT * FROM "{t}"')) for t in tables}
        self.db=Database(self.path);self.assertTrue(self.db.last_backup_path.is_file())
        with closing(self.db.connect()) as c:
            for t,rows in before.items():self.assertEqual(rows,sorted(tuple(r) for r in c.execute(f'SELECT * FROM "{t}"')),t)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM development_settlements').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM development_days').fetchone()[0],480)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        before=self.dump();self.assertIsNone(Database(self.path).last_backup_path);self.assertEqual(before,self.dump())

    def test_migration_failure_rolls_back_and_unknown_old_roles_not_invented(self):
        self.old();before=self.dump()
        with patch('idol_manager.migrations.V11_STATEMENTS',V11_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):Database(self.path)
        self.assertEqual(before,self.dump())
        with closing(self.db.connect()) as c,c:c.execute('UPDATE player_conditions SET history_known_since=3')
        self.db=Database(self.path)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM development_days'),[(0,)])


class DevelopmentUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    rows=fixture.DevelopmentServiceTests.rows
    dump=fixture.DevelopmentServiceTests.dump
    seed_days=fixture.DevelopmentServiceTests.seed_days

    def setUp(self):
        gc.collect();self.app.processEvents();fixture.DevelopmentServiceTests.setUp(self)
        self.seed_days();self.development.settle_current()
        root=Path(self.temp.name);folder=root/'missing';folder.mkdir()
        image=QImage(80,100,QImage.Format.Format_RGB32);image.fill(QColor('#c4d7e8'))
        for i in range(310):image.save(str(folder/f'{i}.png'))
        self.service=GameService(root,database_path=self.path)
        self.window=MainWindow(self.service);self.addCleanup(self.window.close)
        self.window.resize(1700,1000);self.window.show();self.app.processEvents()
        if self.app.platformName()=='windows':
            self.assertTrue(QTest.qWaitForWindowExposed(self.window,5000))
            self.window.raise_();self.window.activateWindow();self.assertTrue(QTest.qWaitForWindowActive(self.window,5000))
        QTest.mouseClick(self.window.development_menu,Qt.MouseButton.LeftButton)
        self.page=self.window.development_page

    def test_history_photo_deltas_filter_reopen_no_settlement_side_effects(self):
        self.assertIs(self.window.pages.currentWidget(),self.page)
        self.assertTrue(self.page.rows);self.assertIn('주간 성장',self.page.period.currentText())
        self.assertEqual(self.page.table.columnCount(),16)
        self.page.changed.setChecked(False);self.assertEqual(self.page.table.rowCount(),160)
        self.page.agency.setCurrentIndex(self.page.agency.findData('ador'));self.assertEqual(self.page.table.rowCount(),16)
        self.assertTrue(all(r['agency_id']=='ador' for r in self.page.rows))
        before=self.dump();self.page.reload();self.window.show_development();self.assertEqual(before,self.dump())
        self.window.close();service=GameService(Path(self.temp.name),database_path=self.path)
        self.assertEqual(self.service.development.history(),service.development.history())

    def test_ui_projection_denies_pa_and_private_trials(self):
        original=self.db.connect
        def connect():
            c=original();c.set_authorizer(lambda action,table,column,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table=='development_trials' or (table,column)==('abilities','potential')) else sqlite3.SQLITE_OK);return c
        # The facade uses the same DB file but a separate database object.
        with patch.object(self.service.database,'connect',side_effect=connect):self.page.reload()
        self.assertTrue(self.page.rows)
