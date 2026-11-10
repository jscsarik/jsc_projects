import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QPushButton
from idol_manager.ui.main_window import MainWindow
from tests import test_market as fixture

class MarketUITests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    dump=fixture.MarketTests.dump
    rows=fixture.MarketTests.rows
    day=fixture.MarketTests.day
    finite=fixture.MarketTests.finite
    member=fixture.MarketTests.member
    vacancy=fixture.MarketTests.vacancy
    def setUp(self):
        fixture.MarketTests.setUp(self);self.vacancy();self.day(203)
        from PySide6.QtGui import QFont
        self.app.setFont(QFont("Malgun Gothic",10))
        self.warnings=[]
        for target,value in (('question',QMessageBox.StandardButton.Yes),('information',None),('warning',None)):
            p=patch('idol_manager.ui.market_page.QMessageBox.'+target,side_effect=(lambda *a:self.warnings.append(a[-1])) if target=='warning' else None,return_value=value)
            p.start();self.addCleanup(p.stop)
        self.window=MainWindow(self.service);self.addCleanup(self.window.close);self.window.resize(1700,1000);self.window.show();self.app.processEvents()
        if self.app.platformName()=='windows':
            self.assertTrue(QTest.qWaitForWindowExposed(self.window,5000));self.window.raise_();self.window.activateWindow();self.assertTrue(QTest.qWaitForWindowActive(self.window,5000))
        QTest.mouseClick(self.window.market_menu,Qt.MouseButton.LeftButton);QTest.qWait(80);self.page=self.window.market_page
    def test_market_tabs_read_only_docks_and_no_hidden_candidate_exact_values(self):
        self.assertIs(self.window.pages.currentWidget(),self.page);self.assertEqual(self.page.tabs.count(),7)
        before=self.dump()
        for index in range(7):self.page.tabs.setCurrentIndex(index);self.app.processEvents()
        self.page.reload();self.assertEqual(before,self.dump())
        for table in (self.page.fa_table,self.page.negotiation_table,self.page.trade_table,self.page.renew_table,self.page.release_table,self.page.trainee_table,self.page.history_table):self.assertTrue(hasattr(table,'dock_panel'))
        self.assertFalse(self.warnings)
    def test_native_bid_button_uses_selected_id_persists_and_does_not_charge_cash(self):
        self.page.tabs.setCurrentIndex(0);self.page.fa_table.setCurrentCell(0,0)
        person=self.page.fa_table.item(0,0).data(Qt.ItemDataRole.UserRole)
        before=self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")
        self.page.bid_amount.setValue(3300)
        button=next(b for b in self.page.findChildren(QPushButton) if b.text()=='공개 입찰 확정')
        QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertFalse(self.warnings,self.warnings)
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'"),before)
        self.assertEqual(self.rows('SELECT person_id FROM market_auctions'),[(person,)])
        self.window.close();other=MainWindow(self.service);self.addCleanup(other.close);other.show();other.show_market()
        self.assertEqual(len(self.service.market.auctions()),1)

    def test_counterproposal_displays_actual_cash_and_players_before_acceptance(self):
        own=self.member('ador');other=self.member('jyp')
        terms=dict(pro_a=own,pro_b=other,cash=0,trainees_a=[],trainees_b=[])
        identity=self.service.market.propose_trade('ador','jyp',terms,request_id='ui-counter')
        terms['cash']=1230000
        self.service.market.trade_reply(identity,'jyp','counter',terms=terms,expected_version=1)
        self.page.reload();self.page.tabs.setCurrentIndex(2);self.page.trade_table.setCurrentCell(0,0);self.app.processEvents()
        self.assertEqual(self.page.trade_cash.value(),123)
        self.assertEqual(self.page.pro_a.currentData(),own);self.assertEqual(self.page.pro_b.currentData(),other)
        self.assertIn('123',self.page.trade_table.item(0,7).text())
        self.page.reply_trade('accept');self.assertFalse(self.warnings,self.warnings)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(identity,)),[('accepted_pending',)])

    def test_market_rows_and_trade_portraits(self):
        from PySide6.QtCore import QSize
        from idol_manager.ui.match_page import PROFILE_ROLE
        before=self.dump()
        for index,table in ((0,self.page.fa_table),(3,self.page.renew_table),(4,self.page.release_table),(5,self.page.trainee_table)):
            self.page.tabs.setCurrentIndex(index);QTest.qWait(100)
            self.assertTrue(table.property('balancedCompanyColumns'))
            self.assertTrue(all(table.rowHeight(r)>=64 for r in range(table.rowCount())))
            visible=[c for c in range(table.columnCount()) if not table.isColumnHidden(c)]
            self.assertLessEqual(sum(table.columnWidth(c) for c in visible),table.viewport().width())
        self.page.tabs.setCurrentIndex(2);QTest.qWait(100)
        for combo,photo,label in ((self.page.pro_a,self.page.photo_a,self.page.trade_summary_a),(self.page.pro_b,self.page.photo_b,self.page.trade_summary_b)):
            combo.setCurrentIndex(min(1,combo.count()-1));QTest.qWait(50)
            person=self.page.by_id[combo.currentData()]
            self.assertIsNotNone(photo.original)
            self.assertFalse(photo.pixmap().isNull())
            self.assertIn(person['name'],label.text())
            self.assertIn('리더십',label.text())
            self.assertTrue(photo.isVisible())
            self.assertGreaterEqual(photo.height(),120)
        self.assertEqual(before,self.dump())
        folder=Path('reports/market_0335');folder.mkdir(parents=True,exist_ok=True)
        self.window.grab().save(str(folder/'trade.png'))
        self.page.tabs.setCurrentIndex(3);QTest.qWait(100)
        self.window.grab().save(str(folder/'renew.png'))
