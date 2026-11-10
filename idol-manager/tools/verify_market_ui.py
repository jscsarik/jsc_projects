"""Native Windows market UI against a disposable save only."""
import os
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from tests import test_market_ui as fixture
class NativeMarket(fixture.MarketUITests):
    def test_native_contract_offer_confirmation_and_restart(self):
        target=next(p for p in self.service.market.public_people(available=True) if p['exact'] and p['age']>=17)
        self.page.tabs.setCurrentIndex(1);self.page.person.setCurrentIndex(self.page.person.findData(target['id']))
        self.page.purpose.setCurrentIndex(self.page.purpose.findData('fa'))
        start=next(b for b in self.page.findChildren(QPushButton) if b.text()=='협상 열기')
        QTest.mouseClick(start,Qt.MouseButton.LeftButton);QTest.qWait(50)
        self.page.offer_amount.setValue(6600);self.page.offer_duration.setValue(2)
        self.assertTrue(self.page.offer_button.isEnabled())
        QTest.mouseClick(self.page.offer_button,Qt.MouseButton.LeftButton);QTest.qWait(50)
        self.assertFalse(self.warnings,self.warnings)
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(target['id'],)),[('ador',)])
        before=self.dump();self.page.reload();self.assertEqual(before,self.dump())
        self.window.grab().save(str(ROOT/'.test-artifacts/market_windows_contract.png'))

    def test_native_market_photos_trade_tabs_and_negotiation_view(self):
        self.window.resize(1700,1000);self.page.tabs.setCurrentIndex(0);QTest.qWait(100)
        self.window.grab().save(str(ROOT/'.test-artifacts/market_windows_fa.png'))
        self.page.tabs.setCurrentIndex(2);self.page.other.setCurrentIndex(self.page.other.findData('jyp'));QTest.qWait(100)
        self.window.grab().save(str(ROOT/'.test-artifacts/market_windows_trade.png'))
        before=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        button=next(b for b in self.page.findChildren(QPushButton) if b.text()=='트레이드 제안')
        QTest.mouseClick(button,Qt.MouseButton.LeftButton);QTest.qWait(80)
        self.assertFalse(self.warnings,self.warnings);self.assertEqual(len(self.service.market.trades()),1)
        self.assertEqual(before,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertTrue(self.page.isVisible())
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeMarket))
    (ROOT/'.test-artifacts/market_windows.json').write_text(json.dumps({'tests':result.testsRun,'success':result.wasSuccessful(),'platform':'windows','actual_save_modified':False},indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
