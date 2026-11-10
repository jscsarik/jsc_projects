"""Windows finance UI, temporary game database only."""
import os
os.environ['QT_QPA_PLATFORM']='windows'
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from tests import test_finance_ui as fixture
class NativeFinance(fixture.FinanceUITests):
    def test_windows_finance_pages(self):
        self.window.resize(1660,1000);QTest.qWait(150)
        before=self.dump();self.window.grab().save(str(ROOT/'.test-artifacts/finance_windows_dashboard.png'))
        self.page.tabs.setCurrentIndex(3);self.page.fit_screen();QTest.qWait(150)
        self.window.grab().save(str(ROOT/'.test-artifacts/finance_windows_payroll.png'))
        table=self.page.payroll_table
        self.assertLessEqual(sum(table.columnWidth(c) for c in range(table.columnCount())),table.viewport().width())
        last=table.visualItemRect(table.item(table.rowCount()-1,0))
        self.assertLessEqual(last.bottom(),table.viewport().height())
        self.page.payroll_table.sortByColumn(1,Qt.SortOrder.DescendingOrder);self.page.photos();self.page.reload()
        self.assertEqual(before,self.dump())
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeFinance))
    (ROOT/'.test-artifacts/finance_windows.json').write_text(json.dumps({'tests':result.testsRun,'success':result.wasSuccessful(),'platform':'windows','actual_save_modified':False},indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
