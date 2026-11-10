"""Theme-only Windows GUI checks, exclusively against a disposable game."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication,QLabel,QMessageBox,QInputDialog,QTableView
from PySide6.QtTest import QTest
from tests import test_market as fixture
from idol_manager.ui.theme_manager import ThemeManager
from idol_manager.ui.theme import STYLE


class ThemeTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    setUp=fixture.MarketTests.setUp
    rows=fixture.MarketTests.rows;day=fixture.MarketTests.day;dump=fixture.MarketTests.dump

    def test_immediate_switch_popups_profiles_persistence_and_light_restore(self):
        from idol_manager.ui.main_window import MainWindow
        from idol_manager.ui.profile_dialog import ProfileDialog
        app=QApplication.instance();path=self.base/'appearance.ini'
        manager=ThemeManager(app,path)
        self.addCleanup(lambda:app.removeEventFilter(manager))
        self.addCleanup(lambda:manager.set_mode('light',persist=False))
        self.assertEqual(manager.mode,'light')
        w=MainWindow(self.service);self.addCleanup(w.close);w.resize(1300,900);w.show();QTest.qWait(120)
        before=self.dump();original=w.styleSheet();self.assertEqual(original,STYLE)
        original_sidebar=w.findChild(QLabel,'brand').styleSheet()
        out=Path(__file__).resolve().parents[1]/'reports/themes';out.mkdir(exist_ok=True)
        w.theme_button.menu().actions()[1].trigger();QTest.qWait(80)
        self.assertEqual(manager.mode,'dark')
        self.assertEqual(QSettings(str(path),QSettings.Format.IniFormat).value('appearance/theme'),'dark')
        manager.settings.sync()
        app.removeEventFilter(manager)
        restarted=ThemeManager(app,path)
        self.addCleanup(lambda:app.removeEventFilter(restarted))
        self.addCleanup(lambda:restarted.set_mode('light',persist=False))
        self.assertEqual(restarted.mode,'dark')
        for show in (w.show_squads,w.show_draft,w.show_schedule,w.show_market,w.show_development,w.show_matches):
            show();QTest.qWait(50)
            for table in w.findChildren(QTableView):
                if table.isVisible():
                    self.assertGreater(table.palette().color(QPalette.ColorRole.Text).lightness(),170)
        w.match_page.tabs.setCurrentIndex(3);QTest.qWait(80)
        w.grab().save(str(out/'dark_league.png'))
        person=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='first_team' LIMIT 1")[0][0]
        dialog=ProfileDialog(self.service,w.thumbnails,[person],w);self.addCleanup(dialog.close)
        dialog.show();dialog.panels[0].tabs.setCurrentIndex(1);QTest.qWait(100)
        dialog.grab().save(str(out/'dark_profile.png'))
        self.assertGreater(dialog.palette().color(QPalette.ColorRole.WindowText).lightness(),170)
        for popup in (QMessageBox(QMessageBox.Icon.Question,'확인','저장하겠습니까?',parent=w),QInputDialog(w)):
            popup.show();QTest.qWait(30)
            self.assertLess(popup.palette().color(QPalette.ColorRole.Window).lightness(),80)
            self.assertGreater(popup.palette().color(QPalette.ColorRole.WindowText).lightness(),170)
            popup.close()
        # Widgets created after switching also receive the theme, with exact restoration.
        label=QLabel('건강 90/90',dialog);label.setStyleSheet('background:#f2f7fd;color:#493f5d;')
        label.show();QTest.qWait(30);self.assertNotIn('#f2f7fd',label.styleSheet())
        restarted.set_mode('light');QTest.qWait(80)
        self.assertEqual(w.styleSheet(),original)
        self.assertEqual(w.findChild(QLabel,'brand').styleSheet(),original_sidebar)
        self.assertEqual(label.styleSheet(),'background:#f2f7fd;color:#493f5d;')
        w.resize(900,1600);QTest.qWait(100)
        self.assertTrue(w.theme_header.isVisible())
        self.assertTrue(w.theme_button.isVisible())
        self.assertGreater(w.theme_button.geometry().left(),w.bgm_controls.geometry().right())
        self.assertEqual(before,self.dump())
        dialog.close();w.grab().save(str(out/'light_league.png'))


if __name__=='__main__':unittest.main()
