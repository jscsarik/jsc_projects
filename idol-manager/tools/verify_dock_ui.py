"""Native Windows dock interactions; all game writes stay in temporary test DBs."""
import os
os.environ['QT_QPA_PLATFORM']='windows'
import json,sys,unittest,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from tests.test_dock_ui import DockUITests

class NativeDock(DockUITests):
    def test_title_double_click_float_and_restore_with_profile(self):
        self.window.show_matches();QTest.qWait(150)
        page=self.window.match_page
        player=next(f for f in self.service.matches.fixtures() if f.player_participates)
        row=next(r for r in range(page.fixture_table.rowCount()) if page.fixture_table.item(r,0).data(Qt.ItemDataRole.UserRole)==player.id)
        page.fixture_table.setCurrentCell(row,0);QTest.qWait(50)
        panel=page.fixture_table.dock_panel;host=panel.workspace
        before=self.dump();self.assertTrue(panel.isVisible());self.assertFalse(host.isWindow())
        QTest.mouseDClick(panel,Qt.MouseButton.LeftButton,pos=QPoint(140,12));QTest.qWait(200)
        self.assertTrue(panel.isFloating());panel.resize(900,350)
        panel.move(self.window.pos()+QPoint(330,150));QTest.qWait(100)
        panel.grab().save(str(ROOT/'.test-artifacts/dock_windows_floating.png'))
        panel.setFloating(False);host.reset_layout();QTest.qWait(150)
        self.window.grab().save(str(ROOT/'.test-artifacts/dock_windows_workspace.png'))
        self.window.profiles.open(self.person);dialog=self.window.profiles.dialog
        dialog.resize(1300,850);profile=dialog.panels[0];profile.tabs.setCurrentIndex(3)
        profile.record_tabs.setCurrentIndex(0);QTest.qWait(100)
        first=profile.match_table.dock_panel;second=profile.skill_total_table.dock_panel
        host=first.workspace
        # Detach the two selected tabs from their old tab group before splitting.
        for dock in host.panels:
            if dock not in (first,second):dock.set_open(False)
        for dock in (first,second):
            host.removeDockWidget(dock);host.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea,dock)
            dock.set_open(True)
        host.splitDockWidget(first,second,Qt.Orientation.Horizontal);first.show();second.show();QTest.qWait(100)
        self.assertNotIn(second,host.tabifiedDockWidgets(first))
        self.assertTrue(first.isVisible());self.assertTrue(second.isVisible())
        self.assertNotEqual(first.geometry().x(),second.geometry().x())
        dialog.grab().save(str(ROOT/'.test-artifacts/dock_windows_profile.png'))
        self.assertEqual(before,self.dump());dialog.close()

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeDock))
    (ROOT/'.test-artifacts/dock_windows.json').write_text(json.dumps({'tests':result.testsRun,
        'success':result.wasSuccessful(),'platform':'windows','actual_save_modified':False},indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
