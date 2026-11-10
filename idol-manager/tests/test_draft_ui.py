from contextlib import closing
from pathlib import Path
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from idol_manager.config import ROOT
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow


class DraftUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="idol_draft_ui_")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"한글 게임"
        folder=self.root/"assets/idols"; folder.mkdir(parents=True)
        image=QImage(120,160,QImage.Format.Format_RGB32); image.fill(QColor("#b8ccef"))
        for i in range(310):
            image.save(str(folder/f"후보{i:03}.png"))
        self.service=GameService(self.root)
        self.service.new_game()
        from tests.game_fixtures import legacy_save
        legacy_save(self.service.database,schedule=True)
        self.window=MainWindow(self.service)
        self.addCleanup(self.window.close)
        self.window.show()
        QTest.mouseClick(self.window.draft_menu,Qt.MouseButton.LeftButton)
        self.page=self.window.draft_page

    def wait_until(self,predicate,timeout=10000):
        start=time.monotonic()
        while not predicate() and (time.monotonic()-start)*1000<timeout:
            QTest.qWait(10)
        self.assertTrue(predicate(),"UI 자동 진행 시간 초과")

    def select_agency(self,agency_id="ador"):
        self.page.agency_combo.setCurrentIndex(self.page.agency_combo.findData(agency_id))
        QTest.mouseClick(self.page.save_agency_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.service.draft_session.player_agency(),agency_id)

    def snapshot(self):
        with closing(self.service.database.connect()) as connection:
            return list(connection.iterdump())

    def age_16(self):
        candidates=self.service.draft.available_candidates()[:12]
        with closing(self.service.database.connect()) as connection,connection:
            connection.executemany("UPDATE idols SET age=16 WHERE person_id=?",[(p.id,) for p in candidates])
        self.page.reload()
        return candidates

    def answer_age_dialog(self,approve,seen):
        def answer():
            dialog=QApplication.activeModalWidget()
            if not isinstance(dialog,QMessageBox):
                QTimer.singleShot(10,answer); return
            seen.append((dialog.text(),dialog.detailedText()))
            prefix="16세 후보를" if approve else "취소"
            target=next((b for b in dialog.buttons() if b.text().startswith(prefix)),None)
            if target:
                target.click()
            else:
                dialog.reject()
        QTimer.singleShot(0,answer)

    def test_age_cancel_exact_12_names_no_database_changes(self):
        targets=self.age_16()
        self.select_agency()
        before=self.snapshot(); seen=[]
        self.answer_age_dialog(False,seen)
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.assertEqual(len(seen),1)
        self.assertIn("다음 12명",seen[0][0])
        self.assertIn("백업",seen[0][0])
        for person in targets:
            self.assertIn(person.name,seen[0][0]); self.assertIn(person.id,seen[0][1])
        self.assertEqual(before,self.snapshot())
        self.assertEqual(self.service.draft.state().status,"not_started")
        self.assertEqual(len(self.service.draft.age_issues()),12)

    def test_age_explicit_approval_only_age_changes_backup_then_starts(self):
        targets=self.age_16(); self.select_agency()
        with closing(self.service.database.connect()) as connection:
            abilities=[tuple(r) for r in connection.execute("SELECT * FROM abilities ORDER BY person_id,skill")]
            candidates=[tuple(r) for r in connection.execute("SELECT * FROM initial_draft_candidates ORDER BY person_id")]
        seen=[]; self.answer_age_dialog(True,seen)
        with patch.object(self.service.draft,"correct_legacy_ages",wraps=self.service.draft.correct_legacy_ages) as correct:
            QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
            self.page.ai_timer.stop()
            correct.assert_called_once_with(approved=True,person_ids=tuple(p.id for p in sorted(targets,key=lambda x:x.name)))
        self.assertEqual(len(seen),1)
        self.assertEqual(self.service.draft.age_issues(),[])
        self.assertEqual(self.service.draft.state().status,"in_progress")
        self.assertFalse(self.page.agency_combo.isEnabled())
        with closing(self.service.database.connect()) as connection:
            self.assertEqual(abilities,[tuple(r) for r in connection.execute("SELECT * FROM abilities ORDER BY person_id,skill")])
            self.assertEqual(candidates,[tuple(r) for r in connection.execute("SELECT * FROM initial_draft_candidates ORDER BY person_id")])
            receipts=connection.execute("SELECT backup_path FROM draft_age_corrections").fetchall()
        self.assertEqual(len(receipts),12)
        self.assertTrue(all(Path(row[0]).is_file() for row in receipts))

    def test_player_confirmation_search_sort_photo_and_window_restart(self):
        ids=sorted(a.id for a in self.service.agencies()); random.Random(8).shuffle(ids)
        self.select_agency(ids[0])
        self.service.draft.start(rng=random.Random(8)); self.page.reload()
        self.assertFalse(self.page.pick_button.isEnabled())
        self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
        selected=self.page.selected_candidate()
        self.assertTrue(self.page.pick_button.isEnabled())
        self.assertFalse(self.page.portrait.pixmap().isNull())
        pixmap=self.page.portrait.pixmap()
        self.assertAlmostEqual(pixmap.width()/pixmap.height(),.75,delta=.02)
        self.page.search.setText(selected.name)
        self.assertEqual(self.page.proxy.rowCount(),1)
        self.page.search.clear()
        self.page.candidate_table.sortByColumn(2,Qt.SortOrder.AscendingOrder)
        ages=[self.page.proxy.index(i,2).data() for i in range(self.page.proxy.rowCount())]
        self.assertEqual(ages,sorted(ages))
        self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
        before=self.service.draft.state()
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.No):
            QTest.mouseClick(self.page.pick_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.service.draft.state(),before)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(self.page.pick_button,Qt.MouseButton.LeftButton)
        self.page.ai_timer.stop()
        expected=(self.service.draft.state(),self.service.draft.turn_order(),self.service.draft.picks())
        self.assertEqual(expected[0].picks_made,1)
        self.assertEqual(self.page.candidate_model.rowCount(),199)
        self.window.close()
        reopened_service=GameService(self.root)
        reopened=MainWindow(reopened_service); self.addCleanup(reopened.close)
        reopened.draft_page._paused=True
        reopened.show(); reopened.show_draft()
        self.assertEqual((reopened_service.draft.state(),reopened_service.draft.turn_order(),reopened_service.draft.picks()),expected)
        self.assertEqual(reopened.draft_page.agency_combo.currentData(),ids[0])
        self.assertFalse(reopened.draft_page.agency_combo.isEnabled())
        self.assertEqual(reopened.draft_page.history_model.rowCount(),1)
        script = """
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import idol_manager.app as app
import os
os.environ['IDOL_MANAGER_USER_DATA']=str(Path(sys.argv[1])/'user_data')
app.ROOT=Path(sys.argv[1])
original_show=app.MainWindow.show
def show_and_verify(window):
    window.draft_page._paused=True
    original_show(window)
    window.show_draft()
    assert window.draft_page.snapshot.player_agency_id==sys.argv[2]
    assert window.draft_page.snapshot.state.picks_made==1
    assert window.draft_page.history_model.rowCount()==1
    assert not window.draft_page.agency_combo.isEnabled()
    QTimer.singleShot(200,lambda: (window.close(),QApplication.instance().quit()))
app.MainWindow.show=show_and_verify
from tests.start_menu_fixtures import enter_legacy_game
enter_legacy_game(app)
raise SystemExit(app.run())
"""
        result=subprocess.run([sys.executable,"-c",script,str(self.root),ids[0]],cwd=ROOT,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))

    def test_windows_ui_full_160_turns_ai_stops_at_player_and_completed_is_locked(self):
        self.select_agency()
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes),patch.object(self.service.draft,"pick",wraps=self.service.draft.pick) as shared_pick:
            while self.service.draft.state().status=="in_progress":
                turn=self.service.draft.state().next_turn
                if turn.agency_id=="ador":
                    self.assertFalse(self.page.ai_timer.isActive())
                    self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
                    self.assertTrue(self.page.pick_button.isEnabled())
                    QTest.mouseClick(self.page.pick_button,Qt.MouseButton.LeftButton)
                else:
                    self.assertFalse(self.page.pick_button.isEnabled())
                    QTest.mouseClick(self.page.fast_button,Qt.MouseButton.LeftButton)
                    self.wait_until(lambda: self.service.draft.state().status=="completed" or self.service.draft.state().next_turn.agency_id=="ador")
            self.assertEqual(shared_pick.call_count,160)
        self.assertEqual(self.page.history_model.rowCount(),160)
        self.assertEqual(self.page.candidate_model.rowCount(),40)
        self.assertFalse(self.page.start_button.isEnabled())
        self.assertFalse(self.page.pick_button.isEnabled())
        self.assertFalse(self.page.fast_button.isEnabled())
        self.assertFalse(self.page.ai_timer.isActive())
        self.assertIn("각 16명",self.page.notice.text())
        self.service.draft_session.validate_completion()
        self.assertEqual(len(self.service.draft.undrafted_candidates()),40)
        for agency in self.service.agencies():
            self.assertEqual(len(self.service.agency_roster(agency.id)),16)
            self.assertEqual(agency.funds_krw,1_000_000_000)
        self.assertEqual(len({p.person_id for p in self.service.draft.picks()}),160)

    def test_blind_ui_payload_roles_missing_photo_and_sql_queries(self):
        self.assertEqual(self.page.candidate_model.HEADERS[:3],("사진","이름","나이"))
        self.assertEqual(self.page.candidate_model.columnCount(),13)
        statements=[]; original=self.service.database.connect
        def traced():
            connection=original(); connection.set_trace_callback(statements.append); return connection
        with patch.object(self.service.database,"connect",side_effect=traced):
            self.page.reload()
            self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
        for role in (Qt.ItemDataRole.ToolTipRole,Qt.ItemDataRole.UserRole,Qt.ItemDataRole.WhatsThisRole,Qt.ItemDataRole.AccessibleTextRole):
            for column in range(3):
                self.assertIsNone(self.page.candidate_model.index(0,column).data(role))
        for forbidden in ("abilities","potential","average","health","archetype","market_value"):
            self.assertNotIn(forbidden," ".join(statements).lower())
        selected=self.page.selected_candidate()
        (self.root/selected.photo_path).unlink()
        self.page.portrait.show_photo(selected.photo_path)
        self.assertIn("불러올 수 없습니다",self.page.portrait.text())

    def test_stale_player_request_has_readable_error_and_refreshes(self):
        ids=sorted(a.id for a in self.service.agencies()); random.Random(4).shuffle(ids)
        self.select_agency(ids[0]); self.service.draft.start(rng=random.Random(4)); self.page.reload()
        self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
        def advance_then_confirm(*args,**kwargs):
            turn=self.service.draft.state().next_turn
            self.service.draft.pick(turn.agency_id,self.page.selected_candidate().id,expected_pick_number=turn.pick_number)
            return QMessageBox.StandardButton.Yes
        with patch.object(QMessageBox,"question",side_effect=advance_then_confirm),patch.object(QMessageBox,"warning") as warning:
            QTest.mouseClick(self.page.pick_button,Qt.MouseButton.LeftButton)
            warning.assert_called_once()
            self.assertIn("지명",warning.call_args.args[2])
        self.page.ai_timer.stop()
        self.assertEqual(self.service.draft.state().picks_made,1)
        self.assertEqual(self.page.candidate_model.rowCount(),199)

    def test_real_photos_draft_page_screenshot_in_temporary_save(self):
        service=GameService(ROOT,self.root/"preview.sqlite3")
        service.new_game(); service.draft_session.select_agency("ador")
        service.draft.start(rng=random.Random(3))
        window=MainWindow(service); self.addCleanup(window.close)
        window.draft_page._paused=True
        window.show(); window.show_draft()
        window.draft_page.candidate_table.setCurrentIndex(window.draft_page.proxy.index(0,1))
        QTest.qWait(200)
        self.wait_until(lambda: not window.thumbnails.pending)
        target=ROOT/".test-artifacts/draft_ui.png"; target.parent.mkdir(exist_ok=True)
        self.assertTrue(window.grab().save(str(target)))
        self.assertEqual(window.draft_page.candidate_model.rowCount(),200)


if __name__=="__main__":
    unittest.main()
