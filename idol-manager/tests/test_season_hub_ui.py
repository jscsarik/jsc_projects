import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from tests import test_season32 as fixture
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.season_hub import read_summary,availability
from idol_manager.game_clock import GameDate

class SeasonHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    day=fixture.Season32Tests.day
    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())
    def test_phase_gates_across_seasons(self):
        for season in (1,2):
            for offset,mid,end in ((0,False,False),(7,False,False),(84,False,False),(91,True,False),(97,True,False),(98,False,False),(182,False,False),(203,False,True),(210,False,True),(217,False,True),(223,False,True)):
                d=GameDate((season-1)*224+offset)
                self.assertEqual((availability(d)[0],availability(d,True)[0]),(mid,end))
    def test_read_only_summary_and_persisted_refresh(self):
        for day,wrap in ((91,False),(203,True),(210,True),(217,True),(315,False),(427,True)):
            self.day(day);before=self.dump()
            a=read_summary(self.db,wrap);b=read_summary(self.service.database,wrap)
            self.assertEqual(a,b);self.assertEqual(before,self.dump());self.assertEqual(len(a['ranks']),10)
    def test_qt_buttons_links_small_window_and_reload(self):
        self.day(91);w=MainWindow(self.service);self.addCleanup(w.close)
        w.resize(900,700);w.show();QTest.qWait(100)
        self.assertTrue(w.midseason_menu.isEnabled());self.assertFalse(w.wrapup_menu.isEnabled())
        w.nav_scroll.ensureWidgetVisible(w.midseason_menu);QTest.qWait(30)
        QTest.mouseClick(w.midseason_menu,Qt.MouseButton.LeftButton)
        self.assertIs(w.pages.currentWidget(),w.midseason_page)
        self.assertNotIn('조회 실패',w.midseason_page.notice.text())
        w.midseason_page.actions['squad'].click();self.assertIs(w.pages.currentWidget(),w.squad_page)
        self.day(203);w.refresh_calendar();self.assertTrue(w.wrapup_menu.isEnabled());self.assertFalse(w.midseason_menu.isEnabled())
        w.nav_scroll.ensureWidgetVisible(w.wrapup_menu);QTest.qWait(30);QTest.mouseClick(w.wrapup_menu,Qt.MouseButton.LeftButton)
        self.assertIs(w.pages.currentWidget(),w.wrapup_page);self.assertNotIn('조회 실패',w.wrapup_page.notice.text())
        before=self.dump();w.wrapup_page.reload();self.assertEqual(before,self.dump())
        self.assertTrue(w.portrait_layout.nav.isVisible());self.assertIn(w.coach_panel.toggle,w.portrait_layout.buttons)
        w.resize(1200,700);QTest.qWait(120)
        self.assertTrue(w.coach_panel.isVisible());self.assertTrue(w.new_button.isVisible())
        self.assertEqual(w.nav_scroll.horizontalScrollBar().maximum(),0)
        from pathlib import Path
        w.grab().save(str(Path(__file__).resolve().parents[1]/'reports/season_hub_0372.png'))
        for day in (0,7,98,182,224):
            self.day(day);w.refresh_calendar();self.assertFalse(w.midseason_menu.isEnabled());self.assertFalse(w.wrapup_menu.isEnabled())

    def test_real_saved_match_totals(self):
        self.day(9);self.service.calendar.ensure_current_schedule()
        match=next(m for m in self.service.matches.fixtures() if any(a[0]=='ador' for a in m.agencies))
        self.service.matches.play(match.id)
        self.day(91);before=self.dump();data=read_summary(self.db)
        self.assertTrue(data['players']);self.assertEqual(sum(p[1] for p in data['players']),match.required)
        self.assertEqual(before,self.dump())
