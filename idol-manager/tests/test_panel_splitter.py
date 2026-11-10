import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget
from idol_manager.ui.panel_splitter import PanelSplitter


class PanelSplitterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'레이아웃.ini'

    def panel(self,key='match'):
        panel=PanelSplitter(self.path,key)
        for minimum in (110,220):
            widget=QWidget();widget.setMinimumHeight(minimum);panel.addWidget(widget)
        panel.resize(1000,800);panel.show();self.addCleanup(panel.close);QTest.qWait(40)
        return panel

    def drag(self,panel,offset):
        handle=panel.handle(1);start=handle.rect().center()
        QTest.mousePress(handle,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(handle,start+QPoint(0,offset),delay=30)
        QTest.mouseRelease(handle,Qt.MouseButton.LeftButton,pos=start+QPoint(0,offset))
        QTest.qWait(30)

    def test_drag_resize_reopen_and_independent_screens(self):
        panel=self.panel();before=panel.sizes()[0];self.drag(panel,150)
        self.assertGreater(panel.sizes()[0],before+100)
        ratio=panel.sizes()[0]/sum(panel.sizes())
        panel.resize(1000,1000);QTest.qWait(40)
        self.assertAlmostEqual(panel.sizes()[0]/sum(panel.sizes()),ratio,places=2)
        panel.close();again=self.panel()
        self.assertAlmostEqual(again.sizes()[0]/sum(again.sizes()),ratio,places=2)
        self.assertAlmostEqual(self.panel('special').sizes()[0]/778,.35,places=2)

    def test_minimum_height_hide_and_return_does_not_erase_ratio(self):
        panel=self.panel();self.drag(panel,100)
        ratio=panel._ratio();panel.widget(0).hide();QTest.qWait(20)
        self.assertEqual(panel._ratio(),ratio)
        panel.widget(0).show();panel.restore_ratio();QTest.qWait(20)
        self.assertAlmostEqual(panel.sizes()[0]/sum(panel.sizes()),ratio,places=2)
        self.drag(panel,-1000);self.assertGreaterEqual(panel.sizes()[0],110)
        self.drag(panel,1500);self.assertGreaterEqual(panel.sizes()[1],220)
