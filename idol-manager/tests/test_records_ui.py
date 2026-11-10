"""One Windows/offscreen entry, numeric sort, details and comparison smoke check."""
import unittest
import time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from tests import test_records as fixture

class RecordsUITest(unittest.TestCase):
    setUpClass=classmethod(fixture.RecordsTests.setUpClass.__func__)
    dump=fixture.RecordsTests.dump
    def setUp(self):fixture.RecordsTests.setUp(self)
    def wait_records(self,page):
        deadline=time.monotonic()+10
        while page.rendered_generation!=page.query_generation and time.monotonic()<deadline:
            QTest.qWait(10);time.sleep(.005)
        self.assertEqual(page.rendered_generation,page.query_generation,page.notice.text())
    def test_entry_sort_profile_details_compare_and_no_writes(self):
        service=GameService(self.root,self.path);before=self.dump()
        window=MainWindow(service);self.addCleanup(window.close);window.show();window.show_records();QTest.qWait(120)
        page=window.records_page;self.wait_records(page);self.assertIs(window.pages.currentWidget(),page)
        self.assertNotIn('조회 오류',page.notice.text());self.assertEqual(page.league_table.rowCount(),20)
        for tab in (1,2,3,4):
            page.tabs.setCurrentIndex(tab);self.wait_records(page);self.assertNotIn('조회 오류',page.notice.text())
        page.tabs.setCurrentIndex(1);self.wait_records(page);table=page.player_table
        table.sortItems(5,Qt.SortOrder.DescendingOrder);self.assertEqual(table.item(0,5).data(Qt.ItemDataRole.DisplayRole),10)
        self.assertEqual(table.item(0,0).data(Qt.ItemDataRole.UserRole),'p0')
        table.setCurrentCell(0,0)
        QTest.mouseClick(page.player_detail_button,Qt.MouseButton.LeftButton);QTest.qWait(20)
        self.assertTrue(page.dialogs);page.dialogs[-1].close()
        # Same single-click path used by the existing common profile controller.
        window.profiles.clicked(table,table.model().index(0,0));QTest.qWait(20)
        self.assertIsNotNone(window.profiles.dialog);self.assertEqual(window.profiles.dialog.panels[0].person,'p0');window.profiles.dialog.close()
        page.tabs.setCurrentIndex(4);page.left.setCurrentIndex(page.left.findData('p0'));page.right.setCurrentIndex(page.right.findData('p2'));self.wait_records(page)
        rows={page.comparison_table.item(i,0).text():i for i in range(page.comparison_table.rowCount())}
        ca=page.comparison_table.item(rows['CA (현재 / 추정)'],2).text();self.assertIn('~',ca)
        page.compare_kind.setCurrentIndex(1);self.wait_records(page);self.assertIn('연습생 제외',page.comparison_note.text())
        page.agency_detail(self.a,1);QTest.qWait(20);self.assertTrue(page.dialogs);page.dialogs[-1].close()
        page.postseason_detail(1);QTest.qWait(20);self.assertTrue(page.dialogs);page.dialogs[-1].close()
        window._records_awards(1);QTest.qWait(20);self.assertIs(window.pages.currentWidget(),window.awards_page);self.assertEqual(window.awards_page.season.currentData(),1)
        window.show_records();self.assertEqual(page.compare_kind.currentIndex(),1)
        page.tabs.setCurrentIndex(0);QTest.qWait(50)
        root=Path(__file__).resolve().parents[1];window.grab().save(str(root/'.test-artifacts/records24_windows.png'))
        self.assertEqual(before,self.dump())
