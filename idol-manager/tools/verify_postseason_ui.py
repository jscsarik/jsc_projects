"""Native Windows finals UI with only disposable SQLite saves."""
from pathlib import Path
from contextlib import closing
import os,sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_finals_ui import FinalsUITests


class NativeFinals(FinalsUITests):
    def test_native_postseason_scene(self):
        photos=list((ROOT/'assets/idols').glob('*.png'))[:16]
        with closing(self.db.connect()) as c,c:
            ids=[r[0] for r in c.execute('SELECT id FROM people ORDER BY id')]
            if photos:c.executemany('UPDATE people SET photo_path=? WHERE id=?',[(photos[i%len(photos)].relative_to(ROOT).as_posix(),p) for i,p in enumerate(ids)])
        self.open(root=ROOT)
        self.choose()
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton);self.wait(lambda:self.page.replaying)
        self.wait(lambda:not self.page.battle_photos.pending);QTest.qWait(600)
        self.window.grab().save(str(ROOT/'.test-artifacts/postseason_windows_battle.png'))
        QTest.mouseClick(self.page.pause_button,Qt.MouseButton.LeftButton);before=self.table('final_contests')
        QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton);self.assertEqual(before,self.table('final_contests'))
        self.assertIn('시리즈 +1승',self.page.result_summary.text())
        self.window.grab().save(str(ROOT/'.test-artifacts/postseason_windows_result.png'))


if __name__=='__main__':
    suite=unittest.TestSuite(NativeFinals(name) for name in ('test_native_postseason_scene',
        'test_postseason_reuses_photos_vs_pause_skip_result_bgm_and_restart','test_three_team_tie_ui_full_rank_result_and_no_regular_points'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'platform':sys.platform,'qt_platform':NativeFinals.app.platformName(),'tests':result.testsRun,'success':result.wasSuccessful(),'actual_save_modified':False}
    (ROOT/'.test-artifacts/postseason_windows_ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
