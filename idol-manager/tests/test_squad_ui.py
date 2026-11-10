from contextlib import closing
from pathlib import Path
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from idol_manager.config import ROOT
from idol_manager.service import GameService
from idol_manager.squads import SquadError, SquadService
from idol_manager.database import Database
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.squad_model import SquadModel
from idol_manager.game_clock import GameDate


class SquadUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.class_temp=tempfile.TemporaryDirectory(prefix="idol_squad_ui_template_")
        cls.addClassCleanup(cls.class_temp.cleanup)
        cls.base=Path(cls.class_temp.name)
        photos=cls.base/"assets/idols"; photos.mkdir(parents=True)
        logos=cls.base/"assets/agencies"; logos.mkdir()
        image=QImage(100,140,QImage.Format.Format_RGB32); image.fill(QColor("#b9cfee"))
        for number in range(310):
            image.save(str(photos/f"가상 선수{number:03}.png"))
        image.save(str(logos/"ADOR.png"))
        service=GameService(cls.base)
        service.new_game(); __import__("tests.game_fixtures",fromlist=["legacy_save"]).legacy_save(service.database,schedule=True); service.draft_session.select_agency("ador")
        service.draft.start(rng=random.Random(4))
        for number,person in enumerate(service.draft.available_candidates()[:160],1):
            turn=service.draft.state().next_turn
            service.draft.pick(turn.agency_id,person.id,expected_pick_number=number)
        with closing(service.database.connect()) as connection,connection:
            connection.execute("UPDATE game_clock SET absolute_day=0")
        cls.pending=service.database.path
        cls.formed=cls.base/"formed.sqlite3"
        cls.copy_db(cls.pending,cls.formed)
        squads=SquadService(Database(cls.formed))
        squads.confirm_initial(tuple(member.id for member in squads.snapshot().members[:5]))

    @staticmethod
    def copy_db(source,target):
        target.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(target)) as dst:
            src.backup(dst)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="idol_squad_ui_")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"한글 게임"
        shutil.copytree(self.base/"assets",self.root/"assets")

    def open_window(self,formed=False,unfinished=False):
        path=self.root/"data/idol_manager.sqlite3"
        self.copy_db(self.formed if formed else self.pending,path)
        if unfinished:
            with closing(sqlite3.connect(path)) as connection,connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("DELETE FROM draft_state")
        self.service=GameService(self.root)
        self.window=MainWindow(self.service)
        self.addCleanup(self.window.close)
        self.window.show()
        QTest.mouseClick(self.window.squad_menu,Qt.MouseButton.LeftButton)
        self.page=self.window.squad_page

    def wait_until(self,predicate,timeout=15000):
        start=time.monotonic()
        while not predicate() and (time.monotonic()-start)*1000<timeout:
            QTest.qWait(10)
            time.sleep(.005)  # Let the Python AI worker run while driving Qt events.
        self.assertTrue(predicate(),"선수단 UI 작업 시간 초과")

    def protected(self):
        with closing(self.service.database.connect()) as connection:
            return {table:sorted(tuple(r) for r in connection.execute(f"SELECT * FROM {table}")) for table in
                    ("people","idols","abilities","agencies","draft_turns","draft_picks")}

    def test_initial_checkboxes_exact_five_cancel_then_confirm_all_ai(self):
        self.open_window()
        before=self.protected()
        self.assertEqual(self.page.model.rowCount(),16)
        self.assertFalse(self.page.confirm_button.isEnabled())
        self.assertIn("월",self.page.date_label.text())
        self.page.table.setCurrentIndex(self.page.proxy.index(0,0))
        QTest.keyClick(self.page.table,Qt.Key.Key_Space)
        self.assertEqual(len(self.page.model.selected_ids),1)
        for row in range(1,4):
            self.page.model.setData(self.page.model.index(row,0),Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole)
        self.assertFalse(self.page.confirm_button.isEnabled())
        self.page.model.setData(self.page.model.index(4,0),Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole)
        self.assertTrue(self.page.confirm_button.isEnabled())
        self.page.model.setData(self.page.model.index(5,0),Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole)
        self.assertFalse(self.page.confirm_button.isEnabled())
        self.page.model.setData(self.page.model.index(5,0),Qt.CheckState.Unchecked,Qt.ItemDataRole.CheckStateRole)
        chosen=set(self.page.model.selected_ids)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.No):
            QTest.mouseClick(self.page.confirm_button,Qt.MouseButton.LeftButton)
        self.assertFalse(self.service.squads.snapshot().initialized)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(self.page.confirm_button,Qt.MouseButton.LeftButton)
        self.wait_until(lambda:self.page.job is None)
        snapshot=self.service.squads.snapshot()
        self.assertEqual({m.id for m in snapshot.members if m.squad=="first_team"},chosen)
        self.assertTrue(snapshot.initialized)
        self.assertEqual(sum(m.squad=="second_team" for m in snapshot.members),11)
        self.assertTrue(self.page.table.isColumnHidden(0))
        self.assertFalse(self.page.confirm_button.isEnabled())
        self.assertTrue(self.window.new_button.isEnabled())
        self.assertIn("1군 5 / 5명",self.page.summary.text())
        self.assertEqual(before,self.protected())
        with closing(self.service.database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM squad_formations").fetchone()[0],10)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM squad_leaders WHERE agency_id!='ador'").fetchone()[0],18)

    def test_monday_ui_leaders_swap_clears_and_restart_preserves(self):
        self.open_window(formed=True)
        before=self.protected()
        first,second=self.page.first_combo.currentData(),self.page.second_combo.currentData()
        self.page.first_leader_combo.setCurrentIndex(self.page.first_leader_combo.findData(first))
        QTest.mouseClick(self.page.first_leader_button,Qt.MouseButton.LeftButton)
        self.page.second_leader_combo.setCurrentIndex(self.page.second_leader_combo.findData(second))
        QTest.mouseClick(self.page.second_leader_button,Qt.MouseButton.LeftButton)
        self.assertEqual(dict(self.service.squads.snapshot().leaders),{"first_team":first,"second_team":second})
        self.page.first_combo.setCurrentIndex(self.page.first_combo.findData(first))
        self.page.second_combo.setCurrentIndex(self.page.second_combo.findData(second))
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(self.page.swap_button,Qt.MouseButton.LeftButton)
        snapshot=self.service.squads.snapshot()
        self.assertEqual(snapshot.leaders,())
        self.assertEqual(next(m.squad for m in snapshot.members if m.id==first),"second_team")
        self.assertEqual(next(m.squad for m in snapshot.members if m.id==second),"first_team")
        self.page.first_leader_combo.setCurrentIndex(self.page.first_leader_combo.findData(second))
        QTest.mouseClick(self.page.first_leader_button,Qt.MouseButton.LeftButton)
        expected=self.service.squads.snapshot()
        self.window.close()
        service=GameService(self.root)
        self.assertEqual(service.squads.snapshot(),expected)
        self.assertEqual(before,self.protected())
        code="""
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import idol_manager.app as app
import os
os.environ['IDOL_MANAGER_USER_DATA']=str(Path(sys.argv[1])/'user_data')
app.ROOT=Path(sys.argv[1])
original=app.MainWindow.show
def show(window):
    original(window); window.show_squads()
    assert window.squad_page.snapshot.initialized
    assert dict(window.squad_page.snapshot.leaders)['first_team']==sys.argv[2]
    assert window.squad_page.model.rowCount()==16
    QTimer.singleShot(150,lambda:(window.close(),QApplication.instance().quit()))
app.MainWindow.show=show
from tests.start_menu_fixtures import enter_legacy_game
enter_legacy_game(app)
raise SystemExit(app.run())
"""
        result=subprocess.run([sys.executable,"-c",code,str(self.root),second],cwd=ROOT,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))

    def test_tuesday_controls_disabled_and_server_rejects_changes(self):
        self.open_window(formed=True)
        with closing(self.service.database.connect()) as connection,connection:
            connection.execute("UPDATE game_clock SET absolute_day=1")
        self.page.reload()
        self.assertEqual(self.page.model.rowCount(),16)
        self.assertIn("월요일이 아닙니다",self.page.notice.text())
        for button in (self.page.swap_button,self.page.promote_button,self.page.demote_button,
                       self.page.first_leader_button,self.page.second_leader_button):
            self.assertFalse(button.isEnabled())
        with self.assertRaisesRegex(SquadError,"월요일"):
            self.service.squads.swap(self.page.first_combo.currentData(),self.page.second_combo.currentData(),
                                    expected_revision=self.page.snapshot.revision)

    def test_unfinished_draft_page_does_not_reveal_current_abilities(self):
        self.open_window(unfinished=True)
        self.assertFalse(self.page.snapshot.ready)
        self.assertEqual(self.page.model.rowCount(),0)
        self.assertFalse(self.page.confirm_button.isEnabled())
        self.assertIn("드래프트",self.page.notice.text())
        self.assertFalse(self.page.swap_button.isEnabled())

    def test_public_stats_sort_filters_no_hidden_fields_and_separate_trainees(self):
        self.open_window(formed=True)
        self.page.table.sortByColumn(5,Qt.SortOrder.DescendingOrder)
        averages=[self.page.proxy.index(i,5).data(SquadModel.SORT_ROLE) for i in range(16)]
        self.assertEqual(averages,sorted(averages,reverse=True))
        self.page.table.sortByColumn(6,Qt.SortOrder.AscendingOrder)
        vocal=[self.page.proxy.index(i,6).data(SquadModel.SORT_ROLE) for i in range(16)]
        self.assertEqual(vocal,sorted(vocal))
        self.page.search.setText(self.page.model.rows[0].name)
        self.assertEqual(self.page.proxy.rowCount(),1)
        self.page.search.clear()
        self.page.filter_combo.setCurrentIndex(self.page.filter_combo.findData("first_team"))
        self.assertEqual(self.page.proxy.rowCount(),5)
        self.page.filter_combo.setCurrentIndex(self.page.filter_combo.findData("second_team"))
        self.assertEqual(self.page.proxy.rowCount(),11)
        with closing(self.service.database.connect()) as connection,connection:
            identity=connection.execute("SELECT person_id FROM roster_memberships WHERE career_status='unassigned' LIMIT 1").fetchone()[0]
            connection.execute("UPDATE roster_memberships SET career_status='trainee',agency_id='ador' WHERE person_id=?",(identity,))
        statements=[]; original=self.service.database.connect
        def traced():
            connection=original(); connection.set_trace_callback(statements.append); return connection
        with patch.object(self.service.database,"connect",side_effect=traced):
            self.page.reload()
        self.page.filter_combo.setCurrentIndex(self.page.filter_combo.findData("trainee"))
        self.assertEqual(self.page.proxy.rowCount(),1)
        self.assertIn("연습생 1명",self.page.summary.text())
        for private in ("potential","archetype","promising"):
            self.assertNotIn(private," ".join(statements).lower())
            self.assertNotIn(private,vars(self.page.model.rows[0]))
        for column in range(15):
            for role in (Qt.ItemDataRole.UserRole,Qt.ItemDataRole.ToolTipRole,Qt.ItemDataRole.WhatsThisRole):
                self.assertIsNone(self.page.model.index(0,column).data(role))

    def test_stale_ui_swap_reports_conflict_and_refreshes(self):
        self.open_window(formed=True)
        snapshot=self.page.snapshot
        first=self.page.first_combo.currentData()
        self.service.squads.set_leader("first_team",first,expected_revision=snapshot.revision)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,"warning") as warning:
            QTest.mouseClick(self.page.swap_button,Qt.MouseButton.LeftButton)
            warning.assert_called_once()
            self.assertIn("다른 창",warning.call_args.args[2])
        self.assertEqual(self.page.snapshot.revision,snapshot.revision+1)

    def test_formation_worker_in_native_application_event_loop(self):
        self.open_window()
        self.window.close()
        code="""
from pathlib import Path
import sys,time
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QMessageBox
import idol_manager.app as app
import os
os.environ['IDOL_MANAGER_USER_DATA']=str(Path(sys.argv[1])/'user_data')
app.ROOT=Path(sys.argv[1])
original=app.MainWindow.show
QMessageBox.question=lambda *a,**k:QMessageBox.StandardButton.Yes
def show(window):
    original(window); window.show_squads()
    for i in range(5):
        window.squad_page.model.setData(window.squad_page.model.index(i,0),Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole)
    window.squad_page.confirm_button.click()
    deadline=time.monotonic()+8
    timer=QTimer(window)
    def poll():
        if window.squad_page.job is None:
            ready=window.squad_page.snapshot.initialized
            timer.stop(); window.close(); QApplication.instance().exit(0 if ready else 2)
        elif time.monotonic()>deadline:
            timer.stop(); window.close(); QApplication.instance().exit(3)
    timer.timeout.connect(poll); timer.start(30)
app.MainWindow.show=show
from tests.start_menu_fixtures import enter_legacy_game
enter_legacy_game(app)
raise SystemExit(app.run())
"""
        result=subprocess.run([sys.executable,"-c",code,str(self.root)],cwd=ROOT,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        self.assertFalse(GameService(self.root).squads.snapshot().initialized)
        self.assertTrue(GameService(self.root,self.root/'user_data/saves/slot1/game.sqlite3').squads.snapshot().initialized)

    def test_real_completed_save_copy_squad_screen(self):
        path=self.root/"preview.sqlite3"
        source=ROOT/"data/idol_manager.sqlite3"
        with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as src,closing(sqlite3.connect(path)) as dst:
            src.backup(dst)
        service=GameService(ROOT,path)
        # This preview intentionally exercises Monday edits on a disposable copy.
        # The real save may now be on a different day.
        with closing(service.database.connect()) as connection,connection:
            connection.execute("UPDATE game_clock SET absolute_day=0")
        snapshot=service.squads.snapshot()
        if not snapshot.ready:
            self.skipTest("Actual project save has not completed its draft")
        window=MainWindow(service); self.addCleanup(window.close)
        window.resize(1680,980)
        window.show(); QTest.mouseClick(window.squad_menu,Qt.MouseButton.LeftButton)
        page=window.squad_page
        if not snapshot.initialized:
            for row in range(5):
                page.table.setCurrentIndex(page.proxy.index(row,0))
                QTest.keyClick(page.table,Qt.Key.Key_Space)
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
                QTest.mouseClick(page.confirm_button,Qt.MouseButton.LeftButton)
            self.wait_until(lambda:page.job is None)
            self.assertTrue(page.snapshot.initialized)
        snapshot=service.squads.snapshot()
        for squad,combo,button in (("first_team",page.first_leader_combo,page.first_leader_button),
                                   ("second_team",page.second_leader_combo,page.second_leader_button)):
            team=[m for m in snapshot.members if m.squad==squad]
            chosen=max(team,key=lambda m:m.leadership)
            combo.setCurrentIndex(combo.findData(chosen.id))
            self.assertTrue(button.isEnabled())
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
            self.assertEqual(dict(service.squads.snapshot().leaders)[squad],chosen.id)
        QTest.qWait(250)
        self.wait_until(lambda:not window.thumbnails.pending)
        target=ROOT/".test-artifacts/squad_management.png"; target.parent.mkdir(exist_ok=True)
        self.assertTrue(window.grab().save(str(target)))
        self.assertTrue(window.grab().save(str(ROOT/'.test-artifacts/date_leader_monday_fixed.png')))
        self.assertEqual(window.squad_page.model.rowCount(),16)
        expected=page.snapshot.leaders
        window.close()
        reopened=MainWindow(GameService(ROOT,path));self.addCleanup(reopened.close)
        reopened.show();QTest.mouseClick(reopened.squad_menu,Qt.MouseButton.LeftButton)
        self.assertEqual(reopened.squad_page.snapshot.leaders,expected)
        self.assertEqual(reopened.squad_page.first_leader_combo.currentData(),dict(expected)['first_team'])
        self.assertEqual(reopened.squad_page.second_leader_combo.currentData(),dict(expected)['second_team'])

    def test_global_date_at_top_visible_on_every_existing_page_and_squad_filter(self):
        self.open_window(formed=True)
        expected="시즌 1 · 정규 1주차 · 월요일"
        for button in (self.window.roster_menu,self.window.draft_menu,self.window.squad_menu,self.window.schedule_menu):
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
            self.assertEqual(self.window.game_date_label.text(),expected)
            self.assertTrue(self.window.game_date_label.isVisible())
            label=self.window.game_date_label
            self.assertLess(label.mapToGlobal(QPoint(0,label.height())).y(),self.window.pages.mapToGlobal(QPoint(0,0)).y()+1)
        QTest.mouseClick(self.window.squad_menu,Qt.MouseButton.LeftButton)
        for squad in ('first_team','second_team'):
            self.page.filter_combo.setCurrentIndex(self.page.filter_combo.findData(squad))
            self.assertEqual(self.window.game_date_label.text(),expected)
            self.assertEqual(self.page.date_label.text(),expected)

    def test_both_leaders_new_and_change_ids_agency_saved_and_reloaded(self):
        self.open_window(formed=True)
        before=self.protected()
        memberships=[(m.id,m.squad) for m in self.page.snapshot.members]
        with patch.object(self.service.squads,'set_leader',wraps=self.service.squads.set_leader) as save:
            for squad,combo,button in (('first_team',self.page.first_leader_combo,self.page.first_leader_button),
                                       ('second_team',self.page.second_leader_combo,self.page.second_leader_button)):
                people=[m.id for m in self.page.snapshot.members if m.squad==squad]
                for identity in people[:2]:
                    combo.setCurrentIndex(combo.findData(identity))
                    self.assertTrue(button.isEnabled())
                    QTest.mouseClick(button,Qt.MouseButton.LeftButton)
                    self.assertEqual(save.call_args.args,(squad,identity))
                    self.assertEqual(save.call_args.kwargs['expected_agency_id'],'ador')
                    self.assertEqual(dict(self.page.snapshot.leaders)[squad],identity)
                    self.assertEqual(combo.currentData(),identity)
                    self.assertIn('저장했습니다',self.page.action_status.text())
                    with closing(self.service.database.connect()) as connection:
                        self.assertEqual(connection.execute('SELECT person_id FROM squad_leaders WHERE agency_id=? AND squad=?',('ador',squad)).fetchone()[0],identity)
        expected=self.page.snapshot.leaders
        self.window.close()
        service=GameService(self.root)
        window=MainWindow(service);self.addCleanup(window.close)
        window.show();QTest.mouseClick(window.squad_menu,Qt.MouseButton.LeftButton)
        self.assertEqual(window.squad_page.snapshot.leaders,expected)
        self.assertTrue(window.squad_page.snapshot.initialized)
        self.assertEqual([(m.id,m.squad) for m in window.squad_page.snapshot.members],memberships)
        self.assertEqual(before,self.protected())

    def test_initial_formation_missing_leaders_does_not_reset_or_offer_initial_again(self):
        self.open_window(formed=True)
        snapshot=self.page.snapshot
        self.assertTrue(snapshot.initialized)
        self.assertEqual(snapshot.leaders,())
        self.assertIn('리더 미지정',self.page.leader_notice.text())
        self.assertFalse(self.page.confirm_button.isEnabled())
        self.assertTrue(self.page.first_leader_button.isEnabled())
        for _ in range(2):
            self.window.show_roster();self.window.show_squads()
            self.assertTrue(self.page.snapshot.initialized)
            self.assertEqual([(m.id,m.squad) for m in self.page.snapshot.members],[(m.id,m.squad) for m in snapshot.members])
            self.assertEqual(self.page.first_leader_combo.count(),6)
            self.assertEqual(self.page.second_leader_combo.count(),12)

    def test_pending_formation_non_monday_explains_both_disabled_reasons(self):
        self.open_window()
        with closing(self.service.database.connect()) as connection,connection:
            connection.execute('UPDATE game_clock SET absolute_day=2')
        self.window.show_squads()
        self.assertEqual(self.page.date_label.text(),str(GameDate(2)))
        self.assertEqual(self.window.game_date_label.text(),str(GameDate(2)))
        self.assertIn('최초 선수단 미편성',self.page.notice.text())
        self.assertIn('월요일이 아닙니다',self.page.notice.text())
        self.assertIn('최초 편성이 완료되지 않았습니다',self.page.leader_notice.text())
        self.assertIn('월요일',self.page.leader_notice.text())
        self.assertFalse(self.page.first_leader_button.isEnabled())
        self.assertFalse(self.page.second_leader_button.isEnabled())
        self.assertEqual(self.page.first_leader_button.toolTip(),self.page.leader_notice.text())

    def test_missing_player_has_visible_disabled_reason(self):
        self.open_window()
        self.service.new_game()  # Synthetic temporary fixture only.
        self.window.show_squads()
        self.assertIsNone(self.page.snapshot.agency)
        self.assertFalse(self.page.first_leader_button.isEnabled())
        self.assertFalse(self.page.second_leader_button.isEnabled())
        self.assertIn('플레이어 기획사가 선택되지 않았습니다',self.page.leader_notice.text())

    def test_tuesday_blocks_both_leaders_and_next_monday_allows_again(self):
        self.open_window(formed=True)
        before=self.protected()
        with closing(self.service.database.connect()) as connection,connection:
            connection.execute('UPDATE game_clock SET absolute_day=1')
        self.window.show_squads()
        for squad,combo,button in (('first_team',self.page.first_leader_combo,self.page.first_leader_button),
                                   ('second_team',self.page.second_leader_combo,self.page.second_leader_button)):
            identity=next(m.id for m in self.page.snapshot.members if m.squad==squad)
            self.assertFalse(button.isEnabled())
            self.assertIn('월요일',button.toolTip())
            with self.assertRaisesRegex(SquadError,'월요일'):
                self.service.squads.set_leader(squad,identity,expected_revision=self.page.snapshot.revision)
        self.assertEqual(self.page.snapshot.leaders,())
        with closing(self.service.database.connect()) as connection,connection:
            connection.execute('UPDATE game_clock SET absolute_day=7')
        self.window.show_squads()
        for squad,combo,button in (('first_team',self.page.first_leader_combo,self.page.first_leader_button),
                                   ('second_team',self.page.second_leader_combo,self.page.second_leader_button)):
            identity=next(m.id for m in self.page.snapshot.members if m.squad==squad)
            combo.setCurrentIndex(combo.findData(identity))
            self.assertTrue(button.isEnabled())
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
            self.assertEqual(dict(self.page.snapshot.leaders)[squad],identity)
        self.assertEqual(before,self.protected())

    def test_wrong_squad_id_shows_error_and_wrong_agency_rejected(self):
        self.open_window(formed=True)
        second=next(m.id for m in self.page.snapshot.members if m.squad=='second_team')
        self.page.first_leader_combo.addItem('잘못 전달된 ID',second)
        self.page.first_leader_combo.setCurrentIndex(self.page.first_leader_combo.findData(second))
        with patch.object(QMessageBox,'warning') as warning:
            QTest.mouseClick(self.page.first_leader_button,Qt.MouseButton.LeftButton)
            self.assertIn('1군 소속이 아닙니다',warning.call_args.args[2])
        self.assertEqual(self.page.snapshot.leaders,())
        first=next(m.id for m in self.page.snapshot.members if m.squad=='first_team')
        with self.assertRaisesRegex(SquadError,'기획사'):
            self.service.squads.set_leader('first_team',first,expected_revision=self.page.snapshot.revision,expected_agency_id='jyp')

    def test_ui_day_advance_and_page_entry_refresh_all_date_labels(self):
        self.open_window(formed=True)
        for squad in ('first_team','second_team'):
            state=self.service.squads.snapshot()
            identity=next(m.id for m in state.members if m.squad==squad)
            self.service.squads.set_leader(squad,identity,expected_revision=state.revision)
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        self.assertEqual(self.window.game_date_label.text(),str(GameDate(1)))
        self.assertEqual(self.page.date_label.text(),str(GameDate(1)))
        self.assertEqual(self.window.schedule_page.date_label.text(),str(GameDate(1)))
        self.assertFalse(self.page.first_leader_button.isEnabled())
        # Another window/service advances the same copied save. Menu entry refreshes.
        self.service.calendar.advance_day(expected_absolute_day=1)
        self.window.show_roster()
        self.assertEqual(self.window.game_date_label.text(),str(GameDate(2)))
        self.window.show_squads()
        self.assertEqual(self.page.date_label.text(),str(GameDate(2)))
        self.window.show_schedule()
        self.assertEqual(self.window.schedule_page.date_label.text(),str(GameDate(2)))

    def test_actual_save_copy_preserves_date_and_explains_current_gate(self):
        path=self.root/'current_copy.sqlite3'
        source=ROOT/'data/idol_manager.sqlite3'
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(path)) as dst:
            src.backup(dst)
        service=GameService(ROOT,path)
        window=MainWindow(service);self.addCleanup(window.close)
        window.show();QTest.mouseClick(window.squad_menu,Qt.MouseButton.LeftButton)
        expected=service.calendar.state().date
        self.assertEqual(window.game_date_label.text(),str(expected))
        self.assertEqual(window.squad_page.date_label.text(),str(expected))
        reason=window.squad_page._leader_block_reason()
        self.assertEqual(window.squad_page.first_leader_button.isEnabled(),not bool(reason))
        self.assertTrue(window.grab().save(str(ROOT/'.test-artifacts/date_leader_current_fixed.png')))


if __name__=="__main__":
    unittest.main()
