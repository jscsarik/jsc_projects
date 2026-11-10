"""Authorized follow-up fix: release debt cannot strand the annual draft."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import os,sqlite3,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from tests import test_market as fixture
from idol_manager.market_service import process_market,MarketError

class ReleasePrepaymentTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    setUp=fixture.MarketTests.setUp
    rows=fixture.MarketTests.rows;dump=fixture.MarketTests.dump;day=fixture.MarketTests.day
    member=fixture.MarketTests.member;finite=fixture.MarketTests.finite
    def plan(self):
        person=self.member();self.finite(person,duration=2)
        return self.market.release('ador',person,'installments',request_id='prepay-plan')
    def test_partial_installments_payoff_idempotent_and_future_charge_stops(self):
        plan=self.plan();self.day(7)
        with self.market.write() as c:process_market(c,7,run_ai=False)
        installments=self.rows('SELECT * FROM market_installments');cash=self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0]
        before={t:self.rows('SELECT * FROM '+t) for t in ('finance_contracts','draft_picks','abilities','people')}
        remaining=self.market.release_balances('ador')[0]['remaining']
        receipt=self.market.prepay_release('ador',plan['id'],expected_remaining=remaining)
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'"),[(cash-remaining,)])
        self.assertEqual(receipt,self.market.prepay_release('ador',plan['id'],expected_remaining=remaining))
        self.assertEqual(self.market.release_balances('ador')[0]['remaining'],0)
        self.day(14)
        with self.market.write() as c:process_market(c,14,run_ai=False)
        self.assertEqual(installments,self.rows('SELECT * FROM market_installments'))
        self.assertEqual(before,{t:self.rows('SELECT * FROM '+t) for t in before})
        self.assertEqual(self.rows('SELECT original_krw,outstanding_krw FROM finance_debts'),[(plan['total'],0)])
    def test_overdue_installment_is_included_and_history_is_preserved(self):
        plan=self.plan()
        with self.market.write() as c:c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'")
        self.day(7)
        with self.market.write() as c:process_market(c,7,run_ai=False)
        self.assertEqual(self.market.release_balances('ador')[0]['remaining'],plan['total'])
        history=self.rows('SELECT * FROM market_installments')
        with self.market.write() as c:c.execute("UPDATE agencies SET funds_krw=? WHERE id='ador'",(plan['total'],))
        self.market.prepay_release('ador',plan['id'])
        self.assertEqual(history,self.rows('SELECT * FROM market_installments'))
        self.assertEqual(self.rows('SELECT SUM(outstanding_krw) FROM finance_debts'),[(0,)])
    def test_insufficient_funds_stale_amount_and_wrong_owner_never_write(self):
        plan=self.plan();before=self.dump()
        with self.assertRaises(MarketError):self.market.prepay_release('jyp',plan['id'])
        with self.assertRaises(MarketError):self.market.prepay_release('ador',plan['id'],expected_remaining=1)
        self.assertEqual(before,self.dump())
        with self.market.write() as c:c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'")
        before=self.dump()
        with self.assertRaisesRegex(MarketError,'부족'):self.market.prepay_release('ador',plan['id'])
        self.assertEqual(before,self.dump())
    def test_failure_rolls_back_and_concurrent_requests_charge_once(self):
        plan=self.plan()
        with self.market.write() as c:c.execute("CREATE TRIGGER qa_payoff_failure BEFORE INSERT ON finance_ledger WHEN NEW.kind='release_prepayment' BEGIN SELECT RAISE(ABORT,'injected');END")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):self.market.prepay_release('ador',plan['id'])
        self.assertEqual(before,self.dump())
        with self.market.write() as c:c.execute('DROP TRIGGER qa_payoff_failure')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.market.prepay_release('ador',plan['id']),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE kind='release_prepayment'"),[(1,)])
    def test_ui_cancel_confirm_and_reopen(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMessageBox
        from idol_manager.ui.main_window import MainWindow
        from idol_manager.market_service import MarketService
        from idol_manager.database import Database
        plan=self.plan();w=MainWindow(self.service);self.addCleanup(w.close);w.resize(900,1560);w.show();w.show_finance();QTest.qWait(100)
        page=w.finance_page;page.agency.setCurrentIndex(page.agency.findData('ador'));self.assertTrue(page.prepay_button.isEnabled())
        before=self.dump()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):QTest.mouseClick(page.prepay_button,Qt.MouseButton.LeftButton)
        self.assertEqual(before,self.dump())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):QTest.mouseClick(page.prepay_button,Qt.MouseButton.LeftButton)
        self.assertFalse(page.prepay_button.isEnabled());w.close()
        self.assertEqual(MarketService(Database(self.path)).release_balances('ador')[0]['remaining'],0)

if __name__=='__main__':unittest.main()
