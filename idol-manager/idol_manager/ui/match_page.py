from .table_widgets import QTableWidget
from .panel_splitter import PanelSplitter
from collections import Counter
from contextlib import closing
import json

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, QSize, Signal
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..game_clock import WEEKDAY_NAMES,GameDate
from ..match_replay import replay_frames
from ..match_types import MatchResult
from .draft_page import configure_table
from .battle_view import BattleView
from .thumbnails import ThumbnailCache

SKILL_NAMES = ('보컬','댄스','랩','예능','외모','신체','지성','리더십')
PHASE_NAMES = {'main':'주요 능력치','support':'일반 능력치','leader':'리더 추가','deathmatch':'데스매치'}
STATUS_NAMES = {'scheduled':'예정','in_progress':'준비 저장됨','completed':'완료'}


PROFILE_ROLE=Qt.ItemDataRole.UserRole+42


def fill_table(table, headers, rows, *, people=None, profile_columns=()):
    sorting = table.isSortingEnabled()
    blocked = table.signalsBlocked()
    table.blockSignals(True);table.setSortingEnabled(False)
    table.setColumnCount(len(headers));table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            item=QTableWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole,value)
            if people is not None and j in profile_columns:item.setData(PROFILE_ROLE,people[i])
            table.setItem(i,j,item)
    table.setSortingEnabled(sorting);table.blockSignals(blocked)


def make_table():
    table=QTableWidget();configure_table(table,32)
    table.setSortingEnabled(True)
    return table


class MatchSignals(QObject):
    finished=Signal(object,str)


class MatchJob(QRunnable):
    def __init__(self,matches,match_id=None,lineups=None):
        super().__init__()
        self.matches,self.match_id,self.lineups=matches,match_id,lineups
        self.signals=MatchSignals()

    def run(self):
        try:
            if self.match_id is not None:
                outcome=self.matches.play(self.match_id,lineups=self.lineups)
            else:
                outcome=[]
                requested_ids={f.id for f in self.matches.fixtures()}
                while True:
                    playable=[f for f in self.matches.fixtures() if f.status!='completed'
                              and f.id in requested_ids and not f.player_participates and not f.block_reason]
                    if not playable:break
                    identity=playable[0].id
                    self.matches.play(identity)
                    outcome.append(identity)
        except Exception as error:
            self.signals.finished.emit(None,str(error))
        else:
            self.signals.finished.emit(outcome,'')


class MatchPage(QWidget):
    busy_changed=Signal(bool)
    state_changed=Signal()
    battle_active_changed=Signal(bool)

    def __init__(self,service,thumbnails,parent=None):
        super().__init__(parent)
        self.service,self.matches,self.thumbnails=service,service.matches,thumbnails
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.job=None;self.replaying=False;self._external_busy=False;self._closing=False
        self.selection=None;self.current_result=None;self.result_match_id=None
        self.choices={}
        self.frames=();self.frame_index=0;self.live_counts=Counter();self.live_scores=Counter()
        self.paused=False;self.judgments_shown=0
        self.battle_photos=ThumbnailCache(service.image_root,service.cache_dir/'battle_thumbnails',self,image_size=QSize(360,480))
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.advance_frame)
        layout=QVBoxLayout(self);layout.setContentsMargins(26,18,26,18);layout.setSpacing(10)
        title=QLabel('정규 경기');title.setObjectName('title');layout.addWidget(title)
        self.notice=QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice)
        tools=QHBoxLayout()
        self.view_combo=QComboBox();self.view_combo.addItem('오늘 정규 경기',True);self.view_combo.addItem('저장된 경기 결과',False)
        self.view_combo.currentIndexChanged.connect(self.reload)
        self.reload_button=QPushButton('새로 불러오기');self.reload_button.clicked.connect(self.reload)
        self.ai_button=QPushButton('AI 경기 빠른 진행');self.ai_button.clicked.connect(self.run_ai)
        tools.addWidget(self.view_combo);tools.addWidget(self.reload_button);tools.addStretch();tools.addWidget(self.ai_button)
        layout.addLayout(tools)
        self.fixture_table=make_table();self.fixture_table.setMinimumHeight(110)
        self.fixture_table.itemSelectionChanged.connect(self.select_fixture)
        self.tabs=QTabWidget();self.tabs.setMinimumHeight(220)
        self.match_splitter=PanelSplitter(service.settings_dir/'ui_layout.ini',type(self).__name__+'/fixtures',self)
        self.match_splitter.addWidget(self.fixture_table);self.match_splitter.addWidget(self.tabs)
        self.match_splitter.setStretchFactor(0,1);self.match_splitter.setStretchFactor(1,2)
        layout.addWidget(self.match_splitter,1)

        selection_page=QWidget();choices=QVBoxLayout(selection_page)
        self.detail=QLabel('경기를 선택하세요.');self.detail.setWordWrap(True);choices.addWidget(self.detail)
        self.lineup_table=make_table();self.lineup_table.setIconSize(QSize(40,48));self.lineup_table.verticalHeader().setDefaultSectionSize(54)
        self.lineup_table.itemChanged.connect(self.lineup_changed);choices.addWidget(self.lineup_table,1)
        selection_controls=QHBoxLayout()
        self.selection_hint=QLabel();self.selection_hint.setWordWrap(True)
        self.start_button=QPushButton('경기 시작');self.start_button.clicked.connect(self.start_match)
        selection_controls.addWidget(self.selection_hint,1);selection_controls.addWidget(self.start_button)
        choices.addLayout(selection_controls)
        self.tabs.addTab(selection_page,'출전자 선택')

        replay_page=QWidget();replay=QVBoxLayout(replay_page)
        self.score_label=QLabel('0 : 0');self.score_label.setStyleSheet('font-size: 25px; font-weight: bold; padding: 12px;')
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        replay.addWidget(self.score_label)
        # Team scores are already shown in the stage. Keep this text for the
        # accessibility/test adapter without taking portrait space twice.
        self.score_label.hide()
        self.phase_label=QLabel();replay.addWidget(self.phase_label)
        self.progress=QProgressBar();replay.addWidget(self.progress)
        self.battle=BattleView(self.battle_photos);replay.addWidget(self.battle,1)
        self.live_table=make_table();self.live_table.setMaximumHeight(150);self.live_table.hide();replay.addWidget(self.live_table)
        replay_controls=QHBoxLayout()
        self.pause_button=QPushButton('일시정지');self.pause_button.clicked.connect(self.toggle_pause)
        self.details_button=QPushButton('상세 진행표');self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.live_table.setVisible)
        replay_controls.addWidget(self.pause_button);replay_controls.addWidget(self.details_button)
        self.skip_button=QPushButton('스킵 · 저장된 동일 결과 확인');self.skip_button.clicked.connect(self.skip)
        replay_controls.addWidget(self.skip_button);replay.addLayout(replay_controls);self.tabs.addTab(replay_page,'경기 진행')
        self.tabs.currentChanged.connect(self._replay_tab_changed)

        result_page=QWidget();result_layout=QVBoxLayout(result_page)
        self.result_summary=QLabel();self.result_summary.setWordWrap(True);self.result_summary.setObjectName('summary')
        result_layout.addWidget(self.result_summary)
        result_tabs=QTabWidget()
        self.records_table=make_table();self.abilities_table=make_table()
        result_tabs.addTab(self.records_table,'개인 기록');result_tabs.addTab(self.abilities_table,'능력치별 기록')
        result_layout.addWidget(result_tabs,1);self.tabs.addTab(result_page,'경기 결과')

        standings_page=QWidget();standing_layout=QVBoxLayout(standings_page)
        standing_layout.addWidget(QLabel('정규 승점 + 특별전 가감점 기준 · 동일 승점은 공동 순위로 표시합니다.'))
        self.standings_table=make_table();standing_layout.addWidget(self.standings_table,1)
        self.tabs.addTab(standings_page,'리그 순위')
        self.tabs.setTabEnabled(1,False);self.tabs.setTabEnabled(2,False)
        self.thumbnails.changed.connect(self._photos_changed)
        self.reload()

    def is_busy(self):
        return self.job is not None or self.replaying or self._external_busy

    def set_external_busy(self,busy):
        self._external_busy=busy;self.controls()

    def _busy_changed(self):
        self.controls();self.busy_changed.emit(self.is_busy())

    def reload(self,*_):
        if self.is_busy() or self._closing:return
        current=self.selection.fixture.id if self.selection else None
        self.fixtures=self.matches.fixtures(today_only=self.view_combo.currentData())
        rows=[]
        for f in self.fixtures:
            rows.append((f'시즌 {f.season} · {f.week}주 · {WEEKDAY_NAMES[f.weekday]}',f.day_order,
                         ' vs '.join(a[1] for a in f.agencies),f.content_name,f.required if f.required is not None else '미확정',
                         STATUS_NAMES.get(f.status,f.status),'플레이어' if f.player_participates else 'AI'))
        self.fixture_table.setSortingEnabled(False)
        fill_table(self.fixture_table,('경기 날짜','차수','참가 기획사','콘텐츠','필요 인원','상태','구분'),rows)
        for i,f in enumerate(self.fixtures):
            self.fixture_table.item(i,0).setData(Qt.ItemDataRole.UserRole,f.id)
        for col,width in enumerate((210,60,300,160,90,105,85)):self.fixture_table.setColumnWidth(col,width)
        self.fixture_table.setSortingEnabled(True)
        target=next((i for i in range(self.fixture_table.rowCount()) if self.fixture_table.item(i,0).data(Qt.ItemDataRole.UserRole)==current),0)
        if self.fixture_table.rowCount():self.fixture_table.setCurrentCell(target,0);self.select_fixture()
        else:
            self.selection=None;self.current_result=None;self.result_match_id=None
            self.tabs.setTabEnabled(1,False);self.tabs.setTabEnabled(2,False);self.tabs.setCurrentIndex(0)
            self.detail.setText('조회할 정규 경기가 없습니다.');self.lineup_table.setRowCount(0)
            self.controls()
        state=self.service.calendar.state()
        if self.view_combo.currentData():
            remaining=sum(f.status!='completed' for f in self.fixtures)
            self.notice.setText(f'{state.date or "게임 시작 전"} · 정규 {len(self.fixtures)}경기 · 미완료 {remaining}경기\n'
                +(state.advance_block_reason or ('당일 정규 경기를 모두 완료했습니다. 미처리 특별전이 없다면 하루 진행이 가능합니다.'
                   if self.fixtures and not remaining else '출전자 선택 후 경기를 시작하세요. 특별전은 자동 처리하지 않습니다.')))
        else:self.notice.setText('저장된 경기 결과를 선택해 확인할 수 있습니다. 결과를 다시 계산하지 않습니다.')
        self.refresh_standings()

    def select_fixture(self):
        if self.is_busy() or self._closing:return
        row=self.fixture_table.currentRow()
        if row<0 or self.fixture_table.item(row,0) is None:return
        identity=self.fixture_table.item(row,0).data(Qt.ItemDataRole.UserRole)
        try:selection=self.matches.selection(identity)
        except Exception as error:self._error(str(error));return
        self.selection=selection;f=selection.fixture
        if self.result_match_id != identity:
            self.current_result=None;self.tabs.setTabEnabled(1,False);self.tabs.setTabEnabled(2,False);self.tabs.setCurrentIndex(0)
        self.detail.setText(f'시즌 {f.season} · 정규 {f.week}주 · {WEEKDAY_NAMES[f.weekday]} · {f.day_order}차 경기\n'
            + ' vs '.join(a[1] for a in f.agencies)+f'\n{f.content_name} · 주요: {" / ".join(f.main_abilities)} · 양측 필요 인원: {f.required if f.required is not None else "미확정"}명'
            + ('\n'+f.block_reason if f.block_reason else ''))
        self.lineup_table.setSortingEnabled(False)
        rows=[]
        for p in selection.options:
            c=p.condition
            rows.append(('',p.player.name+(' · 1군 리더' if p.is_leader else ''),round(sum(p.player.skills)/8,1),*p.player.skills,p.player.health,
                         c.streak if c else 0,f'-{round(c.penalty*100)}%' if c else '0%',
                         '부상 · 출전 불가' if c and c.injured else '출전 가능',c.registration_weeks if c else 0))
        fill_table(self.lineup_table,('선택','이름','원본 평균',*SKILL_NAMES,'건강','연속 출전일','이번 경기 피로','상태','1군 등록 주차'),rows)
        self.lineup_table.blockSignals(True)
        for i,option in enumerate(selection.options):
            item=self.lineup_table.item(i,0);item.setData(Qt.ItemDataRole.UserRole,option.player.id)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|
                          (Qt.ItemFlag.ItemIsUserCheckable if selection.fixed_ids is None and option.available else Qt.ItemFlag.NoItemFlags))
            chosen=selection.fixed_ids if selection.fixed_ids is not None else self.choices.get(identity,())
            item.setCheckState(Qt.CheckState.Checked if option.player.id in chosen and option.available else Qt.CheckState.Unchecked)
            if option.condition:
                c=option.condition
                detail=f'원본 능력치는 유지됩니다. 이번 경기 유효 능력치 = 원본 × {1-c.penalty:.0%}. '
                detail+=f'이번 경기 포함 연속 {c.projected_days}일. 1군 등록 {c.registration_weeks}주. '
                detail+='부상 위험: 건강과 1군 등록 3주 이후 10배·20배… 적용. 하루 쉬면 피로 초기화.'
                if c.history_known_since>0:detail+=' 구버전의 과거 등록 이력은 확인 가능한 최소 주차부터 복원했습니다.'
                if c.injured:detail+=f' 회복 예정: {GameDate(c.recovery_day) if c.recovery_day is not None else "미정"}. 부상 중 출전할 수 없습니다.'
                for col in range(self.lineup_table.columnCount()):self.lineup_table.item(i,col).setToolTip(detail)
            self.lineup_table.item(i,1).setIcon(QIcon(self.thumbnails.get(option.photo_path)))
            self.lineup_table.setColumnWidth(1,210)
        for i,name in enumerate(SKILL_NAMES,3):
            if name in f.main_abilities:
                font=QFont();font.setBold(True);self.lineup_table.horizontalHeaderItem(i).setFont(font)
        self.lineup_table.blockSignals(False);self.lineup_table.setSortingEnabled(True)
        for col,width in enumerate((65,210,90,*([75]*8),75,110,120,150,120)):
            self.lineup_table.setColumnWidth(col,width)
        self.controls()

    def selected_ids(self):
        return tuple(self.lineup_table.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(self.lineup_table.rowCount())
                     if self.lineup_table.item(i,0).checkState()==Qt.CheckState.Checked)

    def lineup_changed(self,*_):
        if self.selection and self.selection.fixed_ids is None:
            self.choices[self.selection.fixture.id]=self.selected_ids()
        self.controls()

    def controls(self):
        if not hasattr(self,'start_button'):return
        busy=self.is_busy();selection=self.selection;f=selection.fixture if selection else None
        for widget in (self.fixture_table,self.lineup_table,self.view_combo,self.reload_button):widget.setEnabled(not busy)
        eligible_ai=any(not x.player_participates and x.status!='completed' and not x.block_reason for x in getattr(self,'fixtures',()))
        self.ai_button.setEnabled(not busy and bool(self.view_combo.currentData()) and eligible_ai)
        self.skip_button.setEnabled(self.replaying)
        self.pause_button.setEnabled(self.replaying)
        self.pause_button.setText('자동 진행 · 재개' if self.paused else '일시정지')
        self.start_button.setEnabled(False)
        if f is None:self.selection_hint.setText('오늘 경기 또는 저장된 결과를 선택하세요.');return
        self.start_button.setText('저장 결과 보기' if f.status=='completed' else ('저장된 경기 재개' if f.run_state else ('경기 시작' if f.player_participates else 'AI 경기 관전 시작')))
        if f.block_reason:self.selection_hint.setText(f.block_reason);return
        valid=True
        if f.status=='completed':self.selection_hint.setText('영구 저장된 결과를 불러옵니다.')
        elif f.player_participates:
            chosen=len(self.selected_ids());valid=chosen==selection.selection_count
            self.selection_hint.setText(f'등록 1군 {len(selection.options)}명 · 출전 가능 {sum(o.available for o in selection.options)}명 · 선택 {chosen} / {selection.selection_count}명'
                + (' · 저장된 출전자 명단으로 재개합니다.' if selection.fixed_ids is not None else '')
                + (' · 출전 가능 인원이 0명이므로 몰수패로 처리됩니다.' if selection.selection_count==0 else
                   (' · 출전 가능 인원이 부족하므로 가능한 인원으로 경기합니다.' if selection.selection_count<f.required else '')))
        else:self.selection_hint.setText('양측 기획사의 출전자는 기존 AI 정책으로 선정합니다.')
        self.start_button.setEnabled(not busy and valid)

    def start_match(self):
        if self.is_busy() or not self.selection:return
        f=self.selection.fixture
        if f.status=='completed':
            result=self.matches.result(f.id)
            if result is None:self._error('저장 결과를 찾을 수 없습니다.');return
            self._show_result(result);return
        if f.block_reason:self._error(f.block_reason);return
        lineups=None
        if f.player_participates and self.selection.fixed_ids is None:
            identities=self.selected_ids()
            if len(identities)!=self.selection.selection_count:
                self._error(f'출전 가능한 1군 중 정확히 {self.selection.selection_count}명을 선택해 주세요.');return
            lineups={f.player_agency_id:identities}
        self.job=MatchJob(self.matches,f.id,lineups);self.job.signals.finished.connect(self._finished)
        self.notice.setText('경기를 계산하고 저장하는 중입니다…');self._busy_changed();self.pool.start(self.job)

    def run_ai(self):
        if self.is_busy():return
        self.job=MatchJob(self.matches);self.job.signals.finished.connect(self._finished)
        self.notice.setText('진행 가능한 AI 경기를 차수 순서대로 저장하는 중입니다…');self._busy_changed();self.pool.start(self.job)

    def _finished(self,outcome,error):
        self.job=None
        if self._closing:return
        if error:
            self._busy_changed();self.reload();self.state_changed.emit();self._error(error);return
        if isinstance(outcome,MatchResult):
            self.current_result=outcome;self.result_match_id=outcome.match_id
            self.names=self.matches.result_names(outcome.match_id)
            self.frames=replay_frames(outcome);self.frame_index=0;self.live_counts=Counter();self.live_scores=Counter()
            self.paused=False;self.judgments_shown=0;self._configure_battle(outcome)
            self.progress.setRange(0,len(self.frames));self.progress.setValue(0)
            self.phase_label.setText(f'기본 판정 틱 0 / 60 · 개별 판정 0 / {len(outcome.events)} (리더·데스매치 포함)')
            self.notice.setText('판정 결과를 저장했습니다. 같은 이벤트를 0.5초 간격으로 관전합니다.')
            self.replaying=bool(self.frames);self.tabs.setTabEnabled(1,True);self.tabs.setCurrentIndex(1)
            self.battle_active_changed.emit(self.replaying)
            self.fixture_table.blockSignals(True)
            for row in range(self.fixture_table.rowCount()):
                if self.fixture_table.item(row,0).data(Qt.ItemDataRole.UserRole)==outcome.match_id:
                    self.fixture_table.item(row,5).setText('관전 중')
                    break
            self.fixture_table.blockSignals(False)
            self._busy_changed();self._render_live()
            if self.replaying:self.timer.start()
            else:self._finish_replay()
        else:
            self._busy_changed();self.reload();self.state_changed.emit()
            self.notice.setText(f'AI 경기 {len(outcome)}건 처리 완료. 플레이어 경기와 차수별 남은 경기를 확인하세요.')

    def advance_frame(self):
        if not self.replaying or self.paused or self.frame_index>=len(self.frames):return
        frame=self.frames[self.frame_index]
        for e in frame.events:
            self.live_counts[(e.person_id,e.phase,'attempts')]+=1
            self.live_counts[(e.person_id,e.phase,'successes')]+=int(e.success)
            self.live_scores[e.agency_id]+=int(e.success)
        self.judgments_shown+=len(frame.events);self.battle.show_frame(frame)
        for bonus in self.current_result.teamwork:
            if any(e.sequence==bonus['after_sequence'] for e in frame.events):self.live_scores[bonus['agency_id']]+=int(bonus['success'])
        self.frame_index+=1;self.progress.setValue(self.frame_index)
        self.phase_label.setText((f'기본 판정 틱 {frame.tick} / 60 · 리더 추가는 별도 판정'
                                if frame.phase=='regular' else f'데스매치 {frame.round_number}회차 · {frame.tick} / 10')
                                +f' · 개별 판정 {self.judgments_shown} / {len(self.current_result.events)}')
        self._render_live()
        if self.frame_index==len(self.frames):self._finish_replay()

    def _render_live(self):
        f=self.selection.fixture
        agencies=dict(f.agencies)
        order=[team.identity for team in self.battle.teams] or list(agencies)
        self.score_label.setText('   :   '.join(f'{agencies[identity]} {self.live_scores[identity]}' for identity in order))
        rows=[]
        for p in self.current_result.players:
            identity=p['person_id'];counts=self.live_counts
            rows.append((self.names.get(identity,identity),agencies[p['agency_id']],
                         sum(counts[(identity,phase,'attempts')] for phase in ('main','support')),
                         counts[(identity,'main','successes')],counts[(identity,'support','successes')],
                         counts[(identity,'leader','successes')],counts[(identity,'deathmatch','successes')]))
        fill_table(self.live_table,('선수','기획사','기본 시도','주요 능력치 성공','일반 능력치 성공','리더 추가 성공','데스매치 성공'),rows,people=[p['person_id'] for p in self.current_result.players],profile_columns=(0,))
        for col,width in enumerate((150,200,100,160,160,150,150)):self.live_table.setColumnWidth(col,width)

    def skip(self):
        if self.replaying:self._finish_replay()

    def _configure_battle(self,result):
        # Presentation reads the frozen leader selection, never today's leader.
        # It does not prepare, play or update a match and never reads potential.
        with closing(self.matches.database.connect()) as connection:
            row=connection.execute('SELECT input_json FROM match_runs WHERE match_id=?',(result.match_id,)).fetchone()
            leaders={t['agency_id']:t['leader_id'] for t in json.loads(row[0])['teams']} if row else {}
            ids=tuple(p['person_id'] for p in result.players)
            paths=dict(connection.execute('SELECT id,photo_path FROM people WHERE id IN ('+','.join('?' for _ in ids)+')',ids)) if ids else {}
        if hasattr(self.matches,'presentation'):leaders,paths=self.matches.presentation(result.match_id)
        from ..franchise import eligible,display_name
        with closing(self.matches.database.connect()) as connection:franchises=eligible(connection)
        people=[dict(id=p['person_id'],agency_id=p['agency_id'],name=self.names.get(p['person_id'],p['person_id']),
                     photo_path=paths.get(p['person_id'],''),leader=leaders.get(p['agency_id'])==p['person_id']) for p in result.players]
        fixture=self.selection.fixture;agencies=list(fixture.agencies)
        if agencies[-1][0]==fixture.player_agency_id:agencies.reverse()
        for person in people:person['name']=display_name(person['name'],person['id'] in franchises)
        self.battle.configure(f'시즌 {fixture.season} · 정규 {fixture.week}주 · {WEEKDAY_NAMES[fixture.weekday]} · {fixture.day_order}차 | {fixture.content_name}',agencies,people,result.teamwork)

    def toggle_pause(self):self.set_paused(not self.paused)

    def set_paused(self,paused):
        if not self.replaying:return
        self.paused=paused;self.battle.pause(paused)
        self.notice.setText('관전 일시정지 · 자동 진행 · 재개를 누르면 이어서 재생합니다.' if paused else '저장된 같은 판정 이벤트를 0.5초 간격으로 자동 재생합니다.')
        if paused:self.timer.stop()
        else:self.timer.start()
        self.controls()

    def _replay_tab_changed(self,index):
        # The stage needs room for portraits; the list returns on every other tab.
        if not hasattr(self.fixture_table,'dock_panel'):self.fixture_table.setVisible(index != 1)
        if index != 1:self.match_splitter.queue_restore()
        if index!=1 and self.replaying:self.set_paused(True)

    def hideEvent(self,event):
        if self.replaying:self.set_paused(True)
        super().hideEvent(event)

    def _finish_replay(self):
        self.timer.stop();self.replaying=False;self.paused=False
        self.battle_active_changed.emit(False)
        for frame in self.frames[self.frame_index:]:
            for e in frame.events:
                self.live_counts[(e.person_id,e.phase,'attempts')]+=1
                self.live_counts[(e.person_id,e.phase,'successes')]+=int(e.success)
                self.live_scores[e.agency_id]+=int(e.success)
        self.live_scores=Counter({t['agency_id']:t['total_score'] for t in self.current_result.teams})
        self.frame_index=len(self.frames);self.progress.setValue(len(self.frames));self._render_live()
        self.judgments_shown=len(self.current_result.events)
        self.battle.final_counts(Counter({p['person_id']:sum(self.live_counts[(p['person_id'],phase,'successes')] for phase in ('main','support','leader','deathmatch')) for p in self.current_result.players}),
            {p['person_id']:{phase:self.live_counts[(p['person_id'],phase,'successes')] for phase in ('main','support','leader','deathmatch')} for p in self.current_result.players})
        self.phase_label.setText(f'저장된 판정 이벤트 재생 완료 · {self.judgments_shown} / {self.judgments_shown}')
        result=self.current_result
        self._show_result(result);self._busy_changed();self.state_changed.emit()

    def _show_result(self,result):
        self.current_result=result;self.result_match_id=result.match_id
        names=self.matches.result_names(result.match_id);agencies=dict(self.selection.fixture.agencies)
        score=' / '.join(f"{agencies[t['agency_id']]} {t['total_score']}점 (정규 {t['base_score']} + 데스매치 {t['deathmatch_score']})" for t in result.teams)
        if result.resolution=='double_forfeit':outcome='양측 몰수패 · 양측 승점 0'
        else:outcome=f"승리: {agencies.get(result.winner_id,'없음')} (+1점) · 패배: {agencies.get(result.loser_id,'없음')}"
        bonus=' / '.join(f"{agencies[t['agency_id']]} 팀워크 +{t.get('teamwork_score',0)}" for t in result.teams)
        self.result_summary.setText(outcome+'\n'+score+'\n'+bonus+'\n'+{'normal':'일반 판정','deathmatch':'데스매치 승부','forfeit':'몰수패','double_forfeit':'실제 출전자 기록 없음'}[result.resolution])
        rows=[]
        phase_success=Counter((e.person_id,e.phase) for e in result.events if e.success)
        for p in result.players:
            rows.append((agencies[p['agency_id']],names.get(p['person_id'],p['person_id']),p['base_attempts'],p['main_attempts'],p['support_attempts'],
                phase_success[(p['person_id'],'main')],phase_success[(p['person_id'],'support')],p['base_failures'],f"{p['leader_successes']}/{p['leader_attempts']}",
                f"{p['deathmatch_successes']}/{p['deathmatch_attempts']}",f"{p['success_rate']*100:.1f}%",
                '승리 아이돌' if p['winning_idol'] else ('패배 아이돌' if p['losing_idol'] else '')))
        fill_table(self.records_table,('기획사','선수','기본 시도','주요 시도','일반 시도','주요 능력치 성공','일반 능력치 성공','기본 실패','리더 성공/시도','DM 성공/시도','전체 성공률','기록'),rows,people=[p['person_id'] for p in result.players],profile_columns=(1,))
        for col,width in enumerate((180,130,90,95,95,160,160,100,140,140,110,130)):self.records_table.setColumnWidth(col,width)
        counts=Counter((e.agency_id,e.person_id,e.phase,e.skill) for e in result.events)
        successes=Counter((e.agency_id,e.person_id,e.phase,e.skill) for e in result.events if e.success)
        skill_names=dict(zip(('vocal','dance','rap','entertainment','appearance','physique','intelligence','leadership'),SKILL_NAMES))
        ability_rows=[(agencies[a],names.get(p,p),PHASE_NAMES[phase],skill_names[skill],n,successes[(a,p,phase,skill)],n-successes[(a,p,phase,skill)])
                      for (a,p,phase,skill),n in counts.items()]
        fill_table(self.abilities_table,('기획사','선수','판정 구분','능력치','시도','성공','실패'),ability_rows,people=[p for a,p,phase,skill in counts],profile_columns=(1,))
        for col,width in enumerate((210,150,130,120,90,90,90)):self.abilities_table.setColumnWidth(col,width)
        self.tabs.setTabEnabled(2,True);self.tabs.setCurrentIndex(2)
        if self.view_combo.currentData() and not any(f.id==result.match_id for f in self.matches.fixtures()):
            self.view_combo.blockSignals(True);self.view_combo.setCurrentIndex(1);self.view_combo.blockSignals(False)
        self.reload();self.notice.setText('저장된 경기 결과입니다. 스킵과 관전은 같은 판정 기록을 사용합니다.')

    def refresh_standings(self):
        day=self.service.calendar.state().date
        season=self.selection.fixture.season if self.selection else (day.season if day else 1)
        records=self.matches.standings(season);point_counts=Counter(r['points'] for r in records)
        rows=[]
        for r in records:
            rank=1+sum(other['points']>r['points'] for other in records)
            rows.append((f'공동 {rank}' if point_counts[r['points']]>1 else str(rank),r['name'],r['played'],r['wins'],r['losses'],r['points'],r['regular_points'],r['special_points']))
        fill_table(self.standings_table,('순위','기획사','정규 경기','승','패','합계 승점','정규 승점','특별전 가감점'),rows)
        for col,width in enumerate((100,300,110,110,110,110)):self.standings_table.setColumnWidth(col,width)

    def _photos_changed(self):
        if self._closing or not self.selection:return
        options={o.player.id:o for o in self.selection.options}
        for row in range(self.lineup_table.rowCount()):
            identity=self.lineup_table.item(row,0).data(Qt.ItemDataRole.UserRole)
            if identity in options:self.lineup_table.item(row,1).setIcon(QIcon(self.thumbnails.get(options[identity].photo_path)))

    def _error(self,message):QMessageBox.warning(self,'정규 경기 안내',message)

    def shutdown(self):
        self._closing=True;self.timer.stop();self.replaying=False;self.battle.clear_animations()
        self.pool.waitForDone();self.job=None;self.battle_photos.close()
