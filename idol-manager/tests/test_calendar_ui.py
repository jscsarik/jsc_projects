from contextlib import closing
from pathlib import Path
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor,QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox

from idol_manager.config import ROOT
from idol_manager.game_clock import GameDate
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.schedule_page import DatePreviewDialog
from tests.game_fixtures import complete_initial_setup


class CalendarUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="idol_calendar_ui_")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"한글 게임"
        folder=self.root/"assets/idols"; folder.mkdir(parents=True)
        image=QImage(80,100,QImage.Format.Format_RGB32); image.fill(QColor("#b0c9f0"))
        for number in range(200):
            image.save(str(folder/f"아이돌{number:03}.png"))
        self.service=GameService(self.root); self.service.new_game()
        complete_initial_setup(self.service.database)
        self.service.calendar.initialize()
        self.window=MainWindow(self.service); self.addCleanup(self.window.close)
        self.window.show()
        QTest.mouseClick(self.window.schedule_menu,Qt.MouseButton.LeftButton)
        self.page=self.window.schedule_page

    def dump(self):
        with closing(self.service.database.connect()) as connection:
            return list(connection.iterdump())

    def test_day_button_transitions_then_readable_unprocessed_match_guard(self):
        self.assertEqual(self.window.game_date_label.text(),"시즌 1 · 정규 1주차 · 월요일")
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes):
            __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        self.assertEqual(self.service.calendar.state().date,GameDate(1))
        self.assertIn("화요일",self.window.game_date_label.text())
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        self.assertEqual(self.service.calendar.state().date,GameDate(2))
        before=self.dump()
        with patch.object(QMessageBox,"warning") as warning:
            __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
            warning.assert_called_once()
            self.assertIn("미처리",warning.call_args.args[2])
        self.assertEqual(before,self.dump())
        self.assertIn("수요일",self.window.game_date_label.text())

    def test_full_24_weeks_week_selection_agency_filter_and_current_week(self):
        QTest.mouseClick(self.page.all_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.page.model.rowCount(),591)
        self.page.agency_combo.setCurrentIndex(self.page.agency_combo.findData("ador"))
        self.assertEqual(self.page.model.rowCount(),123)
        self.assertEqual(sum(e.match_type=="정규" for e in self.page.model.rows),117)
        self.page.week_combo.setCurrentIndex(self.page.week_combo.findData(4))
        expected=self.service.calendar.entries(1,week=4,agency_id="ador")
        self.assertEqual(tuple(self.page.model.rows),expected)
        self.assertTrue(all(e.week==4 for e in self.page.model.rows))
        self.assertEqual(sum(e.match_type=="특별전" for e in self.page.model.rows),1)
        QTest.mouseClick(self.page.current_button,Qt.MouseButton.LeftButton)
        self.assertTrue(all(e.week==1 for e in self.page.model.rows))

    def test_future_regular_contents_publish_on_monday_and_no_real_times_or_results(self):
        self.page.week_combo.setCurrentIndex(self.page.week_combo.findData(2))
        regular=[e for e in self.page.model.rows if e.match_type=="정규"]
        self.assertTrue(regular and all(e.content=="월요일 공개 예정" for e in regular))
        QTest.mouseClick(self.page.current_button,Qt.MouseButton.LeftButton)
        self.assertTrue(all(e.published for e in self.page.model.rows))
        for row in range(self.page.model.rowCount()):
            for column in range(self.page.model.columnCount()):
                value=str(self.page.model.index(row,column).data() or "")
                self.assertIsNone(re.search(r"\b\d{1,2}:\d{2}\b",value))
        for label in self.page.model.HEADERS:
            self.assertNotIn("승패",label)
            self.assertNotIn("승점",label)
            self.assertNotIn("결과",label)

    def test_test_preview_simulates_next_season_without_any_saved_changes(self):
        before=self.dump(); seen=[]
        def respond():
            dialog=QApplication.activeModalWidget()
            if not isinstance(dialog,DatePreviewDialog):
                QTimer.singleShot(10,respond); return
            dialog.days.setValue(217)
            seen.append(dialog.result.text())
            dialog.accept()
        QTimer.singleShot(0,respond)
        QTest.mouseClick(self.page.preview_button,Qt.MouseButton.LeftButton)
        self.assertEqual(seen,["시즌 2 · 정규 1주차 · 월요일"])
        self.assertEqual(before,self.dump())
        self.assertEqual(self.service.calendar.state().date,GameDate(0))

    def test_special_type_hidden_in_table_until_its_week_monday_then_stays_visible(self):
        self.page.week_combo.setCurrentIndex(self.page.week_combo.findData(4))
        special = [(i,e) for i,e in enumerate(self.page.model.rows) if e.match_type=='특별전']
        self.assertEqual(len(special),1)
        self.assertEqual(self.page.model.index(special[0][0],4).data(),'월요일 공개 예정')
        for day in (21,28):
            with closing(self.service.database.connect()) as connection,connection:
                connection.execute('UPDATE game_clock SET absolute_day=?',(day,))
            self.page.reload()
            self.page.week_combo.setCurrentIndex(self.page.week_combo.findData(4))
            special = [(i,e) for i,e in enumerate(self.page.model.rows) if e.match_type=='특별전']
            self.assertTrue(special[0][1].published)
            self.assertIn(self.page.model.index(special[0][0],4).data(),('대학축제','K-POP 페스티벌','아이돌 체육대회'))

    def test_real_app_process_reopens_saved_date_and_same_schedule(self):
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        before=self.dump()
        self.window.close()
        script="""
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
    original(window); window.show_schedule()
    assert window.service.calendar.state().date.absolute_day==1
    assert '화요일' in window.game_date_label.text()
    window.schedule_page.all_button.click()
    assert window.schedule_page.model.rowCount()==591
    QTimer.singleShot(150,lambda:(window.close(),QApplication.instance().quit()))
app.MainWindow.show=show
from tests.start_menu_fixtures import enter_legacy_game
enter_legacy_game(app)
raise SystemExit(app.run())
"""
        result=subprocess.run([sys.executable,"-c",script,str(self.root)],cwd=ROOT,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        self.assertEqual(before,self.dump())

    def test_real_save_copy_schedule_screen_capture(self):
        path=self.root/"preview.sqlite3"; source=ROOT/"data/idol_manager.sqlite3"
        with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as src,closing(sqlite3.connect(path)) as dst:
            src.backup(dst)
        service=GameService(ROOT,path)
        window=MainWindow(service); self.addCleanup(window.close)
        window.resize(1720,960); window.show(); window.show_schedule()
        QTest.mouseClick(window.schedule_page.all_button,Qt.MouseButton.LeftButton)
        QTest.qWait(150)
        target=ROOT/".test-artifacts/season_schedule.png"; target.parent.mkdir(exist_ok=True)
        self.assertTrue(window.grab().save(str(target)))
        self.assertEqual(window.schedule_page.model.rowCount(),591)


if __name__=="__main__":
    unittest.main()
