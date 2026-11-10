"""Native Windows interaction; only disposable game saves are opened."""
from pathlib import Path
import os,sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='windows'
from tests.test_draft_estimates_ui import EstimateUITests
from PySide6.QtTest import QTest


class NativeEstimates(EstimateUITests):
    def test_native_flow(self):
        self.window.resize(1600,1000)
        candidate=self.first_turn();QTest.qWait(300)
        self.assertIn('~',self.page.detail_table.item(0,1).text())
        self.window.grab().save(str(ROOT/'.test-artifacts/estimates_windows_before.png'))
        self.confirm();QTest.qWait(100)
        self.assertEqual(self.page.detail_table.horizontalHeaderItem(1).text(),'실제 현재 값')
        self.window.grab().save(str(ROOT/'.test-artifacts/estimates_windows_after.png'))
        self.assertEqual(self.service.draft.picks()[0].person_id,candidate.id)


if __name__=='__main__':
    suite=unittest.TestSuite(NativeEstimates(name) for name in (
        'test_native_flow','test_public_ranges_numeric_sort_search_age_and_status_filters',
        'test_pick_reveals_only_owned_ca_history_and_restart_preserve_ranges'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'platform':sys.platform,'qt_platform':NativeEstimates.app.platformName(),
        'tests':result.testsRun,'success':result.wasSuccessful(),'actual_save_modified':False}
    (ROOT/'.test-artifacts/estimates_windows_ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
