"""Only the six requested title UI smoke checks; no long simulations."""
from contextlib import closing
from pathlib import Path
import os,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QMessageBox
from PySide6.QtTest import QTest
from idol_manager.start_controller import StartController
from tests import test_save_slots as fixtures

class TitleSmokeTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.SlotTests.setUpClass.__func__)
    setUp=fixtures.SlotTests.setUp
    seed=fixtures.SlotTests.seed
    def open(self):
        c=StartController(self.paths,self.resources);self.addCleanup(self.cleanup,c);c.show();self.app.processEvents();return c
    def cleanup(self,c):
        if c.game:
            c.game.before_close=None;c.game.returning_to_menu=True;c.game.close()
        c.title.close();c.bgm.shutdown();c.pool.waitForDone();self.app.processEvents()
    def test_1_home_has_only_two_visible_actions(self):
        c=self.open();buttons=[b.text() for b in c.title.findChildren(QPushButton) if b.isVisible()]
        self.assertEqual(buttons,['불러오기','새 게임']);self.assertFalse(self.paths.slot(1).save.exists())
    def test_2_title_image_aspect_and_resource_packaging(self):
        c=self.open();label=c.title.title_image;self.assertFalse(label.original.isNull())
        self.assertEqual(c.title.title_path.parts[-3:],('assets','title','title.png'))
        QTest.qWait(40);image=label.pixmap();self.assertAlmostEqual(image.width()/image.height(),label.original.width()/label.original.height(),places=2)
        root=Path(__file__).resolve().parents[1];self.assertIn("'assets/title'",(root/'IDOL_Manager.spec').read_text(encoding='utf8'))
    def test_3_load_opens_exactly_two_purple_cards(self):
        self.seed();c=self.open();QTest.mouseClick(c.title.load_button,Qt.MouseButton.LeftButton)
        self.assertIs(c.title.stack.currentWidget(),c.title.slot_page);self.assertEqual(len(c.title.cards),2)
        self.assertTrue(all(card.isVisible() for card in c.title.cards));self.assertEqual(c.title.cards[1].details.text(),'빈 슬롯 · 새 게임을 시작하세요.')
        c.title.back_button.click();self.assertIs(c.title.stack.currentWidget(),c.title.home)
    def test_4_new_game_selects_slot_and_emits_existing_flow(self):
        c=self.open();c.title.new_requested.disconnect(c.new_game);seen=[];c.title.new_requested.connect(seen.append)
        c.title.new_button.click();self.assertEqual(c.title.mode,'new');c.title.cards[1].new.click();self.assertEqual(seen,[2])
    def test_5_exit_question_cancel_keeps_game(self):
        self.seed();c=self.open();c.open_game(1);seen=[]
        def cancel():
            dialog=QApplication.activeModalWidget()
            if isinstance(dialog,QMessageBox):
                seen.append(dialog.text());seen.extend(b.text() for b in dialog.buttons())
                next(b for b in dialog.buttons() if b.text()=='취소').click()
            else:QTimer.singleShot(10,cancel)
        QTimer.singleShot(0,cancel);c.return_to_menu()
        self.assertIn('저장하겠습니까?',seen);self.assertIn('저장 후 종료',seen);self.assertIn('저장하지 않고 종료',seen)
        self.assertIsNotNone(c.game);self.assertFalse(c.game.returning_to_menu)
    def test_6_exit_save_and_skip_paths(self):
        self.seed();c=self.open();c.open_game(1)
        with patch.object(c,'exit_decision',return_value='skip'),patch.object(c.manager,'save_active') as save:
            c.return_to_menu();save.assert_not_called()
        self.assertIsNone(c.game);c.open_game(1)
        with patch.object(c,'exit_decision',return_value='save'),patch.object(c.manager,'save_active',wraps=c.manager.save_active) as save:
            c.return_to_menu();save.assert_called_once()
        self.assertIsNone(c.game);self.assertIs(c.title.stack.currentWidget(),c.title.home)

if __name__=='__main__':unittest.main()
