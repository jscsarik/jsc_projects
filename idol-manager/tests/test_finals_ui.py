import os
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import unittest,time,gc
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from idol_manager.bgm import BgmManager
from tests.test_bgm import FakeAudio
from tests import test_finals as fixture


class FinalsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.FinalsTests.setUpClass.__func__(cls)
    def setUp(self):
        gc.collect();self.app.processEvents()
        fixture.FinalsTests.setUp(self)
        self.warnings=[]
        warning=patch.object(QMessageBox,'warning',side_effect=lambda _parent,_title,message,*_args,**_kwargs:self.warnings.append(str(message)))
        warning.start();self.addCleanup(warning.stop)
    rows=fixture.FinalsTests.rows
    table=fixture.FinalsTests.table
    setup_rank=fixture.FinalsTests.setup_rank
    day=fixture.FinalsTests.day

    def open(self,*,tied=0,root=None):
        self.setup_rank(tied,player_third=True);self.day(168 if tied else 170)
        self.service=GameService(root or Path(self.temp.name),database_path=self.path)
        self.manager=BgmManager(self.service.root,self.path.parent/'ui_test_bgm_settings.json',backend_factory=FakeAudio,transition_ms=0,fade_ms=0)
        self.window=MainWindow(self.service,bgm=self.manager);self.addCleanup(self.window.close)
        self.window.resize(1700,1050);self.window.show();self.app.processEvents()
        if self.app.platformName()=='windows':
            self.assertTrue(QTest.qWaitForWindowExposed(self.window,5000))
            self.window.raise_();self.window.activateWindow()
            self.assertTrue(QTest.qWaitForWindowActive(self.window,5000))
        QTest.mouseClick(self.window.finals_menu,Qt.MouseButton.LeftButton)
        self.assertIs(self.window.pages.currentWidget(),self.window.finals_page)
        self.page=self.window.finals_page
        self.app.processEvents();QTest.qWait(40)

    def wait(self,predicate):
        end=time.monotonic()+10
        while not predicate() and time.monotonic()<end:
            QTest.qWait(10)
            # Give the Python QRunnable an explicit GIL-free scheduling turn;
            # Qt-only waits can starve it in a long combined GUI suite.
            time.sleep(.003)
        if not predicate():
            import faulthandler
            faulthandler.dump_traceback()
        self.assertTrue(predicate(),f'경기 UI 대기 실패: warnings={self.warnings}, visible={self.page.isVisible()}, busy={self.page.job is not None}, selected={self.page.selected_ids()}, required={self.page.selection.selection_count if self.page.selection else None}, notice={self.page.notice.text()}')

    def choose(self):
        table=self.page.lineup_table
        identities=[table.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(self.page.selection.selection_count)]
        for identity in identities:
            row=next(i for i in range(table.rowCount()) if table.item(i,0).data(Qt.ItemDataRole.UserRole)==identity)
            table.item(row,0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(len(self.page.selected_ids()),self.page.selection.selection_count)
        self.assertTrue(self.page.start_button.isEnabled())

    def test_postseason_reuses_photos_vs_pause_skip_result_bgm_and_restart(self):
        self.open();self.choose()
        self.assertTrue(self.page.start_button.isEnabled())
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.replaying)
        self.assertEqual(self.manager.desired_category,'battle')
        self.assertIn('시리즈',self.page.battle.content.text());self.assertTrue(self.page.battle.cards)
        QTest.mouseClick(self.page.pause_button,Qt.MouseButton.LeftButton);self.assertTrue(self.page.paused)
        before=self.table('final_contests');QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        self.assertEqual(before,self.table('final_contests'));self.assertEqual(self.manager.desired_category,'default')
        result=self.page.current_result;self.assertEqual(self.page.tabs.currentIndex(),2)
        self.assertEqual(result,self.page.matches.result(result.match_id))
        self.window.close();self.assertEqual(result,self.page.matches.result(result.match_id))

    def test_three_team_tie_ui_full_rank_result_and_no_regular_points(self):
        self.open(tied=3);self.page.selection.fixture.player_participates
        self.choose()
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton);self.wait(lambda:self.page.current_result is not None)
        self.page.skip();self.assertIn('최종 순위',self.page.result_summary.text())
        self.assertEqual(len(self.table('match_results')),585)
