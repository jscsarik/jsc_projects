"""Small in-window agency chat; existing market editor handles counteroffers."""
from html import escape
import sqlite3
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QFrame,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QTextBrowser,QPushButton,QMessageBox
from ..game_clock import GameDate

STATES={'proposed':'협상 중','countered':'협상 중','accepted_pending':'합의 완료 · 다음 월요일 마감 체결','completed':'체결 완료','rejected':'거절','expired':'기한 만료','void':'체결 실패'}

class TradeChat(QFrame):
    def __init__(self,window):
        super().__init__(window);self.window_owner=window;self.service=window.service;self.rows=()
        self.setObjectName('agencyTradeChat');self.setStyleSheet('QFrame#agencyTradeChat {background:#faf6ff;border:1px solid #c49de3;border-radius:12px;}')
        box=QVBoxLayout(self);top=QHBoxLayout();top.addWidget(QLabel('기획사 채팅 · 트레이드'),1)
        close=QPushButton('닫기');close.clicked.connect(self.hide);top.addWidget(close);box.addLayout(top)
        self.agency=QComboBox();box.addWidget(self.agency)
        self.agency_name=QLabel();self.agency_name.setWordWrap(True);self.agency_name.setMinimumWidth(0)
        self.agency.currentTextChanged.connect(self.agency_name.setText);box.addWidget(self.agency_name)
        self.proposals=QComboBox();box.addWidget(self.proposals)
        self.summary=QLabel();self.summary.setWordWrap(True);box.addWidget(self.summary)
        self.messages=QTextBrowser();box.addWidget(self.messages,1)
        actions=QHBoxLayout();self.accept=QPushButton('수락');self.counter=QPushButton('역제안');self.reject=QPushButton('거절')
        for button in (self.accept,self.counter,self.reject):actions.addWidget(button)
        box.addLayout(actions);self.accept.clicked.connect(lambda:self.respond('accept'));self.reject.clicked.connect(lambda:self.respond('reject'))
        self.counter.clicked.connect(self.edit);self.agency.currentIndexChanged.connect(self.list_proposals);self.proposals.currentIndexChanged.connect(self.render)
        manager=getattr(QApplication.instance(),'theme_manager',None)
        if manager:manager.changed.connect(self.update_message_theme)
        self.hide()

    def toggle(self):
        if self.isVisible():self.hide();return
        self.reposition();self.show();self.raise_();self.refresh()

    def reposition(self):
        w=self.window_owner;self.resize(min(540,max(320,w.width()-30)),min(470,w.height()-70))
        self.move(12,max(12,w.height()-self.height()-24))

    def refresh(self):
        self.rows=self.service.ai_trades.inbox();names={a.id:a.name for a in self.service.agencies()}
        unread=sum(r['unread'] for r in self.rows)
        self.window_owner.chat_header.setText('채팅'+(f' ({unread})' if unread else ''))
        if not self.isVisible():return
        old=self.agency.currentData();self.agency.blockSignals(True);self.agency.clear()
        for a in self.service.agencies():
            if a.id==self.service.draft_session.player_agency():continue
            new=any(r['agency_a']==a.id and r['unread'] for r in self.rows)
            self.agency.addItem(('● ' if new else '')+a.name,a.id)
        self.agency.setCurrentIndex(max(0,self.agency.findData(old)));self.agency.blockSignals(False)
        self.agency_name.setText(self.agency.currentText())
        self.list_proposals()

    def list_proposals(self,*_):
        old=self.proposals.currentData();self.proposals.blockSignals(True);self.proposals.clear()
        for r in self.rows:
            if r['agency_a']==self.agency.currentData():self.proposals.addItem(f"{GameDate(r['created_day'])} · {STATES.get(r['status'],r['status'])}",r['id'])
        self.proposals.setCurrentIndex(max(0,self.proposals.findData(old)));self.proposals.blockSignals(False);self.render()

    def current(self):return next((r for r in self.rows if r['id']==self.proposals.currentData()),None)

    def render(self,*_):
        r=self.current()
        for button in (self.accept,self.reject,self.counter):button.setEnabled(False)
        if not r:self.summary.setText('도착한 트레이드 제안이 없습니다.');self.messages.clear();return
        people={p['id']:p['name'] for p in self.service.market.public_people()};t=r['terms'];amount=t.get('cash',0)
        extra=' / '.join(people.get(p,p) for p in t.get('trainees_a',())+t.get('trainees_b',())) or '없음'
        self.summary.setText(f"{STATES.get(r['status'],r['status'])}\n우리 보냄: {people.get(t['pro_b'],t['pro_b'])} → 받음: {people.get(t['pro_a'],t['pro_a'])}\n현금: {'받음' if amount>=0 else '지급'} {abs(amount):,}원 · 추가 연습생: {extra}\n마감: {GameDate(r['deadline_day'])} · 역제안 {r['counter_count']}/3회")
        self.update_message_theme()
        day=self.service.calendar.state().date
        active=bool(day and r['status'] in ('proposed','countered') and r['created_day']<=day.absolute_day<=r['deadline_day'])
        self.accept.setEnabled(active);self.reject.setEnabled(active);self.counter.setEnabled(active and r['counter_count']<3)
        if self.isVisible():self.service.ai_trades.read(r['id'])

    def update_message_theme(self,*_):
        r=self.current()
        if not r:return
        manager=getattr(QApplication.instance(),'theme_manager',None)
        background='#393046' if manager and manager.mode=='dark' else '#efe3f8'
        names={a.id:a.name for a in self.service.agencies()}
        self.messages.setHtml(''.join(f"<p style='background:{background};padding:6px'><b>{escape(names.get(m['sender'],m['sender']))}</b><br>{escape(m['message'])}</p>" for m in r['messages']))

    def respond(self,action):
        r=self.current()
        if not r:return
        if QMessageBox.question(self,'트레이드 응답','제안을 '+('수락' if action=='accept' else '거절')+'하시겠습니까?')!=QMessageBox.StandardButton.Yes:return
        try:self.service.ai_trades.respond(r['id'],r['agency_b'],action,expected_revision=r['revision'])
        except (ValueError,sqlite3.Error) as error:QMessageBox.warning(self,'트레이드',str(error))
        self.refresh();self.window_owner.refresh_calendar()

    def edit(self):
        r=self.current()
        if not r:return
        w=self.window_owner;w.show_market();page=w.market_page;page.tabs.setCurrentIndex(2)
        row=next((i for i in range(page.trade_table.rowCount()) if page.trade_table.item(i,0).text()==r['id']),None)
        if row is not None:page.trade_table.setCurrentCell(row,0);page.select_trade()
        self.hide()
