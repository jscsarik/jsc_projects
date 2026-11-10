"""Windows design/column interaction check using a disposable game only."""
import os
os.environ['QT_QPA_PLATFORM'] = 'windows'
import json
from pathlib import Path
import shutil
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_match_ui import MatchUITests
from tests.test_ui_layout import TableLayoutTests


class NativeRefresh(MatchUITests):
    def test_resize_regions_and_restart(self):
        from PySide6.QtCore import QPoint,QPointF,QEvent
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        self.open();self.window.resize(1500,950);self.window.show_matches()
        self.assertTrue(QTest.qWaitForWindowExposed(self.window,5000))
        self.window.raise_();self.window.activateWindow()
        self.assertTrue(QTest.qWaitForWindowActive(self.window,5000));QTest.qWait(100)
        self.select(self.player_fixture().id)
        host=self.page.fixture_table.dock_panel.workspace
        upper,lower=host.panels;before=self.dump();old=upper.height()
        start=QPoint(host.width()//2,(upper.geometry().bottom()+lower.geometry().top())//2)
        QTest.mousePress(host,Qt.MouseButton.LeftButton,pos=start)
        # QMainWindow checks held buttons; QTest.mouseMove alone reports none.
        for delta in range(10,131,10):
            point=start+QPoint(0,delta)
            QApplication.sendEvent(host,QMouseEvent(QEvent.Type.MouseMove,QPointF(point),
                QPointF(host.mapToGlobal(point)),Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
            QTest.qWait(10)
        QTest.mouseRelease(host,Qt.MouseButton.LeftButton,pos=start+QPoint(0,130));QTest.qWait(150)
        self.assertGreater(upper.height(),old+60)
        height=upper.height();self.page.reload();QTest.qWait(60)
        self.assertAlmostEqual(upper.height(),height,delta=5)
        self.assertGreater(self.page.fixture_table.height(),180)
        self.window.grab().save(str(ROOT/'.test-artifacts/ui_regions_resized.png'))
        self.assertEqual(before,self.dump());self.window.close()
        self.open();self.window.resize(1500,950);self.window.show_matches();QTest.qWait(150)
        upper=self.page.fixture_table.dock_panel
        self.assertAlmostEqual(upper.height(),height,delta=8)
        self.assertEqual(before,self.dump())

    def test_management_and_saved_battle(self):
        sources = [p for p in (ROOT / 'assets/idols').iterdir() if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')]
        if sources:
            for i, destination in enumerate((self.base / 'assets/idols').glob('*.png')):
                shutil.copyfile(sources[i % len(sources)], destination)
        self.open(); self.window.resize(1660, 1000)
        self.assertTrue(QTest.qWaitForWindowExposed(self.window, 5000))
        self.window.raise_(); self.window.activateWindow()
        self.assertTrue(QTest.qWaitForWindowActive(self.window, 5000))
        self.window.show_squads(); QTest.qWait(400)
        table = self.window.squad_page.table
        original = self.dump()
        table.horizontalHeader().resizeSection(2, 235)
        self.window.show_schedule(); self.window.show_squads()
        self.assertEqual(table.columnWidth(2), 235); self.assertEqual(original, self.dump())
        self.window.grab().save(str(ROOT / '.test-artifacts/ui_refresh_management.png'))
        self.window.show_matches(); self.page = self.window.match_page
        result, _ = self.play_player(skip=False); self.page.timer.stop()
        frozen = self.dump()
        for _ in range(15):
            self.page.advance_frame()
        self.wait(lambda:not self.page.battle_photos.pending)
        QTest.qWait(150)
        self.window.grab().save(str(ROOT / '.test-artifacts/ui_refresh_battle.png'))
        self.page.skip(); self.assertEqual(frozen, self.dump())
        self.assertEqual(self.service.matches.result(result.match_id), result)


if __name__ == '__main__':
    suite = unittest.TestSuite([NativeRefresh('test_management_and_saved_battle'),NativeRefresh('test_resize_regions_and_restart')])
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TableLayoutTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    (ROOT / '.test-artifacts/ui_refresh_windows.json').write_text(json.dumps({
        'tests': result.testsRun, 'success': result.wasSuccessful(),
        'platform': 'windows', 'actual_save_modified': False}, indent=2), encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
