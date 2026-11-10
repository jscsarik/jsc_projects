from contextlib import closing
from pathlib import Path
import gc
import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox

from idol_manager.config import ROOT
from idol_manager.database import Database
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from idol_manager.bgm import BgmManager
from tests.test_bgm import FakeAudio
from tests import test_special_service as fixture


class SpecialUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.SpecialServiceTests.setUpClass.__func__(cls)

    def setUp(self):
        gc.collect();self.app.processEvents()
        self.temp=tempfile.TemporaryDirectory(prefix='idol_special_ui_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'copy.sqlite3'
        fixture.fixture.copy_db(self.template,self.path)

    def open(self):
        self.service=GameService(self.root,self.path);self.service.specials.seed_factory=lambda:1827
        for category in ('default','battle'):
            folder=self.root/'assets/audio/bgm'/category;folder.mkdir(parents=True,exist_ok=True)
            (folder/f'{category}.mp3').write_bytes(b'fake audio')
        self.manager=BgmManager(self.root,self.root/'bgm.json',backend_factory=FakeAudio,transition_ms=0,fade_ms=0)
        self.window=MainWindow(self.service,bgm=self.manager);self.addCleanup(self.window.close)
        self.window.show();QTest.mouseClick(self.window.special_menu,Qt.MouseButton.LeftButton)
        self.page=self.window.special_page
        self.wait(lambda:self.manager.current_track is not None)
        return self.page

    def wait(self,predicate,seconds=20):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:QTest.qWait(10);time.sleep(.002)
        self.assertTrue(predicate(),'특별전 GUI 작업 시간 초과')

    def dump(self):
        with closing(self.service.database.connect()) as c:return list(c.iterdump())

    def start_event(self):
        QTest.mouseClick(self.page.open_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.job is None)
        self.assertEqual(self.page.round_table.rowCount(),2)

    def select(self,stage):
        identity=next(r['id'] for r in self.page.event_state['rounds'] if r['stage']==stage)
        row=next(i for i in range(self.page.round_table.rowCount()) if self.page.round_table.item(i,0).data(Qt.ItemDataRole.UserRole)==identity)
        self.page.round_table.setCurrentCell(row,0);self.page.select_round()

    def choose(self):
        selection=self.page.selection;table=self.page.lineup_table
        if selection['agency'] not in self.page.current_round['agencies']:return
        for i in range(table.rowCount()):
            if len(self.page.selected_ids())>=selection['count']:break
            item=table.item(i,0)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState()!=Qt.CheckState.Checked:item.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(len(self.page.selected_ids()),selection['count'])

    def play(self,stage,skip=True):
        self.select(stage);self.choose();self.assertTrue(self.page.start_button.isEnabled())
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.job is None)
        result=self.page.current_result
        self.assertIsNotNone(result)
        if skip and self.page.replaying:QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        return result

    def test_manual_ten_first_priority_complete_all_stages_and_next_monday(self):
        self.open();self.start_event()
        state=self.service.specials.state(self.page.event_combo.currentData())
        own=next(r for r in state['rounds'] if 'ador' in r['agencies'])
        self.select(own['stage'])
        self.assertEqual(len(self.page.selected_ids()),5)
        self.assertFalse(self.page.start_button.isEnabled())
        self.choose();self.assertTrue(self.page.start_button.isEnabled())
        for stage in ('upper','lower','final'):self.play(stage)
        self.assertIn('전체 완료',self.page.result_label.text())
        self.assertEqual(self.page.standings_table.rowCount(),10)
        self.assertEqual(self.page.summary_table.rowCount(),10)
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        self.assertEqual(self.service.calendar.state().date.absolute_day,28)
        self.assertEqual(self.page.event_state['status'],'completed')

    def test_replay_skip_same_database_and_real_bgm_view_state(self):
        self.open();self.start_event();result=self.play('upper',skip=False)
        self.assertEqual(self.page.timer.interval(),500)
        self.assertGreaterEqual(len(self.page.frames),30)
        self.wait(lambda:self.manager.category=='battle')
        before=self.dump()
        self.page.tabs.setCurrentIndex(3);self.wait(lambda:self.manager.category=='default')
        self.page.tabs.setCurrentIndex(1);self.wait(lambda:self.manager.category=='battle')
        self.page.timer.stop()
        for _ in range(5):self.page.advance_frame()
        QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.manager.category=='default')
        self.assertEqual(before,self.dump())
        self.assertEqual(result,self.service.specials.result(result.round_id))
        self.assertEqual(dict(self.page.scores),{t['agency_id']:t['base_score']+t['tiebreak_score'] for t in result.teams})

    def test_full_fifteen_second_watch_keeps_saved_result(self):
        self.open();self.start_event();result=self.play('lower',skip=False)
        before=self.dump();started=time.monotonic()
        self.wait(lambda:not self.page.replaying,seconds=len(self.page.frames)*.5+10)
        self.assertGreaterEqual(time.monotonic()-started,13)
        self.assertEqual(before,self.dump())
        self.assertEqual(result,self.page.current_result)

    def test_injured_disabled_and_future_type_not_leaked(self):
        self.open()
        self.assertIn('월요일 공개 예정',self.page.event_combo.itemText(1))
        self.start_event();own=next(r for r in self.page.event_state['rounds'] if 'ador' in r['agencies'])
        selection=self.service.specials.selection(own['id']);person=selection['options'][0]['player'].id
        with closing(self.service.database.connect()) as c,c:c.execute('UPDATE player_conditions SET injured=1,recovery_day=29 WHERE person_id=?',(person,))
        self.page.reload();self.select(own['stage'])
        table=self.page.lineup_table;row=next(i for i in range(table.rowCount()) if table.item(i,0).data(Qt.ItemDataRole.UserRole)==person)
        self.assertFalse(table.item(row,0).flags() & Qt.ItemFlag.ItemIsUserCheckable)
        self.assertIn('부상',table.item(row,7).text())
        self.assertNotIn(person,self.page.selected_ids())

    def test_unfinished_blocks_date_storage_failure_message_and_resume(self):
        self.open();self.start_event();before=self.dump()
        with patch.object(QMessageBox,'warning') as warning:
            __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
            self.assertIn('특별전',warning.call_args.args[2])
        self.assertEqual(before,self.dump())
        self.select('upper');self.choose()
        with patch('idol_manager.special_service.SpecialService._store',side_effect=sqlite3.OperationalError('injected')),patch.object(QMessageBox,'warning') as warning:
            QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton);self.wait(lambda:self.page.job is None)
            self.assertTrue(warning.called)
        self.assertFalse(self.page.replaying)
        self.assertEqual(self.service.specials.state(self.page.event_combo.currentData())['rounds'][0]['status'],'prepared')
        self.play('upper')

    def test_restart_after_group_and_mid_replay_resumes_from_stored_results(self):
        self.open();self.start_event();result=self.play('upper',skip=False);before=self.dump()
        self.window.close();self.open()
        self.assertEqual(before,self.dump());self.select('upper')
        with patch.object(self.service.specials,'play',side_effect=AssertionError('must not reroll')):
            QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.assertEqual(result,self.page.current_result)
        self.play('lower');self.play('final')

