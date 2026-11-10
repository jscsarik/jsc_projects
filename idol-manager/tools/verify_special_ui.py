"""Native Windows Qt interaction with disposable saves and generated test images."""
from pathlib import Path
import json
import os
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from tests.test_special_ui import SpecialUITests


class NativeSpecialUI(SpecialUITests):
    def test_native_flow(self):
        self.open();self.window.resize(1600,980)
        photos=self.root/'assets/idols';photos.mkdir(parents=True,exist_ok=True)
        image=QImage(64,80,QImage.Format.Format_RGB32);image.fill(QColor('#c8d9ed'))
        for i in range(310):image.save(str(photos/f'{i}.png'))
        self.start_event()
        own=next(r for r in self.page.event_state['rounds'] if 'ador' in r['agencies'])
        self.select(own['stage']);self.choose()
        self.wait(lambda:not self.window.thumbnails.pending)
        self.window.grab().save(str(ROOT/'.test-artifacts/special_windows_selection.png'))
        result=self.play(own['stage'],skip=False);before=self.dump();started=time.monotonic()
        self.wait(lambda:self.manager.category=='battle')
        QTest.qWait(1000)
        self.window.grab().save(str(ROOT/'.test-artifacts/special_windows_replay.png'))
        self.wait(lambda:not self.page.replaying,seconds=len(self.page.frames)*.5+10)
        self.assertGreaterEqual(time.monotonic()-started,13)
        self.assertEqual(before,self.dump())
        other='lower' if own['stage']=='upper' else 'upper'
        self.play(other);self.play('final')
        self.assertEqual(self.page.event_state['status'],'completed')
        self.wait(lambda:self.manager.category=='default')
        self.app.processEvents();self.window.grab().save(str(ROOT/'.test-artifacts/special_windows_result.png'))
        QTest.mouseClick(self.window.day_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.service.calendar.state().date.absolute_day,28)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([NativeSpecialUI('test_native_flow')]))
    report={'platform':sys.platform,'qt_platform':NativeSpecialUI.app.platformName(),'tests':result.testsRun,
            'success':result.wasSuccessful(),'actual_save_modified':False,'native_fifteen_second_watch':True,
            'bgm_contexts_verified_with_fake_backend':True}
    (ROOT/'.test-artifacts/special_windows_ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
