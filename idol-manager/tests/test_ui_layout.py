import os
from pathlib import Path
import tempfile
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QStandardItemModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHeaderView
from idol_manager.ui.table_widgets import QTableView, QTableWidget


class TableLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '한글 설정.ini'

    def table(self, key='test', widget=True):
        table = QTableWidget(3, 3) if widget else QTableView()
        if not widget:
            table.setModel(QStandardItemModel(3, 3, table))
        table.setColumnWidth(0, 100); table.setColumnWidth(1, 120); table.setColumnWidth(2, 140)
        table.bind_layout(self.path, key); table.resize(680, 320); table.show()
        self.addCleanup(table.close); self.app.processEvents()
        return table

    def test_all_columns_including_last_draggable_reload_and_restart(self):
        table = self.table(); header = table.horizontalHeader()
        self.assertFalse(header.stretchLastSection())
        for column in range(3):
            self.assertEqual(header.sectionResizeMode(column), QHeaderView.ResizeMode.Interactive)
        start = QPoint(header.sectionViewportPosition(0) + header.sectionSize(0) - 1, header.height() // 2)
        QTest.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(header.viewport(), start + QPoint(65, 0), delay=20)
        QTest.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(65, 0))
        self.assertGreater(table.columnWidth(0), 140)
        header.resizeSection(2, 245)
        width = table.columnWidth(0)
        table.setColumnWidth(0, 100); table.setColumnWidth(2, 140)
        self.assertEqual(table.columnWidth(0), width); self.assertEqual(table.columnWidth(2), 245)
        again = self.table(); self.assertEqual(again.columnWidth(0), width); self.assertEqual(again.columnWidth(2), 245)

    def test_page_specific_reset_and_view_model_reset(self):
        table = self.table(widget=False); table.horizontalHeader().resizeSection(1, 290)
        table.model().clear(); table.model().setColumnCount(3)
        self.assertEqual(table.columnWidth(1), 290)
        other = self.table('another'); self.assertEqual(other.columnWidth(1), 120)
        table.reset_columns(); self.assertEqual(table.columnWidth(1), 120)
        self.assertEqual(self.table().columnWidth(1), 120)

    def test_dynamic_table_and_invalid_preferences(self):
        table = QTableWidget(); self.addCleanup(table.close)
        table.bind_layout(self.path, 'dynamic')
        table.setColumnCount(3); table.setColumnWidth(1, 180)
        table.horizontalHeader().resizeSection(1, 260)
        table.setColumnCount(0); table.setColumnCount(3); table.setColumnWidth(1, 180)
        self.assertEqual(table.columnWidth(1), 260)
        table.reset_columns(); self.assertEqual(table.columnWidth(1), 180)
        table._layout_settings.setValue('invalid', 'bad:data')
        table._layout_settings.sync()
        self.assertEqual(self.table('invalid').columnWidth(0), 100)
