"""Reserved bottom-right coach area; no floating overlay over game controls."""
from html import escape
from urllib.parse import quote,unquote
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTextBrowser
from ..coach_service import CoachService
from ..game_clock import GameDate

class CoachPanel(QFrame):
    def __init__(self,window,*,compact=False):
        super().__init__(window);self.owner=window;self.service=CoachService(window.service.database);self.rows=[];self.announcements=[]
        self.setObjectName('coachPanel');self.setMinimumWidth(340);self.setMaximumWidth(460)
        self.setStyleSheet('QFrame#coachPanel {border:1px solid #9e7abd;border-radius:8px;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(8,4,8,4);layout.setSpacing(3)
        top=QHBoxLayout();self.toggle=QPushButton('담당 코치 · 채팅');self.toggle.clicked.connect(self.expand)
        self.alert=QLabel('!');self.alert.setStyleSheet('color:#e53935;font-size:22px;font-weight:bold;background:transparent;border:none;')
        self.alert.setFixedWidth(16)
        self.blink=QTimer(self);self.blink.setInterval(700);self.blink.timeout.connect(self.blink_alert)
        top.addWidget(self.toggle,1);top.addWidget(self.alert);layout.addLayout(top)
        if compact:
            self.setMinimumWidth(0);self.setMaximumWidth(16777215)
            self.setStyleSheet('QFrame#coachPanel {border:none;background:transparent;}')
            layout.setContentsMargins(0,0,0,0);top.setSpacing(2)
            self.toggle.setText('담당 코치');self.toggle.setStyleSheet('padding:8px 4px;border-radius:9px;')
        self.body=QDialog(window);self.body.setWindowTitle('담당 코치 · 오늘의 할 일')
        area=self.body.screen().availableGeometry();self.body.resize(min(620,area.width()-40),min(540,area.height()-80))
        box=QVBoxLayout(self.body);box.setContentsMargins(16,16,16,16)
        self.heading=QLabel('담당 코치 · 오늘의 할 일');self.heading.setObjectName('title');self.heading.setWordWrap(True);box.addWidget(self.heading)
        self.browser=QTextBrowser();self.browser.setStyleSheet('QTextBrowser {background:#fcf9ff;color:#3e3150;border:1px solid #9e7abd;border-radius:5px;}');self.browser.setOpenLinks(False);self.browser.setOpenExternalLinks(False);self.browser.anchorClicked.connect(self.link)
        box.addWidget(self.browser,1)
        buttons=QHBoxLayout();self.read_all=QPushButton('오늘 안내 읽음');self.read_all.clicked.connect(self.mark_all);buttons.addWidget(self.read_all)
        close=QPushButton('닫기');close.clicked.connect(self.body.close);buttons.addWidget(close);box.addLayout(buttons)
        self.body.hide()
        self.timer=QTimer(self);self.timer.setInterval(3000);self.timer.timeout.connect(self.refresh);self.timer.start()
        from PySide6.QtWidgets import QApplication
        manager=getattr(QApplication.instance(),'theme_manager',None)
        if manager:manager.changed.connect(self.render)

    def ready(self):
        return not self.owner._closing and self.owner.job is None and self.owner.squad_menu.isEnabled() and not self.owner.match_page.is_busy() and not self.owner.special_page.is_busy()

    def refresh(self):
        if not self.ready():return
        self.rows=self.service.refresh()
        self.announcements=self.service.announcements()
        self.render()

    def render(self):
        unread=any(not r['is_read'] for r in self.rows)
        self.alert.setVisible(unread)
        if unread and not self.blink.isActive():self.alert.setText('!');self.blink.start()
        elif not unread:self.blink.stop();self.alert.setText('!')
        if self.body.isHidden():return

        from PySide6.QtWidgets import QApplication
        manager=getattr(QApplication.instance(),'theme_manager',None)
        dark=bool(manager and manager.mode=='dark')
        color='#d6b8f4' if dark else '#58307E'
        title_color='#e2d4f5' if dark else '#4A2E6D'
        border_color='#4a4358' if dark else '#DDD8E6'
        background,foreground=('#292c3b','#e9e6f0') if dark else ('#fcf9ff','#262238')

        day_title=escape(str(GameDate(self.rows[0]['absolute_day']))) if self.rows else ''
        status_badge='새 안내' if unread else '읽음'

        parts=[f'<p style="margin:0 0 10px 0; font-size:13px; line-height:1.5;"><b>담당 코치</b> · {day_title}<br><span style="font-size:12px; color:{color};">{status_badge}</span></p>']

        # 1. 오늘의 업무 섹션
        parts.append(f'<h4 style="margin:10px 0 6px 0; color:{title_color}; font-size:14px; border-bottom:1px solid {border_color}; padding-bottom:3px;">오늘의 업무</h4>')
        task_items=[]
        for r in self.rows:
            key=quote(r['report_key'],safe='')
            for t in r['targets']:
                href='go:'+key+':'+quote(t['target'],safe='')
                task_items.append(('✓ ' if t['done'] else '□ ')+f'<a href="{href}" style="color:{color}; text-decoration:none; font-weight:bold;">'+escape(t['text'])+'</a><br>')
            if not r['is_read']:
                task_items.append(f'<a href="read:{key}" style="font-size:11px; color:#9e7abd; text-decoration:underline;">[읽음 표시]</a><br>')
        if task_items:
            parts.append(f'<div style="margin:4px 0 12px 0; line-height:1.7; font-size:13px;">{"".join(task_items)}</div>')
        else:
            parts.append('<div style="margin:4px 0 12px 0; font-size:13px; color:#888;">오늘은 별도의 필수 업무가 없습니다.</div>')

        # 2. 결과 발표 섹션
        parts.append(f'<h4 style="margin:14px 0 6px 0; color:{title_color}; font-size:14px; border-bottom:1px solid {border_color}; padding-bottom:3px;">결과 발표</h4>')
        announcements=getattr(self,'announcements',[])
        if announcements:
            result_items=[f'- {escape(item)}<br>' for item in announcements]
            parts.append(f'<div style="margin:4px 0 4px 0; line-height:1.7; font-size:13px;">{"".join(result_items)}</div>')
        else:
            parts.append('<div style="margin:4px 0 4px 0; font-size:13px; color:#888;">오늘 전달할 결과 발표는 없습니다.</div>')

        self.heading.setText('오늘의 할 일\n'+day_title)
        position=self.browser.verticalScrollBar().value()
        self.browser.setHtml(f'<style>a {{color:{color};}}</style><body style="color:{foreground}; font-family:sans-serif;"><table width="100%" cellpadding="14"><tr><td bgcolor="{background}">{"".join(parts)}</td></tr></table></body>')
        self.browser.verticalScrollBar().setValue(position)

    def blink_alert(self):
        self.alert.setText('' if self.alert.text() else '!')

    def expand(self):
        self.body.show();self.body.raise_();self.body.activateWindow();self.refresh()

    def mark_all(self):
        for row in self.rows:self.service.read(row['report_key'])
        self.refresh()

    def link(self,url):
        if not self.ready():return
        value=url.toString()
        if value.startswith('read:'):self.service.read(unquote(value[5:]));self.refresh();return
        if not value.startswith('go:'):return
        _,key,target=value.split(':',2);target=unquote(target)
        routes={'draft':self.owner.show_draft,'annual':self.owner.show_annual,'squads':self.owner.show_squads,
            'growth':self.owner.show_development,'training':self.owner.show_training,'schedule':self.owner.show_schedule,
            'matches':self.owner.show_matches,'specials':self.owner.show_specials,'finals':self.owner.show_finals}
        if target in routes:routes[target]()
        elif target.startswith('market:') and target[7:].isdigit() and 0<=int(target[7:])<7:
            self.owner.show_market();self.owner.market_page.tabs.setCurrentIndex(int(target[7:]))
        elif target.startswith('profile:'):self.owner.profiles.open(target[8:])
        else:return
        self.service.read(unquote(key));self.refresh()
