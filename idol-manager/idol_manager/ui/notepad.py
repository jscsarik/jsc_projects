"""Small per-slot text memo, saved independently of game transactions."""
from pathlib import Path
import os,uuid
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QLabel,QPushButton

class Notepad(QDialog):
    def __init__(self,path,parent=None):
        super().__init__(parent);self.path=Path(path);self.dirty=False
        self.setWindowTitle('메모장');area=self.screen().availableGeometry()
        self.resize(min(520,area.width()-40),min(480,area.height()-80))
        layout=QVBoxLayout(self);self.editor=QPlainTextEdit();self.editor.setPlaceholderText('자유롭게 메모하세요. 내용은 자동 저장됩니다.')
        layout.addWidget(self.editor,1);self.status=QLabel('자동 저장');layout.addWidget(self.status)
        self.save_timer=QTimer(self);self.save_timer.setSingleShot(True);self.save_timer.setInterval(350);self.save_timer.timeout.connect(self.flush)
        try:self.editor.setPlainText(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:pass
        except (OSError,UnicodeError):self.status.setText('기존 메모를 읽지 못했습니다. 저장 경로를 확인해 주세요.')
        self.editor.textChanged.connect(self.changed)
        buttons=QHBoxLayout();save=QPushButton('저장');save.clicked.connect(self.flush);buttons.addWidget(save)
        close=QPushButton('닫기');close.clicked.connect(self.close);buttons.addWidget(close);layout.addLayout(buttons)

    def changed(self):
        self.dirty=True;self.status.setText('저장 중…');self.save_timer.start()

    def flush(self):
        self.save_timer.stop()
        if not self.dirty:return True
        temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with temporary.open('w',encoding='utf-8',newline='') as stream:
                stream.write(self.editor.toPlainText());stream.flush();os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError:
            self.status.setText('저장 실패 · 입력 내용은 창에 유지됩니다. 저장 경로를 확인하고 다시 저장해 주세요.')
            return False
        finally:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
        self.dirty=False;self.status.setText('자동 저장 완료');return True

    def open_window(self):self.show();self.raise_();self.activateWindow();self.editor.setFocus()

    def closeEvent(self,event):
        if self.flush():event.accept()
        else:event.ignore()
