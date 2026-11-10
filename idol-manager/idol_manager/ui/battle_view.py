"""Presentation only: frozen participants and persisted judgments, never rolls."""
from collections import deque
from collections import Counter
from PySide6.QtCore import Qt,QVariantAnimation,QAbstractAnimation,Signal,QSize
from PySide6.QtGui import QColor,QPixmap
from PySide6.QtWidgets import (QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,
    QScrollArea,QWidget,QSizePolicy,QProgressBar,QLayout)

SKILL_LABELS=dict(zip(('vocal','dance','rap','entertainment','appearance','physique','intelligence','leadership'),
    ('보컬','댄스','랩','예능','외모','신체','지성','리더십')))


class CardPhoto(QLabel):
    clicked=Signal()
    def __init__(self,height,parent=None):
        super().__init__(parent);self.original=None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(40,40);self.setMaximumHeight(height)
        # The previous scaled pixmap must not become a new minimum height.
        # Layout stretch supplies the space; fit() preserves the photo ratio.
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)

    def set_photo(self,pixmap):self.original=pixmap;self.fit()

    def fit(self):
        if self.original is not None:
            # ThumbnailCache stores 2x pixels; fit to logical widget dimensions.
            image=QPixmap(self.original);image.setDevicePixelRatio(1.0)
            self.setPixmap(image.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self,event):super().resizeEvent(event);self.fit()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.clicked.emit()
        super().mousePressEvent(event)


class ProfileName(QLabel):
    clicked=Signal()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.clicked.emit()
        super().mousePressEvent(event)


class ParticipantCard(QFrame):
    profile_requested=Signal(str)
    def __init__(self,person,photos,count,parent=None):
        super().__init__(parent);self.person=person;self.photos=photos;self.successes=0;self.last_success=None;self.phase_successes=Counter()
        self.setObjectName('battleCard');self.setMinimumWidth(90)
        layout=QVBoxLayout(self);layout.setContentsMargins(6,5,6,5);layout.setSpacing(2)
        self.name=ProfileName(person['name']);self.name.setObjectName('performerName');self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setWordWrap(True);layout.addWidget(self.name)
        self.badge=QLabel('★ 1군 리더' if person['leader'] else '출전자');self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.badge)
        self.photo=CardPhoto(640);layout.addWidget(self.photo,1)
        for clickable in (self.name,self.photo):
            clickable.setCursor(Qt.CursorShape.PointingHandCursor);clickable.setToolTip('아이돌 상세 프로필')
            clickable.clicked.connect(lambda:self.profile_requested.emit(self.person['id']))
        self.score=QLabel();self.score.setObjectName('performerScore');self.score.setAlignment(Qt.AlignmentFlag.AlignCenter);self.score.setWordWrap(True);layout.addWidget(self.score);self.update_score()
        self.state=QLabel('진행 대기');self.state.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.state)
        self.flash=QVariantAnimation(self);self.flash.setDuration(350);self.flash.setStartValue(1.0);self.flash.setEndValue(0.0)
        self.flash.valueChanged.connect(self._paint_flash);self._paint_flash(0.0);self.refresh_photo()

    def refresh_photo(self):self.photo.set_photo(self.photos.get(self.person['photo_path'] or ''))

    def _paint_flash(self,value):
        neutral=QColor('#514567');accent=QColor('#66f0d2' if self.last_success else '#f37ea7')
        color=QColor(*(round(neutral.getRgb()[i]*(1-float(value))+accent.getRgb()[i]*float(value)) for i in range(3)))
        self.setStyleSheet(f'QFrame#battleCard {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #302642,stop:1 #211c32);border:2px solid {color.name()};border-radius:14px;}}')

    def show_event(self,event):
        self.successes+=int(event.success);self.last_success=event.success
        self.phase_successes[event.phase]+=int(event.success);self.update_score()
        prefix={'main':'주요 능력치 · ','support':'일반 능력치 · ','leader':'리더 추가 · ','deathmatch':'데스매치 · '}.get(event.phase,'')
        self.state.setText(prefix+('+1 성공' if event.success else '실패'))
        self.flash.stop();self.flash.start()

    def update_score(self):
        text=f'주요 능력치 성공 {self.phase_successes["main"]}회\n일반 능력치 성공 {self.phase_successes["support"]}회'
        if not getattr(self,'_card_mode',(False,False))[1]:text+=f'\n합계 {self.successes}회'
        self.score.setText(text)
        self.score.setToolTip(f'합계 {self.successes}회 · 리더 추가 {self.phase_successes["leader"]}회 · 데스매치 {self.phase_successes["deathmatch"]}회 (합계에 포함)')

    def compact(self,enabled,tight=False):
        mode=(enabled,tight)
        if getattr(self,'_card_mode',None)==mode:return
        self._card_mode=mode
        self.setMinimumWidth(72 if enabled else 90)
        self.layout().setContentsMargins(4,3,4,3) if enabled else self.layout().setContentsMargins(6,5,6,5)
        self.layout().setSpacing(1 if enabled else 2)
        self.name.setStyleSheet('font-size:11px;padding:0;' if enabled else '')
        self.badge.setStyleSheet('font-size:10px;' if enabled else '')
        self.score.setStyleSheet(('font-size:10px;' if tight else 'font-size:11px;') if enabled else '')
        self.state.setStyleSheet('font-size:10px;' if enabled else '')
        self.badge.setVisible(not tight);self.state.setVisible(not tight)
        self.name.setText(('★ ' if tight and self.person['leader'] else '')+self.person['name'])
        self.update_score()
        self.photo.setMinimumSize(28,28) if tight else self.photo.setMinimumSize(40,40)
        for label in (self.name,self.badge,self.score,self.state):
            label.setMinimumWidth(0);label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)

    def pause(self,paused):
        if paused and self.flash.state()==QAbstractAnimation.State.Running:self.flash.pause()
        elif not paused and self.flash.state()==QAbstractAnimation.State.Paused:self.flash.resume()

    def settle(self):
        self.flash.stop();self._paint_flash(0.0);self.state.setText('진행 중')


class TeamPanel(QWidget):
    def __init__(self,identity,name,people,photos,parent=None):
        super().__init__(parent);self.identity=identity
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        heading=QLabel(name);heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setObjectName('teamName');heading.setWordWrap(True);layout.addWidget(heading)
        self.total=QLabel('0');self.total.setObjectName('teamTotal');self.total.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.total)
        if len(people)>1:
            layout.setSpacing(3);heading.setStyleSheet('font-size:14px;padding:0;')
            self.total.setStyleSheet('font-size:30px;padding:0;')
        host=QWidget();host.setMinimumSize(0,0);self.host=host
        self.grid=QGridLayout(host);self.grid.setContentsMargins(2,2,2,2);self.grid.setSpacing(4)
        self.cards=[ParticipantCard(p,photos,len(people)) for p in people]
        if not people:self.grid.addWidget(QLabel('출전 가능 선수 없음 · 몰수 처리'),0,0)
        self.columns=1 if len(people)==1 else 2 if len(people) in (2,4) else 3
        for column in range(6):self.grid.setColumnStretch(column,1)
        for index,card in enumerate(self.cards):
            row,column=divmod(index,self.columns)
            row_count=min(self.columns,len(self.cards)-row*self.columns)
            span=6//self.columns;offset=(6-row_count*span)//2
            self.grid.addWidget(card,row,offset+column*span,1,span)
            self.grid.setRowStretch(row,1);card.setVisible(True)
            card.compact(len(people)>1,len(people)>self.columns)
        layout.addWidget(host,1)

    def focus_person(self,identity):
        # Every participant stays visible. The event's own card flashes instead
        # of switching to a single portrait and hiding the other four players.
        self.active_person=identity

    def reflow(self):
        rows=max(1,(len(self.cards)+self.columns-1)//self.columns)
        for card in self.cards:card.compact(len(self.cards)>1,rows>1)

    def resizeEvent(self,event):super().resizeEvent(event);self.reflow()


class BattleView(QWidget):
    """Reusable two-team scene. Caller owns playback, timing, results and BGM."""
    profile_requested=Signal(str)
    def __init__(self,photos,parent=None):
        super().__init__(parent);self.photos=photos;self.cards={};self.teams=[];self.logs=deque(maxlen=5)
        self.setObjectName('battleStage');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.setStyleSheet('''
            QWidget#battleStage {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #15182e,stop:0.5 #30203e,stop:1 #111f32);border-radius:18px;}
            QWidget#battleStage QWidget {background:transparent;color:#eee6fa;}
            QWidget#battleStage QScrollArea {border:0;}
            QLabel#stageHeading {font-size:19px;font-weight:bold;color:#f0d5ff;padding:8px;}
            QLabel#stagePhase {color:#7bf0d7;font-weight:bold;letter-spacing:1px;}
            QLabel#teamName {font-size:18px;font-weight:bold;color:#d4c1ee;}
            QLabel#teamTotal {font-size:38px;font-weight:900;color:#fff0fc;padding:2px;}
            QLabel#performerName {font-weight:bold;color:#f4eaff;padding:4px;}
            QLabel#performerScore {font-size:17px;font-weight:bold;color:#8af1dd;}
            QLabel#stageLog {background:#1c1930;border:1px solid #49375d;border-radius:10px;padding:10px;color:#cbbbdc;}
            QProgressBar#stageProgress {background:#221c35;border:0;border-radius:4px;min-height:6px;max-height:6px;}
            QProgressBar#stageProgress::chunk {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #bc8cfa,stop:1 #ff90c9);border-radius:4px;}
        ''')
        layout=QVBoxLayout(self);layout.setContentsMargins(14,12,14,12);layout.setSpacing(8)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.phase=QLabel('ON STAGE · 대결 준비');self.phase.setObjectName('stagePhase');layout.addWidget(self.phase)
        self.content=QLabel('경기 시작 대기');self.content.setWordWrap(True);layout.addWidget(self.content)
        self.content.setObjectName('stageHeading')
        self.progress=QProgressBar();self.progress.setObjectName('stageProgress');self.progress.setRange(0,60);self.progress.setValue(0);self.progress.setTextVisible(False);layout.addWidget(self.progress)
        self.arena=QHBoxLayout();layout.addLayout(self.arena,1)
        self.log=QLabel('저장된 판정 이벤트를 재생합니다.');self.log.setWordWrap(True)
        self.log.setMinimumHeight(0);self.log.setMaximumHeight(50);self.log.setObjectName('stageLog')
        layout.addWidget(self.log)
        photos.changed.connect(self.refresh_photos)

    def minimumSizeHint(self):
        # Native dock layouts otherwise keep an old two-row content minimum
        # outside the viewport. The arena reflows within its assigned space.
        return QSize(0,0)

    def configure(self,content,agencies,people,teamwork=()):
        self.teamwork=teamwork;self.shown_sequence=0
        self.clear_animations();self.cards={};self.teams=[];self.logs.clear()
        while self.arena.count():
            item=self.arena.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.content.setText(content);self.log.setText('저장 완료 · 기본 판정 시작 대기')
        dense=any(sum(p['agency_id']==identity for p in people)>1 for identity,_ in agencies)
        multirow=any(sum(p['agency_id']==identity for p in people)>=4 for identity,_ in agencies)
        self.layout().setContentsMargins(10,8,10,8) if dense else self.layout().setContentsMargins(14,12,14,12)
        self.layout().setSpacing(5 if dense else 8)
        self.content.setStyleSheet('font-size:16px;padding:2px;' if dense else '')
        self.log.setStyleSheet('font-size:11px;padding:4px;' if dense else '')
        self.phase.setVisible(not multirow);self.progress.setVisible(not multirow)
        self.phase.setText('ON STAGE · 대결 준비');self.progress.setValue(0)
        for index,(identity,name) in enumerate(agencies):
            if index:
                vs=QLabel('VS');vs.setAlignment(Qt.AlignmentFlag.AlignCenter)
                vs.setStyleSheet('font-size:42px;font-weight:900;color:#ff8bc8;padding:8px;');self.arena.addWidget(vs)
            panel=TeamPanel(identity,name,[p for p in people if p['agency_id']==identity],self.photos)
            self.arena.addWidget(panel,1);self.teams.append(panel)
            for card in panel.cards:card.profile_requested.connect(self.profile_requested)
            self.cards.update({card.person['id']:card for card in panel.cards})

    def show_frame(self,frame):
        sudden=frame.phase=='deathmatch'
        self.phase.setText(f'SUDDEN DEATH · 데스매치 {frame.round_number}차' if sudden else f'LIVE STAGE · 판정 {frame.tick}')
        self.phase.setStyleSheet('color:#ff90c9;font-size:16px;font-weight:bold;' if sudden else '')
        self.progress.setValue(60 if sudden else min(60,frame.tick))
        for card in self.cards.values():card.settle()
        for event in frame.events:
            self.shown_sequence=max(self.shown_sequence,event.sequence)
            card=self.cards.get(event.person_id)
            if card:card.show_event(event)
            if card:
                for panel in self.teams:
                    if panel.identity==card.person['agency_id']:panel.focus_person(event.person_id)
            name=card.person['name'] if card else event.person_id
            phase='리더 보너스' if event.phase=='leader' else '데스매치' if event.phase=='deathmatch' else ('주요 능력치 · ' if event.phase=='main' else '일반 능력치 · ')+SKILL_LABELS.get(event.skill,event.skill)
            self.logs.append(f'{name} · {phase} 판정 '+('성공 +1' if event.success else '실패'))
        self.log.setText(self.logs[-1] if self.logs else '')
        self._team_scores()

    def _team_scores(self):
        for panel in self.teams:
            bonus=sum(b['success'] for b in getattr(self,'teamwork',()) if b['agency_id']==panel.identity and b['after_sequence']<=self.shown_sequence)
            panel.total.setText(str(sum(card.successes for card in panel.cards)+bonus))
            panel.total.setToolTip(f'프랜차이즈 팀워크 +{bonus}점 · 개인 성공과 별도')

    def final_counts(self,counts,phase_counts=None):
        self.shown_sequence=float('inf')
        self.clear_animations()
        for identity,card in self.cards.items():
            card.successes=counts[identity]
            if phase_counts is not None:card.phase_successes=Counter(phase_counts.get(identity,{}))
            card.update_score();card.state.setText('경기 종료')
        self._team_scores();self.progress.setValue(60);self.phase.setText('STAGE COMPLETE · 최종 기록');self.phase.setStyleSheet('')

    def pause(self,paused):
        for card in self.cards.values():card.pause(paused)

    def clear_animations(self):
        for card in self.cards.values():card.settle()

    def refresh_photos(self):
        for card in self.cards.values():card.refresh_photo()
