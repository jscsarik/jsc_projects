import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from unittest.mock import patch
from idol_manager.game_clock import GameDate
from idol_manager.ui.training_page import TrainingPage,SkillButtonDelegate
from idol_manager.ui.coach_panel import CoachPanel
from idol_manager.ui.theme_manager import ThemeManager

class TrainingButtonStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_raised_buttons_select_toggle_and_keep_geometry_in_both_themes(self):
        with tempfile.TemporaryDirectory() as folder:
            player=dict(id='p',name='선수',career_status='second_team',skills=(70,)*8,focus=None,last_day=None,last_delta=0,photo_path='')
            service=SimpleNamespace(draft_session=SimpleNamespace(player_agency=lambda:'ador'),agencies=lambda:[],
                training=SimpleNamespace(state=lambda agency:dict(day=GameDate(8),players=[player],confirmed=False,revision=0)))
            page=TrainingPage(service);self.addCleanup(page.close);page.resize(1400,500);page.show()
            manager=getattr(self.app,'theme_manager',None) or ThemeManager(self.app,Path(folder)/'appearance.ini')
            for mode in ('light','dark','light'):
                manager.set_mode(mode);QTest.qWait(140)
                self.assertIsInstance(page.table.itemDelegateForColumn(4),SkillButtonDelegate)
                width=page.table.columnWidth(4);index=page.table.model().index(0,4)
                QTest.mouseClick(page.table.viewport(),Qt.MouseButton.LeftButton,pos=page.table.visualRect(index).center())
                self.assertEqual(page.pending['p'],'vocal')
                page.grab()  # Exercise the light/dark raised-button paint path.
                QTest.mouseClick(page.table.viewport(),Qt.MouseButton.LeftButton,pos=page.table.visualRect(index).center())
                self.assertIsNone(page.pending['p']);self.assertEqual(page.table.columnWidth(4),width)
            output=Path('reports/training_buttons');output.mkdir(exist_ok=True)
            self.assertTrue(page.updatesEnabled())
            page.grab().save(str(output/'raised_buttons.png'))

    def test_unread_coach_blinks_until_marked_read_without_width_changes(self):
        owner=QWidget();owner.service=SimpleNamespace(database=None)
        self.addCleanup(owner.close)
        with patch('idol_manager.ui.coach_panel.CoachService'):
            panel=CoachPanel(owner);panel.rows=[dict(is_read=False)];panel.render()
            self.assertTrue(panel.blink.isActive());width=panel.alert.width()
            QTest.qWait(760);self.assertEqual(panel.alert.text(),'');self.assertEqual(panel.alert.width(),width)
            QTest.qWait(760);self.assertEqual(panel.alert.text(),'!')
            panel.rows=[dict(is_read=True)];panel.render();self.assertFalse(panel.blink.isActive())
            panel.timer.stop();panel.blink.stop()
