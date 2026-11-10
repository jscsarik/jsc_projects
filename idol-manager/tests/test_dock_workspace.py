import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile,unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QTabWidget,QTableWidget,QTableWidgetItem
from idol_manager.ui.dock_workspace import DockWorkspace,DockLayoutManager


class DockWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'도킹 설정.ini'

    def build(self,key='main',*,parent=None,scope=None):
        manager=DockLayoutManager(self.path);self.addCleanup(manager.shutdown)
        workspace=DockWorkspace(manager,key,parent,scope=scope)
        one=QTableWidget(100,2);two=QTableWidget(20,2)
        for row in range(100):one.setItem(row,0,QTableWidgetItem(str(row)))
        a=workspace.add_panel('선수 명단',one,key+'/one');b=workspace.add_panel('경기 기록',two,key+'/two',beside=a)
        workspace.resizeDocks([a,b],[350,250],Qt.Orientation.Vertical);workspace.finish();workspace.resize(900,650)
        self.addCleanup(workspace.close)
        if parent is None:workspace.show();QTest.qWait(80)
        return manager,workspace,a,b

    def test_float_resize_dock_split_tabify_and_original_model_selection(self):
        manager,w,a,b=self.build();table=a.widget();model=table.model();table.setCurrentCell(50,0)
        a.setFloating(True);a.resize(600,400);QTest.qWait(80)
        self.assertTrue(a.isFloating());self.assertTrue(a.isVisible());self.assertGreater(a.width(),500)
        self.assertIs(a.widget(),table);self.assertIs(table.model(),model);self.assertEqual(table.currentRow(),50)
        a.setFloating(False);w.tabifyDockWidget(a,b);QTest.qWait(30)
        self.assertIn(b,w.tabifiedDockWidgets(a))
        w.splitDockWidget(a,b,Qt.Orientation.Horizontal);QTest.qWait(30)
        self.assertNotIn(b,w.tabifiedDockWidgets(a));self.assertNotEqual(a.geometry().x(),b.geometry().x())

    def test_layout_float_size_closed_panel_persist_and_reset(self):
        manager,w,a,b=self.build();a.setFloating(True);a.resize(530,360);a.move(60,70);b.close();QTest.qWait(50)
        manager.shutdown();w.close()
        manager2,other,c,d=self.build()
        self.assertTrue(c.isFloating());self.assertAlmostEqual(c.width(),530,delta=20);self.assertAlmostEqual(c.height(),360,delta=20)
        self.assertFalse(d.user_open);self.assertFalse(d.isVisible())
        other.show_all();self.assertTrue(d.isVisible());other.reset_layout();QTest.qWait(50)
        self.assertFalse(c.isFloating());self.assertTrue(d.user_open);self.assertIsNot(c.widget(),a.widget())

    def test_closed_panel_reopens_without_changing_table_and_source_hide_respected(self):
        manager,w,a,b=self.build();table=a.widget();a.close();self.assertFalse(a.user_open)
        a.set_open(True);self.assertIs(a.widget(),table);self.assertTrue(a.isVisible())
        table.hide();QTest.qWait(30);self.assertFalse(a.isVisible());self.assertTrue(a.user_open)
        w.show_all();self.assertFalse(a.isVisible())
        table.show();QTest.qWait(30);self.assertTrue(a.isVisible())

    def test_float_survives_same_page_tab_switch_but_not_page_hide(self):
        page=QWidget();layout=QVBoxLayout(page);tabs=QTabWidget();layout.addWidget(tabs)
        first=QWidget();inner=QVBoxLayout(first);tabs.addTab(first,'한 화면');tabs.addTab(QWidget(),'다른 탭')
        manager,w,a,b=self.build(parent=first,scope=page);inner.addWidget(w)
        page.resize(1000,800);page.show();self.addCleanup(page.close);QTest.qWait(80)
        a.setFloating(True);QTest.qWait(50);tabs.setCurrentIndex(1);QTest.qWait(80)
        self.assertTrue(a.isVisible());page.hide();QTest.qWait(30);self.assertFalse(a.isVisible())
        page.show();QTest.qWait(80);self.assertTrue(a.isVisible());manager.shutdown();self.assertFalse(a.isVisible())

    def test_corrupt_settings_and_offscreen_float_are_recoverable(self):
        manager,w,a,b=self.build();a.setFloating(True);a.move(99999,99999);QTest.qWait(20)
        w.keep_on_screen(a);self.assertLess(a.x(),99999);self.assertLess(a.y(),99999)
        manager.settings.setValue('dock_workspaces/v1/bad/state','not a valid state');manager.settings.sync()
        _,other,c,d=self.build('bad');self.assertFalse(c.isFloating());self.assertTrue(c.isVisible())
