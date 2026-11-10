"""UI-only checks with existing disposable roster/market fixtures."""
from contextlib import closing
from pathlib import Path
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.ui.main_window import MainWindow
from tests import test_market as fixture


class ReadabilityTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    rows=fixture.MarketTests.rows;dump=fixture.MarketTests.dump;member=fixture.MarketTests.member
    day=fixture.MarketTests.day
    def setUp(self):
        fixture.MarketTests.setUp(self)
        self.w=MainWindow(self.service);self.addCleanup(self.w.close);self.w.resize(1700,1000);self.w.show();QTest.qWait(80)
    def test_navigation_and_squad_rest_columns_are_readonly(self):
        self.assertIs(self.w.pages.currentWidget(),self.w.explorer_page)
        self.assertTrue(self.w.roster_menu.isHidden())
        self.assertEqual(self.w.portrait_layout.buttons[0],self.w.explorer_menu)
        first=self.member('ador','first_team');second=self.member('ador','second_team')
        with closing(self.service.database.connect()) as c,c:
            c.execute('UPDATE player_conditions SET registration_weeks=5,registration_week=0,complete_rest_weeks=0 WHERE person_id=?',(first,))
            c.execute('UPDATE player_conditions SET registration_weeks=4,registration_week=0,complete_rest_weeks=1 WHERE person_id=?',(second,))
        before=self.dump();self.w.show_squads();QTest.qWait(40);page=self.w.squad_page
        for person,expected in ((first,(5,2)),(second,(4,1))):
            row=next(i for i,m in enumerate(page.model.rows) if m.id==person)
            self.assertEqual(tuple(page.model.index(row,col).data() for col in range(15,17)),expected)
        self.assertEqual(page.model.columnCount(),17)
        page.table.sortByColumn(15,Qt.SortOrder.DescendingOrder)
        self.w.resize(900,1000);QTest.qWait(100)
        self.w.portrait_layout.navigate(0);QTest.qWait(30);self.assertIs(self.w.pages.currentWidget(),self.w.explorer_page)
        self.w.show_squads();QTest.qWait(30);self.assertEqual(self.w.portrait_layout.nav.currentIndex(),2)
        self.assertEqual(before,self.dump())
    def test_market_large_rows_separate_abilities_and_candidate_privacy(self):
        before=self.dump();self.w.show_market();QTest.qWait(80);page=self.w.market_page
        self.assertEqual(page.fa_table.columnCount(),23)
        self.assertGreaterEqual(page.fa_table.verticalHeader().defaultSectionSize(),64)
        self.assertGreaterEqual(page.fa_table.iconSize().height(),52)
        for col in range(14,23):self.assertFalse(page.fa_table.isColumnHidden(col))
        self.assertTrue(page.fa_table.isColumnHidden(7))
        for row in range(page.fa_table.rowCount()):
            p=page.by_id[page.fa_table.item(row,0).data(Qt.ItemDataRole.UserRole)]
            if not p['exact']:
                for i in range(8):self.assertEqual(page.fa_table.item(row,14+i).text(),f'{p["ranges"][i][0]}~{p["ranges"][i][1]}')
                self.assertEqual(page.fa_table.item(row,22).text(),'미공개')
        page.fa_table.sortItems(14,Qt.SortOrder.AscendingOrder)
        scores=[page.fa_table.item(i,14).data(Qt.ItemDataRole.UserRole+1) for i in range(page.fa_table.rowCount())]
        self.assertEqual(scores,sorted(scores))
        page.people_view.setCurrentIndex(1);self.assertFalse(page.fa_table.isColumnHidden(7));self.assertTrue(page.fa_table.isColumnHidden(14))
        page.people_view.setCurrentIndex(0);page.reload();QTest.qWait(50)
        root=Path(__file__).resolve().parents[1];self.w.grab().save(str(root/'.test-artifacts/ui_readability_market_windows.png'))
        self.w.resize(900,1000);QTest.qWait(120)
        page.people_view.setCurrentIndex(1);QTest.qWait(40);page.people_view.setCurrentIndex(0);QTest.qWait(40)
        pager=self.w.portrait_layout.tables[page.fa_table]
        self.assertTrue(pager.enabled);self.assertIn(7,pager.original_columns);self.assertNotIn(14,pager.original_columns)
        self.assertEqual(before,self.dump())

    def test_profile_condition_compact_and_details_collapsed(self):
        before=self.dump();person=self.member('ador','first_team');self.w.profiles.open(person)
        dialog=self.w.profiles.dialog;panel=dialog.panels[0];panel.tabs.setCurrentIndex(2);QTest.qWait(60)
        summary=panel.condition_label.text();self.assertLessEqual(len(summary.splitlines()),8)
        self.assertIn('필요 휴식 0주',summary);self.assertNotIn('기본 부상 확률',summary)
        self.assertTrue(panel.condition_detail.isHidden());QTest.mouseClick(panel.condition_more,Qt.MouseButton.LeftButton)
        self.assertFalse(panel.condition_detail.isHidden());self.assertIn('기본 부상 확률',panel.condition_detail.text());self.assertEqual(summary,panel.condition_label.text())
        QTest.mouseClick(panel.condition_more,Qt.MouseButton.LeftButton);self.assertTrue(panel.condition_detail.isHidden())
        dialog.close()
        candidate=next(p for p in self.service.profiles.search(role='candidate') if not p['exact']);self.w.profiles.open(candidate['id'])
        panel=self.w.profiles.dialog.panels[0];self.assertTrue(panel.condition_more.isHidden());self.assertEqual(panel.condition_detail.text(),'')
        self.w.profiles.dialog.close();self.assertEqual(before,self.dump())
