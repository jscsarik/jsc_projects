"""Title and two explicit save cards. All destructive actions have two confirmations."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QPixmap,QFont
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QFrame,QComboBox,QMessageBox,QFileDialog,QSizePolicy,QStackedWidget)

from .theme import STYLE as GAME_STYLE
from ..storage import resource_root

STYLE=GAME_STYLE+"""
QFrame#card {background:#ffffff;border:1px solid #e0d0ee;border-radius:16px;}
QFrame#card[selected="true"] {border:2px solid #b38bd3;background:#f8f1ff;}
QFrame#card QLabel {background:transparent;border:0;}
QPushButton#title_action {background:#e9dcf7;color:#69458b;border:1px solid #d3b9e9;font-size:18px;padding:14px;}
QPushButton#title_action:hover {background:#dfc9f1;}
"""


def time_label(value):
    try:return datetime.fromisoformat(value).astimezone().strftime('%Y-%m-%d %H:%M:%S') if value else '기록 없음'
    except (TypeError,ValueError):return '기록 확인 필요'

def confirm_action(parent,title,text,action):
    dialog=QMessageBox(parent);dialog.setWindowTitle(title);dialog.setText(text)
    dialog.setIcon(QMessageBox.Icon.Warning)
    confirm=dialog.addButton(action,QMessageBox.ButtonRole.DestructiveRole)
    cancel=dialog.addButton('취소',QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel);dialog.setEscapeButton(cancel);dialog.exec()
    return dialog.clickedButton() is confirm


class PreviewLabel(QLabel):
    def __init__(self):
        super().__init__('EMPTY SLOT');self.original=QPixmap()
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
    def set_preview(self,pix):
        self.original=pix
        self._scale()
    def _scale(self):
        if not self.original.isNull():
            self.setPixmap(self.original.scaled(self.size().boundedTo(self.original.size()),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        else:self.setPixmap(QPixmap())
    def resizeEvent(self,event):
        super().resizeEvent(event);self._scale()


class SlotCard(QFrame):
    selected=Signal(int)
    open_requested=Signal(int)
    new_requested=Signal(int)
    delete_requested=Signal(int)
    def __init__(self,identity,parent=None):
        super().__init__(parent);self.identity=identity;self.setObjectName('card');self.setMinimumWidth(0)
        box=QVBoxLayout(self);box.setContentsMargins(16,14,16,14)
        self.heading=QPushButton(f'슬롯 {identity} 선택');self.heading.clicked.connect(lambda:self.selected.emit(identity));box.addWidget(self.heading)
        self.image=PreviewLabel();self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.image.setMinimumHeight(150)
        self.image.setMaximumHeight(225);box.addWidget(self.image);self.image.hide()
        self.details=QLabel();self.details.setWordWrap(True);box.addWidget(self.details)
        self.load=QPushButton('불러오기');self.load.clicked.connect(lambda:self.open_requested.emit(identity))
        self.new=QPushButton('새 게임 시작');self.new.clicked.connect(lambda:self.new_requested.emit(identity))
        self.remove=QPushButton('삭제');self.remove.clicked.connect(lambda:self.delete_requested.emit(identity))
        row=QHBoxLayout()
        for button in (self.load,self.new,self.remove):row.addWidget(button)
        box.addLayout(row)
    def update_slot(self,item,path):
        self.item=item;meta=item['meta'];empty=item['state']=='empty'
        self.load.setEnabled(not empty);self.remove.setEnabled(not empty)
        self.new.setText('새 게임 시작' if empty else '새 게임으로 덮어쓰기')
        self.load.setText('오류 확인' if item['state']=='error' else '불러오기')
        pix=QPixmap(str(Path(path)/'thumbnail.png'))
        if not empty and not pix.isNull():
            self.image.set_preview(pix)
        else:self.image.set_preview(QPixmap());self.image.setText('EMPTY SLOT' if empty else '미리보기 없음')
        if empty:self.details.setText('빈 슬롯 · 새 게임을 시작하세요.')
        else:
            text=f"{meta.get('agency_name','저장 정보 확인 필요')}\n저장 데이터 있음\n{meta.get('date_label','날짜 확인 필요')}\n마지막 저장: {time_label(meta.get('last_saved_at'))}"
            if item['state'] in ('error','recoverable'):text+='\n'+item['error']+f"\n확인된 백업: {len(item.get('backups',[]))}개"
            self.details.setText(text)


class StartMenu(QMainWindow):
    continue_requested=Signal()
    open_requested=Signal(int)
    new_requested=Signal(int)
    delete_requested=Signal(int)
    import_requested=Signal(str,int)
    def __init__(self,manager):
        super().__init__();self.manager=manager;self.selection=1;self.mode='load';self.busy=False
        self.setWindowTitle('IDOL Manager');self.resize(1100,780);self.setMinimumSize(720,600);self.setStyleSheet(STYLE)
        self.stack=QStackedWidget();self.setCentralWidget(self.stack)
        self.home=QWidget();home=QVBoxLayout(self.home);home.setContentsMargins(24,24,24,28)
        self.title_image=PreviewLabel();self.title_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_image.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        self.title_path=resource_root()/'assets/title/title.png'
        self.title_image.set_preview(QPixmap(str(self.title_path)))
        if self.title_image.original.isNull():self.title_image.setText('IDOL Manager · 타이틀 이미지를 찾을 수 없습니다.')
        home.addWidget(self.title_image,1)
        actions=QHBoxLayout();actions.addStretch()
        self.load_button=QPushButton('불러오기');self.new_button=QPushButton('새 게임')
        for button in (self.load_button,self.new_button):
            button.setObjectName('title_action');button.setMinimumSize(180,56);button.setMaximumWidth(260);actions.addWidget(button)
        actions.setSpacing(20);actions.addStretch();home.addLayout(actions);self.stack.addWidget(self.home)
        self.slot_page=QWidget();box=QVBoxLayout(self.slot_page);box.setContentsMargins(28,24,28,24);box.setSpacing(18)
        self.page_title=QLabel('불러오기');self.page_title.setObjectName('title');box.addWidget(self.page_title)
        self.notice=QLabel();self.notice.setWordWrap(True);box.addWidget(self.notice)
        cards=QHBoxLayout();self.cards=[]
        for identity in (1,2):
            card=SlotCard(identity);self.cards.append(card);cards.addWidget(card,1)
            card.selected.connect(self.select);card.open_requested.connect(self.open_requested)
            card.new_requested.connect(self.new_requested);card.delete_requested.connect(self.delete_requested)
        box.addStretch();box.addLayout(cards);box.addStretch()
        self.legacy=QFrame();legacy_box=QVBoxLayout(self.legacy)
        text=QLabel('이전 단일 세이브를 복사하여 가져옵니다. 원본은 보존합니다.');text.setWordWrap(True);legacy_box.addWidget(text)
        self.sources=QComboBox();self.sources.setMinimumContentsLength(20)
        self.sources.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);legacy_box.addWidget(self.sources)
        row=QHBoxLayout()
        for identity in (1,2):
            button=QPushButton(f'슬롯 {identity}로 가져오기');button.clicked.connect(lambda _,i=identity:self.request_import(i));row.addWidget(button)
        browse=QPushButton('파일 찾기');browse.clicked.connect(self.browse);row.addWidget(browse);legacy_box.addLayout(row);box.addWidget(self.legacy);self.legacy.hide()
        footer=QHBoxLayout();self.back_button=QPushButton('뒤로가기');self.back_button.clicked.connect(self.show_home);footer.addWidget(self.back_button)
        self.legacy_button=QPushButton('이전 저장 가져오기');self.legacy_button.clicked.connect(lambda:self.legacy.setVisible(not self.legacy.isVisible()));footer.addWidget(self.legacy_button)
        footer.addStretch();self.chosen=QPushButton('선택 슬롯에 새 게임 시작');self.chosen.clicked.connect(self.run_selection);footer.addWidget(self.chosen);box.addLayout(footer)
        self.stack.addWidget(self.slot_page)
        self.load_button.clicked.connect(lambda:self.select_mode('load'));self.new_button.clicked.connect(lambda:self.select_mode('new'))
        # Keep the controller's recent-slot API without adding a home-screen button.
        self.continue_button=QPushButton(self);self.continue_button.hide();self.select_button=self.load_button
        self.select(1);self.show_home()
    def show_home(self):
        self.stack.setCurrentWidget(self.home);self.legacy.hide()
    def reload(self):
        self.slots=self.manager.scan()
        for item,card in zip(self.slots,self.cards):card.update_slot(item,self.manager.slot(item['slot_id']).directory)
        self.continue_button.setEnabled(self.manager.latest(self.slots) is not None)
        count=sum(s['state']!='empty' for s in self.slots)
        self.notice.setText(f'세이브 {count}/2 · 각 슬롯은 독립적인 게임입니다.' if count else '이어할 게임이 없습니다. 새 게임을 시작해 주세요.')
        self.sources.clear()
        for p in self.manager.legacy_sources():self.sources.addItem(str(p),str(p))
        self.legacy.hide()
        self.select(self.selection)
    def select(self,identity):
        self.selection=identity
        for card in self.cards:
            card.setProperty('selected',card.identity==identity);card.style().unpolish(card);card.style().polish(card)
    def select_mode(self,mode):
        self.mode=mode;self.stack.setCurrentWidget(self.slot_page);self.legacy.hide()
        self.page_title.setText('새 게임 · 저장 위치 선택' if mode=='new' else '불러오기')
        self.notice.setText('슬롯 1 또는 슬롯 2를 선택하세요. 기존 저장이 있으면 덮어쓰기를 확인합니다.' if mode=='new' else '저장된 슬롯을 불러오세요. 이전 단일 세이브는 아래에서 가져올 수 있습니다.')
        self.chosen.setVisible(mode=='new');self.legacy_button.setVisible(mode=='load')
        for card in self.cards:
            card.load.setVisible(mode=='load');card.remove.setVisible(mode=='load');card.new.setVisible(mode=='new')
        if mode=='new':
            empty=next((s['slot_id'] for s in self.slots if s['state']=='empty'),self.selection);self.select(empty)
    def run_selection(self):
        (self.new_requested if self.mode=='new' else self.open_requested).emit(self.selection)
    def request_import(self,identity):
        if self.sources.currentData():self.import_requested.emit(self.sources.currentData(),identity)
    def browse(self):
        path,_=QFileDialog.getOpenFileName(self,'이전 단일 세이브 선택','','SQLite (*.sqlite3 *.db);;모든 파일 (*)')
        if path:self.sources.addItem(path,path);self.sources.setCurrentIndex(self.sources.count()-1);self.legacy.show()
    def confirm_replace(self,identity,operation):
        item=self.slots[identity-1]
        if item['state']=='empty' and operation!='삭제':return True
        meta=item['meta'];details=f"슬롯 {identity} · {meta.get('agency_name','정보 확인 불가')}\n{meta.get('date_label','날짜 확인 불가')}"
        text=details+'\n\n'+('슬롯의 게임을 삭제하시겠습니까?' if operation=='삭제' else '이 슬롯에는 기존 게임이 저장되어 있습니다. 새 게임/가져온 게임으로 기존 진행 데이터를 교체하시겠습니까?')
        label='삭제 확인' if operation=='삭제' else '기존 게임 덮어쓰기'
        if not confirm_action(self,operation+' 확인',text,label):return False
        return confirm_action(self,operation+' 최종 확인',details+'\n\n복구용 백업과 이전 슬롯 폴더를 보관합니다. '+operation+'를 확정하시겠습니까?',label)
    def set_busy(self,busy):
        self.busy=busy;self.centralWidget().setEnabled(not busy)
        if busy:self.statusBar().showMessage('저장 파일을 검증·처리 중입니다. 기존 세이브를 보존하고 있습니다.')
        else:self.statusBar().clearMessage()
    def closeEvent(self,event):
        if self.busy:event.ignore();return
        super().closeEvent(event)
