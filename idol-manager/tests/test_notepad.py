import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from idol_manager.ui.notepad import Notepad

class NotepadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_autosave_reload_unicode_and_empty_memo(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'설정/notes.txt';first=Notepad(path);self.addCleanup(first.close)
            first.editor.setPlainText('다음 주 선수 교체\n집중 훈련: 댄스 ✓')
            QTest.qWait(450);self.assertFalse(first.dirty);first.close()
            second=Notepad(path);self.addCleanup(second.close)
            self.assertEqual(second.editor.toPlainText(),'다음 주 선수 교체\n집중 훈련: 댄스 ✓')
            second.editor.clear();second.close()
            self.assertEqual(path.read_text(encoding='utf8'),'');self.assertFalse(list(path.parent.glob('*.tmp')))
    def test_failed_save_preserves_previous_file_and_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'notes.txt';path.write_text('기존 메모',encoding='utf8')
            notes=Notepad(path);self.addCleanup(notes.close);notes.editor.setPlainText('새 메모')
            with patch.object(Path,'replace',side_effect=OSError('test failure')):self.assertFalse(notes.flush())
            self.assertEqual(path.read_text(encoding='utf8'),'기존 메모');self.assertTrue(notes.dirty)
            self.assertEqual(notes.editor.toPlainText(),'새 메모');self.assertTrue(notes.flush())
