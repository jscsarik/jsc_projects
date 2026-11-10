import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from contextlib import closing
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.ui.main_window import MainWindow
from tests import test_finance as fixture

class FinanceUITests(unittest.TestCase):
    setUpClass=classmethod(fixture.FinanceTests.setUpClass.__func__)
    dump=fixture.FinanceTests.dump
    rows=fixture.FinanceTests.rows
    week=fixture.FinanceTests.week
    def setUp(self):
        fixture.FinanceTests.setUp(self)
        for w in range(1,5):self.week(w)
        self.window=MainWindow(self.service);self.addCleanup(self.window.close);self.window.show();self.app.processEvents()
        if self.app.platformName()=='windows':
            self.assertTrue(QTest.qWaitForWindowExposed(self.window,5000));self.window.raise_();self.window.activateWindow();self.assertTrue(QTest.qWaitForWindowActive(self.window,5000))
        QTest.mouseClick(self.window.finance_menu,Qt.MouseButton.LeftButton);QTest.qWait(80);self.page=self.window.finance_page
    def test_native_dashboard_all_agencies_cash_ledger_payroll_and_docks_read_only(self):
        self.assertIs(self.window.pages.currentWidget(),self.page);self.assertEqual(self.page.agency.count(),10)
        self.assertEqual(self.page.agency.currentData(),'ador');self.assertGreater(self.page.ledger_table.rowCount(),0)
        self.assertEqual(self.page.payroll_table.rowCount(),16);self.assertEqual(self.page.forecast_table.rowCount(),4)
        for table in (self.page.ledger_table,self.page.payroll_table,self.page.contract_table,self.page.debt_table,self.page.sale_table,self.page.forecast_table):self.assertTrue(hasattr(table,'dock_panel'))
        from idol_manager.ui.match_page import PROFILE_ROLE
        self.page.payroll_table.sortByColumn(1,Qt.SortOrder.DescendingOrder);self.page.photos()
        self.assertEqual(self.page.payroll_table.item(0,0).data(Qt.ItemDataRole.UserRole),self.page.payroll_table.item(0,1).data(PROFILE_ROLE))
        before=self.dump()
        for i in range(10):self.page.agency.setCurrentIndex(i);self.page.tabs.setCurrentIndex(i%5);self.app.processEvents()
        self.page.reload();self.assertEqual(before,self.dump())
        self.window.close();window=MainWindow(self.service);self.addCleanup(window.close);window.show();window.show_finance();QTest.qWait(50)
        self.assertEqual(before,self.dump());self.assertEqual(window.finance_page.agency.count(),10)
    def test_fit_tabs_and_all_columns_keep_game_unchanged(self):
        before=self.dump();self.window.resize(1400,940)
        self.page.tabs.setCurrentWidget(self.page.payroll_table.dock_panel.workspace)
        QTest.qWait(80);self.page._fitted_tables.clear();self.page.fit_visible_tables()
        table=self.page.payroll_table
        self.assertTrue(table.isVisible())
        self.assertLessEqual(sum(table.columnWidth(c) for c in range(table.columnCount())),table.viewport().width())
        self.assertEqual(table.verticalHeader().defaultSectionSize(),30)
        table.horizontalHeader().resizeSection(1,160)
        self.assertEqual(table.columnWidth(1),160)
        self.assertEqual(before,self.dump())

    def test_profile_contract_and_payroll_are_saved_reads_only(self):
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' LIMIT 1")[0][0]
        before=self.dump();self.window.profiles.open(person);panel=self.window.profiles.dialog.panels[0];panel.tabs.setCurrentIndex(5)
        self.assertIn('3,000만원',panel.contract_label.text());self.assertIn('계약',panel.contract_label.text())
        self.window.profiles.dialog.close();self.assertEqual(before,self.dump())
