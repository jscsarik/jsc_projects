"""Native Windows public settlement history, using disposable saves only."""
from pathlib import Path
import os,sys,json,unittest,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='windows'
from tests.test_development_ui_migration import DevelopmentUITests
from PySide6.QtTest import QTest


class NativeDevelopment(DevelopmentUITests):
    def test_native_history_and_records_unchanged(self):
        sources=list((ROOT/'assets/idols').glob('*.png'))[:16]
        if sources:
            for i,target in enumerate((Path(self.temp.name)/'missing').glob('*.png')):shutil.copyfile(sources[i%len(sources)],target)
        self.page.changed.setChecked(False);self.page.reload();QTest.qWait(250)
        before=self.dump();self.window.grab().save(str(ROOT/'.test-artifacts/growth_windows_history.png'))
        self.assertTrue(self.page.rows);self.assertEqual(before,self.dump())
        if self.page.period.count()>1:self.page.period.setCurrentIndex(1)
        self.assertEqual(before,self.dump())


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(NativeDevelopment(name) for name in (
        'test_native_history_and_records_unchanged','test_history_photo_deltas_filter_reopen_no_settlement_side_effects','test_ui_projection_denies_pa_and_private_trials')))
    report={'platform':sys.platform,'qt_platform':NativeDevelopment.app.platformName(),'tests':result.testsRun,'success':result.wasSuccessful(),'actual_source_modified':False}
    (ROOT/'.test-artifacts/growth_windows_ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
