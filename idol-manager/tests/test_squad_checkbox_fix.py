import os,time,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QMessageBox
from PySide6.QtTest import QTest
from tests import test_squad_ui as fixtures

class CheckboxTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.SquadUITests.setUpClass.__func__)
    setUp=fixtures.SquadUITests.setUp
    copy_db=staticmethod(fixtures.SquadUITests.copy_db)
    open_window=fixtures.SquadUITests.open_window
    def test_checkbox_survives_column_pages_and_maximize_and_confirms_five(self):
        self.open_window();self.window.portrait_layout.refresh();table=self.page.table;pager=table._portrait_pager
        pager.enable(True);pager.original_columns.add(0);pager.original_widths[0]=0
        pager.column_page=2;pager.signature=None;pager.refresh()
        self.assertFalse(table.isColumnHidden(0))
        pager.enable(False);self.window.resize(1920,1080);self.app.processEvents()
        self.assertFalse(table.isColumnHidden(0));self.assertGreaterEqual(table.columnWidth(0),80)
        index=self.page.proxy.index(0,0);table.scrollTo(index);self.app.processEvents()
        rect=table.visualRect(index);QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(rect.left()+10,rect.center().y()))
        self.assertEqual(len(self.page.model.selected_ids),1)
        for row in range(1,5):self.page.proxy.setData(self.page.proxy.index(row,0),Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole)
        self.assertTrue(self.page.confirm_button.isEnabled())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):self.page.confirm_button.click()
        deadline=time.monotonic()+10
        while self.page.job and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertTrue(self.service.squads.snapshot().initialized)
        self.assertEqual(sum(m.squad=='first_team' for m in self.service.squads.snapshot().members),5)
        self.window.grab().save(str(__import__('pathlib').Path(__file__).resolve().parents[1]/'reports/squad_checkbox/fixed.png'))
    def test_initial_replacement_second_team_can_be_checked(self):
        from dataclasses import replace
        self.open_window();member=replace(self.page.model.rows[0],squad='second_team')
        self.page.model.replace([member],True)
        index=self.page.model.index(0,0)
        self.assertIsNotNone(index.data(Qt.ItemDataRole.CheckStateRole))
        self.assertTrue(self.page.model.setData(index,Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole))
        self.assertIn(member.id,self.page.model.selected_ids)
