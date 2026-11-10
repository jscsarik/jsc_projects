"""Confirmed trainees appear in their own squad view; synthetic DB only."""
import os,unittest
from pathlib import Path
from contextlib import closing
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from idol_manager.config import ROOT
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from idol_manager.trainee_recruitment import finalize
from tests import test_founding_recruitment as fixtures

class TraineeViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixtures.FoundingTests.setUpClass.__func__(cls)
    def setUp(self):
        fixtures.FoundingTests.setUp(self)
        self.service=GameService(ROOT,self.path);self.window=MainWindow(self.service)
        self.addCleanup(self.window.close);self.window.resize(1400,950);self.window.show();self.window.show_squads();self.page=self.window.squad_page
    def test_application_not_owned_then_confirmation_added_to_trainee_tab(self):
        api=self.service.recruitment;person=api.candidates()[0].id
        api.apply('ador',[person]);self.page.reload();self.page.squad_tabs.setCurrentIndex(1)
        self.assertEqual(self.page.proxy.rowCount(),0)
        with closing(self.db.connect()) as c,c:c.execute('BEGIN IMMEDIATE');finalize(c,-7,policy=lambda people,rng:())
        self.page.reload();self.assertEqual(self.page.proxy.rowCount(),1)
        member=self.page.model.rows[self.page.proxy.mapToSource(self.page.proxy.index(0,2)).row()]
        self.assertEqual((member.id,member.squad),(person,'trainee'))
        self.assertIn('1명',self.page.squad_tabs.tabText(1));self.assertFalse(self.page.moves_group.isVisible());self.assertFalse(self.page.model.editable)
        self.page.squad_tabs.setCurrentIndex(0);self.assertEqual(self.page.proxy.rowCount(),16)
        self.assertNotIn(person,[self.page.proxy.index(r,2).data() for r in range(self.page.proxy.rowCount())])
        self.page.squad_tabs.setCurrentIndex(1);self.app.processEvents()
        out=ROOT/'reports/trainee_ui';out.mkdir(exist_ok=True);self.window.grab().save(str(out/'trainees.png'))
    def test_existing_owned_trainee_restored_on_reload(self):
        person=self.service.recruitment.candidates()[0].id
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id='ador',career_status='trainee' WHERE person_id=?",(person,))
        self.page.reload();self.page.filter_combo.setCurrentIndex(self.page.filter_combo.findData('trainee'))
        self.assertEqual(self.page.squad_tabs.currentIndex(),1);self.assertEqual(self.page.proxy.rowCount(),1)
        reopened=self.service.squads.snapshot();self.assertEqual(sum(m.squad=='trainee' for m in reopened.members),1)
        self.assertEqual(sum(m.squad in ('pro_pending','first_team','second_team') for m in reopened.members),16)
