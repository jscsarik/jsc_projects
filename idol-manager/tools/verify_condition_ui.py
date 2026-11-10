"""Native Windows QtTest interaction; copied/generated saves, no real-save writes."""
from pathlib import Path
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='windows'
from tests.test_match_ui import MatchUITests


class NativeConditionUI(MatchUITests):
    def test_condition_flow(self):
        self.test_injury_disabled_fatigue_preview_matches_saved_probability_and_skip()
        self.select(self.player_fixture().id)
        self.window.resize(1600,950)
        self.app.processEvents()
        self.window.grab().save(str(ROOT/'.test-artifacts/fatigue_windows_ui.png'))


if __name__=='__main__':
    suite=unittest.TestSuite([NativeConditionUI('test_condition_flow')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'platform':sys.platform,'qt_platform':NativeConditionUI.app.platformName(),
            'tests':result.testsRun,'success':result.wasSuccessful(),'actual_save_modified':False,
            'screenshot':str(ROOT/'.test-artifacts/fatigue_windows_ui.png')}
    (ROOT/'.test-artifacts/fatigue_windows_ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
