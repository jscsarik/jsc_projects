"""One disposable Windows Qt selection/pick/profile smoke test."""
import os,json,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from idol_manager.ui.main_window import MainWindow
from tests import test_annual_draft as fixture

class AnnualUITest(unittest.TestCase):
    setUpClass=classmethod(fixture.AnnualTests.setUpClass.__func__)
    rows=fixture.AnnualTests.rows;dump=fixture.AnnualTests.dump;day=fixture.AnnualTests.day
    def setUp(self):fixture.AnnualTests.setUp(self)
    def test_select_sort_pick_profile_and_restart(self):
        self.day(196)
        player=self.service.draft_session.player_agency()
        order=[a for a in self.ranks if a!=player]+[player]
        with closing(self.db.connect()) as c,c:c.execute('UPDATE season_finals SET final_order_json=?',(json.dumps(order),))
        self.api.start();founding=self.rows('SELECT * FROM draft_picks ORDER BY pick_number')
        w=MainWindow(self.service);self.addCleanup(w.close)
        page=w.annual_page;page.auto.setChecked(False);w.show();w.show_annual();QTest.qWait(100)
        page.candidate_table.sortItems(2,Qt.SortOrder.DescendingOrder)
        candidates={p['id']:p for p in page.data['candidates']}
        row=None
        for i in range(page.candidate_table.rowCount()):
            pid=page.candidate_table.item(i,0).data(Qt.ItemDataRole.UserRole)
            self.assertEqual(page.candidate_table.item(i,1).text(),candidates[pid]['name'])
            if candidates[pid]['age']<17:row=i
        self.assertIsNotNone(row);page.candidate_table.setCurrentCell(row,0);QTest.qWait(20)
        selected=page.selected;self.assertTrue(page.pick_button.isEnabled())
        self.assertIn('추정 범위',page.detail_label.text())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(page.pick_button,Qt.MouseButton.LeftButton)
        QTest.qWait(50);self.assertEqual(self.api.state()['turn']['pick_number'],2)
        self.assertTrue(self.api.person(selected)['exact']);self.assertIn('공개 현재 능력치',page.detail_label.text())
        page.open_profile();QTest.qWait(30)
        self.assertIsNotNone(w.profiles.dialog)
        panel=w.profiles.dialog.panels[0];self.assertTrue(panel.data['annual_drafts'])
        w.profiles.dialog.close()
        self.assertEqual(founding,self.rows('SELECT * FROM draft_picks ORDER BY pick_number'))
        from idol_manager.service import GameService
        restored=GameService(self.root,self.path)
        self.assertEqual(restored.annual_draft.state()['turn']['pick_number'],2)
        target=Path(__file__).resolve().parents[1]/'.test-artifacts/annual21_windows.png'
        w.grab().save(str(target))
