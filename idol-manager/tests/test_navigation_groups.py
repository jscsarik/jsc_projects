import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtTest import QTest
from tests import test_squad_ui as fixtures
from pathlib import Path

class NavigationTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.SquadUITests.setUpClass.__func__)
    setUp=fixtures.SquadUITests.setUp
    copy_db=staticmethod(fixtures.SquadUITests.copy_db)
    open_window=fixtures.SquadUITests.open_window
    def test_grouping_single_draft_and_standalone_records(self):
        self.open_window()
        groups={name:[b.text() for b in buttons] for name,buttons in self.window.nav_sections}
        self.assertEqual(list(groups),['아이돌','매니저','경기','시즌 관리','연말시즌'])
        self.assertEqual(groups['아이돌'],['아이돌 탐색 · 분석','선수 시장','드래프트'])
        self.assertEqual(groups['매니저'],['선수단 관리','경기 일정','성장 · 노화 · 훈련','기획사 재정'])
        self.assertEqual(groups['경기'],['정규 경기','특별전','포스트시즌']);self.assertEqual(groups['연말시즌'],['시상식'])
        self.assertTrue(self.window.annual_menu.isHidden());self.assertEqual(self.window.records_menu.property('navGroup'),'기타')
        self.assertEqual(sum(b.text()=='드래프트' for b,p in self.window.navigation_pages),1)
        self.window.resize(1350,1000);QTest.qWait(100)
        out=Path(__file__).resolve().parents[1]/'reports/navigation';out.mkdir(exist_ok=True);self.window.grab().save(str(out/'sidebar.png'))
    def test_initial_and_annual_route_share_menu_and_portrait_selector(self):
        self.open_window();w=self.window
        w.draft_menu.click();self.assertIs(w.pages.currentWidget(),w.annual_page);self.assertTrue(w.draft_menu.property('navActive'))
        w.initial_draft_history.click();self.assertIs(w.pages.currentWidget(),w.draft_page)
        w.annual_draft_link.click();self.assertIs(w.pages.currentWidget(),w.annual_page)
        w.resize(900,1300);w.portrait_layout.refresh();w.portrait_layout.sync_navigation()
        self.assertIn('드래프트',w.portrait_layout.nav.currentText())
        self.service.new_game();w.draft_menu.click();self.assertIs(w.pages.currentWidget(),w.draft_page)
        self.assertFalse(w.annual_draft_link.isVisible())
