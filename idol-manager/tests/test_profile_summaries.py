"""Compact growth/contract UI. Display-only fixture injection, no settlement."""
from pathlib import Path
import unittest
from PySide6.QtTest import QTest
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from tests import test_records as fixture

class ProfileSummaryTests(unittest.TestCase):
    setUpClass=classmethod(fixture.RecordsTests.setUpClass.__func__)
    dump=fixture.RecordsTests.dump
    def setUp(self):fixture.RecordsTests.setUp(self)
    def test_compact_growth_contract_details_and_private_candidate(self):
        service=GameService(self.root,self.path);before=self.dump();w=MainWindow(service);self.addCleanup(w.close);w.show();QTest.qWait(80)
        w.profiles.open('p0');dialog=w.profiles.dialog;panel=dialog.panels[0]
        panel.tabs.setCurrentIndex(4);QTest.qWait(70)
        panel.data['growth']=[dict(day=7,kind='growth',role='second_team',age_before=20,age_after=20,deltas=[1,0,0,0,0,0,0,0],changes=[dict(skill='vocal',applied=1,kind='second_net')],reasons=[]),
            dict(day=14,kind='growth',role='second_team',age_before=20,age_after=20,deltas=[0]*8,changes=[],reasons=[])]
        panel.render_growth();self.assertEqual(panel.growth_table.columnCount(),5);self.assertEqual(panel.growth_table.rowCount(),1)
        self.assertLessEqual(len(panel.growth_summary.text().splitlines()),2)
        self.assertIn('보컬 +1',panel.growth_table.item(0,3).text());self.assertTrue(panel.growth_detail.isHidden())
        panel.growth_zero.setChecked(True);self.assertEqual(panel.growth_table.rowCount(),2)
        panel.growth_zero.setChecked(False);panel.tabs.setCurrentIndex(5);QTest.qWait(70)
        self.assertLessEqual(len(panel.contract_label.text().splitlines()),6);self.assertIn('시즌 개인상',panel.contract_label.text())
        self.assertNotIn('계약금',panel.contract_label.text());self.assertTrue(panel.contract_detail.isHidden())
        panel.contract_more.click();QTest.qWait(100);self.assertTrue(panel.contract_detail.isVisible())
        wrapper=getattr(panel.contract_detail,'_text_pages_wrapper',None)
        if wrapper is not None:self.assertTrue(wrapper.isVisible())
        panel.contract_more.click();QTest.qWait(30);self.assertTrue(panel.contract_detail.isHidden())
        if wrapper is not None:self.assertTrue(wrapper.isHidden())
        dialog.grab().save(str(Path(__file__).resolve().parents[1]/'.test-artifacts/profile_contract_compact_windows.png'))
        dialog.close();w.profiles.open('p2');panel=w.profiles.dialog.panels[0]
        self.assertEqual(panel.contract_detail.text(),'');self.assertTrue(panel.contract_more.isHidden());self.assertEqual(panel.growth_table.rowCount(),0)
        w.profiles.dialog.close();self.assertEqual(before,self.dump())
