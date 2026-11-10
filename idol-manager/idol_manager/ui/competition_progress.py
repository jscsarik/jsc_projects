"""Compact, theme-inheriting competition progress cards."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QFrame,QLabel,QPushButton

def show_table_region(table,visible):
    if hasattr(table,'dock_panel'):table.dock_panel.workspace.setVisible(visible)
    table.setVisible(visible)

class CompetitionProgress(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.box=QHBoxLayout(self);self.box.setContentsMargins(0,0,0,0);self.box.setSpacing(8)

    def update_cards(self,cards):
        while self.box.count():
            item=self.box.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        for card in cards:
            frame=QFrame();frame.setObjectName('summary' if card.get('active') else 'competitionStage')
            frame.setStyleSheet('QFrame {background:'+('#f1ebff' if card.get('active') else '#fffaff')+';border:1px solid '+('#b88bd6' if card.get('active') else '#e3d6f4')+';border-radius:10px;} QLabel {background:transparent;border:0;}')
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            box=QVBoxLayout(frame);box.setContentsMargins(10,8,10,8);box.setSpacing(4)
            for text in (card['title'],card.get('body','')):
                label=QLabel(text);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);box.addWidget(label)
            if card.get('action'):
                button=QPushButton(card.get('button','선택'));button.clicked.connect(card['action']);box.addWidget(button)
            self.box.addWidget(frame,1)
