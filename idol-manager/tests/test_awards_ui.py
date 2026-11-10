"""One native/offscreen card and profile smoke test on a fixed disposable DB."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.ui.main_window import MainWindow
from tests import test_awards as fixture

class AwardsUITest(unittest.TestCase):
    setUpClass=classmethod(fixture.AwardsTests.setUpClass.__func__)
    day=fixture.AwardsTests.day;rows=fixture.AwardsTests.rows;dump=fixture.AwardsTests.dump;complete_fixture=fixture.AwardsTests.complete_fixture
    def setUp(self):fixture.AwardsTests.setUp(self)
    def test_cards_enter_history_detail_and_profile_read_only(self):
        self.complete_fixture();self.service.awards.finalize(1);before=self.dump()
        w=MainWindow(self.service);self.addCleanup(w.close);w.show();w.show_awards();QTest.qWait(100)
        page=w.awards_page;self.assertEqual(len(page.cards),11);self.assertTrue(all(c.record for c in page.cards.values()))
        self.assertFalse(page.finalize_button.isEnabled());self.assertEqual(len(page.data['awards']),11)
        w.pages.setCurrentWidget(w.finals_page);w._offer_awards();self.assertIs(w.pages.currentWidget(),page)
        self.assertIn('포스트시즌 챔피언',page.notice.text())
        QTest.mouseClick(page.cards['mvp'].detail,Qt.MouseButton.LeftButton);self.assertTrue(page.detail_dialog.isVisible());page.detail_dialog.close()
        QTest.mouseClick(page.cards['mvp'].name,Qt.MouseButton.LeftButton)
        self.assertIsNotNone(w.profiles.dialog);panel=w.profiles.dialog.panels[0]
        self.assertTrue(panel.data['awards']);self.assertIn('시즌 개인상',panel.contract_label.text());w.profiles.dialog.close()
        for i in range(page.tabs.count()):page.tabs.setCurrentIndex(i);QTest.qWait(30)
        page.tabs.setCurrentIndex(0);QTest.qWait(50)
        root=Path(__file__).resolve().parents[1];w.grab().save(str(root/'.test-artifacts/awards20_windows.png'))
        self.assertEqual(before,self.dump())
