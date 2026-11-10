import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from tests import test_season32 as fixture
from idol_manager.market_service import _move,_new_contract

class ProfileDebutLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day
    def test_saved_trainee_debut_in_both_contract_views_and_draft_unchanged(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from idol_manager.ui.main_window import MainWindow
        app=QApplication.instance() or QApplication([]);self.day(91)
        p=self.rows('SELECT person_id FROM initial_draft_undrafted LIMIT 1')[0][0]
        with closing(self.db.connect()) as c,c:
            _move(c,p,'ador','trainee','trainee')
            outgoing=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' AND person_id NOT IN (SELECT person_id FROM squad_leaders) LIMIT 1").fetchone()[0]
            _move(c,outgoing,None,'fa','release')
            contract=_new_contract(c,p,'ador',30000000,1,'pro');_move(c,p,'ador','second_team','debut',contract)
        self.assertEqual(self.service.profiles.get(p)['trainee_debut_season'],1)
        window=MainWindow(self.service);self.addCleanup(window.close);window.profiles.open(p);QTest.qWait(60)
        panel=window.profiles.dialog.panels[0]
        self.assertIn('최초 지명: 시즌 1 연습생 데뷔',panel.contract_label.text())
        self.assertIn('최초 지명: 시즌 1 연습생 데뷔',panel.contract_detail.text())
        self.day(315);panel.reload();self.assertIn('시즌 1 연습생 데뷔',panel.contract_label.text())
        founder=self.rows('SELECT person_id FROM draft_picks ORDER BY pick_number LIMIT 1')[0][0]
        data=self.service.profiles.get(founder);self.assertIsNotNone(data['draft']);self.assertIsNone(data['trainee_debut_season'])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks'),[(160,)])
