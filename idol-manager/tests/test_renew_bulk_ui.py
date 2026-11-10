import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from tests import test_season32 as fixture
from idol_manager.ui.main_window import MainWindow

class RenewBulkUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    day=fixture.Season32Tests.day;rows=fixture.Season32Tests.rows

    def open(self,day=203):
        self.day(day);self.window=MainWindow(self.service);self.addCleanup(self.window.close)
        self.window.resize(1600,950);self.window.show();self.window.show_market()
        self.page=self.window.market_page;self.page.tabs.setCurrentIndex(3);QTest.qWait(90)
        return self.page

    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())

    def test_check_all_sort_reload_cancel_and_bulk_open_without_contracts(self):
        page=self.open();before=self.dump()
        QTest.mouseClick(page.renew_all_button,Qt.MouseButton.LeftButton)
        identities=set(page.checked_renew_ids());self.assertEqual(len(identities),16)
        page.renew_table.sortItems(1,Qt.SortOrder.DescendingOrder);page.reload()
        self.assertEqual(set(page.checked_renew_ids()),identities)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):page.renew_button.click()
        self.assertEqual(before,self.dump())
        contracts=self.rows('SELECT * FROM finance_contracts ORDER BY id');funds=self.rows('SELECT id,funds_krw FROM agencies ORDER BY id')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):
            page.renew_button.click()
        self.assertEqual(self.rows("SELECT COUNT(*) FROM market_negotiations WHERE agency_id='ador' AND purpose='renew'"),[(16,)])
        self.assertEqual(contracts,self.rows('SELECT * FROM finance_contracts ORDER BY id'));self.assertEqual(funds,self.rows('SELECT id,funds_krw FROM agencies ORDER BY id'))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):page.start_renew_selected()
        self.assertEqual(self.rows("SELECT COUNT(*) FROM market_negotiations WHERE agency_id='ador' AND purpose='renew'"),[(16,)])
        self.assertEqual(page.tabs.currentIndex(),1)
        page.tabs.setCurrentIndex(3);QTest.qWait(80)
        from pathlib import Path
        self.window.grab().save(str(Path(__file__).resolve().parents[1]/'reports/renew_bulk_0371.png'))
        page.renew_clear_button.click();self.assertEqual(page.checked_renew_ids(),())

    def test_single_checkbox_and_regular_season_stays_blocked(self):
        page=self.open(day=7)
        item=page.renew_table.item(0,0);identity=item.data(Qt.ItemDataRole.UserRole)
        item.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(page.checked_renew_ids(),(identity,));self.assertIn('1명',page.renew_count.text())
        self.assertFalse(page.renew_button.isEnabled());self.assertIn('비시즌',page.renew_button.toolTip())

    def test_one_failed_player_is_reported_without_hiding_other_success(self):
        page=self.open();ids=[]
        for row in range(2):
            item=page.renew_table.item(row,0);ids.append(item.data(Qt.ItemDataRole.UserRole));item.setCheckState(Qt.CheckState.Checked)
        original=self.service.market.start_negotiation
        def start(agency,person,purpose):
            if person==ids[0]:raise ValueError('계약 조건 확인 필요')
            return original(agency,person,purpose)
        with patch.object(self.service.market,'start_negotiation',side_effect=start),patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'warning') as warning:
            page.renew_button.click()
        self.assertEqual(self.rows("SELECT COUNT(*) FROM market_negotiations WHERE agency_id='ador' AND purpose='renew'"),[(1,)])
        self.assertIn('계약 조건 확인 필요',warning.call_args.args[2])
