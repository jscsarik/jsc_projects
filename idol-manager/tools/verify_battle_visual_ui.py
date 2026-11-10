"""Native Windows playback on disposable SQLite saves; originals stay read-only."""
from pathlib import Path
import os,sys,json,unittest,shutil,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_battle_view import VisualReplayTests,BattleViewTests


class NativeVisual(VisualReplayTests):
    def test_native_watch_pause_skip_and_results(self):
        # Copy pictures only into generated test fixtures. Never rename sources.
        sources=list((ROOT/'assets/idols').glob('*.png'))[:16]
        if sources:
            for i,target in enumerate((self.base/'assets/idols').glob('*.png')):
                shutil.copyfile(sources[i%len(sources)],target)
        self.open();self.window.resize(1700,1050)
        result,_=self.play_player(skip=False);before=self.dump()
        self.wait(lambda:not self.page.battle_photos.pending)
        QTest.qWait(1200)
        self.window.grab().save(str(ROOT/'.test-artifacts/visual_windows_battle.png'))
        QTest.mouseClick(self.page.pause_button,Qt.MouseButton.LeftButton)
        tick=self.page.frame_index;QTest.qWait(650);self.assertEqual(self.page.frame_index,tick)
        self.window.grab().save(str(ROOT/'.test-artifacts/visual_windows_paused.png'))
        QTest.mouseClick(self.page.pause_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.frame_index>tick)
        QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        self.assertEqual(before,self.dump());self.assertEqual(result,self.service.matches.result(result.match_id))
        self.window.grab().save(str(ROOT/'.test-artifacts/visual_windows_result.png'))


class NativeCards(BattleViewTests):
    def test_sizes_screenshots(self):
        for count in (1,2,3,5):
            self.configure(count);self.view.resize(1100,580);QTest.qWait(100)
            self.view.grab().save(str(ROOT/f'.test-artifacts/visual_windows_{count}_players.png'))


if __name__=='__main__':
    suite=unittest.TestSuite([NativeVisual('test_native_watch_pause_skip_and_results'),
        NativeVisual('test_pause_resume_tabs_log_score_and_repeated_skip_do_not_change_database'),
        NativeCards('test_sizes_screenshots'),NativeCards('test_success_failure_leader_log_five_lines_and_pause_animation')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'platform':sys.platform,'qt_platform':NativeVisual.app.platformName(),'tests':result.testsRun,
        'success':result.wasSuccessful(),'actual_save_modified':False}
    (ROOT/'.test-artifacts/visual_windows_ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
