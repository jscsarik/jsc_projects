"""Special stages use the same persisted-judgment replay model as regular games."""
from collections import Counter
from ..franchise import display_name
from contextlib import closing

from PySide6.QtCore import QObject,QRunnable,QThreadPool,QTimer,Qt,Signal,QSize
from PySide6.QtGui import QIcon,QBrush,QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
    QTabWidget,QProgressBar,QMessageBox)

from ..match_replay import replay_frames
from ..game_clock import regular_day
from .competition_progress import CompetitionProgress,show_table_region
from .panel_splitter import PanelSplitter
from .match_page import make_table,fill_table,SKILL_NAMES,PHASE_NAMES

STAGES={'upper':'상위 그룹 · 5자 대결','lower':'하위 그룹 · 5자 대결','final':'후속 4자 대결'}
STATES={'scheduled':'예정','in_progress':'진행 중','prepared':'준비 저장됨','completed':'완료','blocked':'판정 차단'}
KOREAN=dict(zip(('vocal','dance','rap','entertainment','appearance','physique','intelligence','leadership'),SKILL_NAMES))


class SpecialSignals(QObject):
    finished=Signal(object,str)


class SpecialJob(QRunnable):
    def __init__(self,service,identity,*,start=False,lineups=None):
        super().__init__();self.service=service;self.identity=identity;self.start=start;self.lineups=lineups
        self.signals=SpecialSignals()

    def run(self):
        try:
            outcome=self.service.start(self.identity) if self.start else self.service.play(self.identity,lineups=self.lineups)
        except Exception as error:self.signals.finished.emit(None,str(error))
        else:self.signals.finished.emit(outcome,'')


class SpecialPage(QWidget):
    state_changed=Signal()
    busy_changed=Signal(bool)
    battle_active_changed=Signal(bool)

    def __init__(self,service,thumbnails,parent=None):
        super().__init__(parent)
        self.service=service;self.specials=service.specials;self.thumbnails=thumbnails
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.job=None;self.replaying=False;self._external_busy=False;self._closing=False;self._loading=False
        self.current_round=None;self.current_result=None;self.selection=None;self.choices={}
        self.frames=();self.frame_index=0;self.scores=Counter();self.names={a.id:a.name for a in service.agencies()}
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance_frame)
        layout=QVBoxLayout(self);layout.setContentsMargins(26,18,26,18);layout.setSpacing(10)
        title=QLabel('특별전');title.setObjectName('title');layout.addWidget(title)
        self.notice=QLabel('특별전 일요일에 상위·하위 그룹과 후속 4자 대결을 진행합니다.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        controls=QHBoxLayout();self.event_combo=QComboBox();self.reload_button=QPushButton('결과 새로고침');self.open_button=QPushButton('그룹 편성 확정')
        self.current_button=QPushButton('현재 일정으로 이동');self.current_button.clicked.connect(self.go_current)
        controls.addWidget(self.current_button)
        self.stage_list_button=QPushButton('단계 목록');self.stage_list_button.setCheckable(True)
        self.stage_list_button.toggled.connect(lambda visible:self.round_table.setVisible(visible))
        controls.addWidget(self.stage_list_button)
        controls.addWidget(self.event_combo,1);controls.addWidget(self.reload_button);controls.addWidget(self.open_button);layout.addLayout(controls)
        self.event_combo.currentIndexChanged.connect(self.event_changed);self.reload_button.clicked.connect(self.reload);self.open_button.clicked.connect(self.open_event)
        self.group_label=QLabel();self.group_label.setWordWrap(True);layout.addWidget(self.group_label)
        self.stage_progress=CompetitionProgress();layout.addWidget(self.stage_progress)
        self._anchor_day=None
        self.round_table=make_table();self.round_table.setMinimumHeight(110);self.round_table.itemSelectionChanged.connect(self.select_round)
        self.round_table.hide()
        self.tabs=QTabWidget();self.tabs.setMinimumHeight(220)
        self.match_splitter=PanelSplitter(service.settings_dir/'ui_layout.ini','SpecialPage/rounds',self)
        self.match_splitter.addWidget(self.round_table);self.match_splitter.addWidget(self.tabs)
        self.match_splitter.setStretchFactor(0,1);self.match_splitter.setStretchFactor(1,2)
        layout.addWidget(self.match_splitter,1)

        page=QWidget();box=QVBoxLayout(page);self.detail=QLabel();self.detail.setWordWrap(True);box.addWidget(self.detail)
        self.lineup_table=make_table();self.lineup_table.setIconSize(QSize(36,42));self.lineup_table.verticalHeader().setDefaultSectionSize(46)
        self.lineup_table.itemChanged.connect(self.lineup_changed);box.addWidget(self.lineup_table,1)
        row=QHBoxLayout();self.hint=QLabel();self.hint.setWordWrap(True);self.start_button=QPushButton('대결 시작');self.start_button.clicked.connect(self.start_match)
        row.addWidget(self.hint,1);row.addWidget(self.start_button);box.addLayout(row);self.tabs.addTab(page,'출전자 선택')

        page=QWidget();box=QVBoxLayout(page);self.score_label=QLabel();self.score_label.setWordWrap(True);self.score_label.setObjectName('summary');box.addWidget(self.score_label)
        self.phase_label=QLabel();box.addWidget(self.phase_label);self.progress=QProgressBar();box.addWidget(self.progress)
        self.live_table=make_table();box.addWidget(self.live_table,1);self.skip_button=QPushButton('스킵 · 저장된 동일 결과 확인');self.skip_button.clicked.connect(self.skip);box.addWidget(self.skip_button)
        self.tabs.addTab(page,'경기 진행')

        page=QWidget();box=QVBoxLayout(page);self.result_label=QLabel();self.result_label.setWordWrap(True);box.addWidget(self.result_label)
        self.rank_table=make_table()
        self.record_tabs=QTabWidget();self.records_table=make_table();self.ability_table=make_table()
        self.record_tabs.addTab(self.records_table,'개인 기록');self.record_tabs.addTab(self.ability_table,'능력치별 기록');box.addWidget(self.record_tabs,1)
        self.record_tabs.addTab(self.rank_table,'단계 순위')
        self.summary_table=make_table();self.record_tabs.addTab(self.summary_table,'특별전 최종 정리 · 10개 기획사')
        self.tabs.addTab(page,'순위·선수 기록')

        page=QWidget();box=QVBoxLayout(page);box.addWidget(QLabel('정규 승점 + 특별전 가감점 · 정규 승패 기록은 그대로 유지됩니다.'))
        self.standings_table=make_table();box.addWidget(self.standings_table);self.tabs.addTab(page,'리그 순위')
        self.tabs.currentChanged.connect(lambda *_:self.battle_active_changed.emit(self.replaying))
        self.tabs.currentChanged.connect(self._resize_regions)
        self.tabs.setTabEnabled(1,False);self.tabs.setTabEnabled(2,False)
        self.thumbnails.changed.connect(self._photos_changed)
        self.reload()

    def _resize_regions(self,index):
        if not hasattr(self.round_table,'dock_panel'):self.round_table.setVisible(index != 1 and self.stage_list_button.isChecked())
        if index != 1:self.match_splitter.queue_restore()

    def is_busy(self):return self.job is not None or self.replaying or self._external_busy

    def set_external_busy(self,busy):self._external_busy=busy;self.controls()

    def go_current(self):
        if self.is_busy():return
        self._anchor_day=None;self.reload()

    def reload(self,*_):
        if self.is_busy() or self._closing:return
        old=self.event_combo.currentData();selected=self.current_round['id'] if self.current_round else None
        day=self.service.calendar.state().date
        changed=self._anchor_day is None or (day and self._anchor_day!=day.absolute_day)
        self._anchor_day=day.absolute_day if day else None
        self._loading=True;self.event_combo.clear()
        events=self.specials.events()
        for e in events:self.event_combo.addItem(f'시즌 {e["season"]} · 정규 {e["week"]}주 일요일 · {e["event_type"]} · {STATES[e["status"]]}',e['id'])
        today=next((e['id'] for e in events if e['today']),None)
        past=[e for e in events if day and regular_day(e['season'],e['week'],6)<=day.absolute_day]
        target=today or (past[-1]['id'] if past else events[0]['id'] if events else None)
        index=self.event_combo.findData(target if changed or old is None else old)
        self.event_combo.setCurrentIndex(max(0,index));self._loading=False;self.event_changed()
        if not changed and selected:self.choose_stage(selected)

    def event_changed(self,*_):
        if self._loading or self.is_busy():return
        event_id=self.event_combo.currentData()
        self.current_round=None;self.selection=None
        self.current_result=None;self.tabs.setTabEnabled(1,False);self.tabs.setTabEnabled(2,False);self.tabs.setCurrentIndex(0)
        if event_id is None:
            self.group_label.setText('특별전 일정이 없습니다. 새 게임의 기존 일정을 확인하세요.');fill_table(self.round_table,('단계',),());self.controls();return
        state=self.specials.state(event_id);self.event_state=state
        self.render_progress()
        sorting=self.round_table.isSortingEnabled();blocked=self.round_table.blockSignals(True)
        self.round_table.setSortingEnabled(False)
        fill_table(self.round_table,('단계','콘텐츠','필요 인원','참가 기획사','진행 상태'),
            [(STAGES[r['stage']],r['content_name'],r['required'],'\n'.join(self.names[a] for a in r['agencies']),STATES[r['status']]) for r in state['rounds']])
        for i,r in enumerate(state['rounds']):self.round_table.item(i,0).setData(Qt.ItemDataRole.UserRole,r['id'])
        self.round_table.setSortingEnabled(sorting);self.round_table.blockSignals(blocked)
        for i,width in enumerate((190,160,90,500,125)):self.round_table.setColumnWidth(i,width)
        target_id=next((r['id'] for r in state['rounds'] if r['status']!='completed'),state['rounds'][-1]['id'] if state['rounds'] else None)
        target=next((i for i in range(self.round_table.rowCount()) if self.round_table.item(i,0).data(Qt.ItemDataRole.UserRole)==target_id),0)
        if state['rounds']:self.round_table.setCurrentCell(target,0);self.select_round()
        else:
            fill_table(self.lineup_table,('선수',),());self.lineup_table.hide();self.tabs.setTabVisible(0,True)
            self.detail.setText('특별전 당일 그룹 편성을 확정한 뒤 출전자를 선택하세요.')
        self.refresh_standings();self.controls()

    def select_round(self):
        if self.is_busy() or self._loading:return
        row=self.round_table.currentRow()
        if row<0:return
        identity=self.round_table.item(row,0).data(Qt.ItemDataRole.UserRole)
        self.current_round=next(r for r in self.event_state['rounds'] if r['id']==identity)
        self.selection=self.specials.selection(identity);r=self.current_round
        if r['status']=='completed':
            show_table_region(self.lineup_table,False);self.tabs.setTabVisible(0,False)
            self.show_result(self.specials.result(identity));return
        self.tabs.setTabVisible(0,True);self.tabs.setCurrentIndex(0)
        event=next(e for e in self.specials.events() if e['id']==self.event_combo.currentData())
        show_table_region(self.lineup_table,event['today'] and self.selection['agency'] in r['agencies'])
        self.detail.setText(f'{STAGES[r["stage"]]} · {r["content_name"]} · 주요: {" / ".join(KOREAN[s] for s in r["main_skills"])} · 기획사별 필요 {r["required"]}명\n'
            + ('최초 10명 중 건강한 1군 우선 · 부족분은 최초 참가 2군. ' if r['stage']=='final' else '출전 가능한 소속 1군 우선 · 부족분은 2군. ')
            + f'선수당 주요 능력치 {r["base_attempts"]//2}회 + 일반 능력치 {r["base_attempts"]//2}회. 출전 리더 추가 판정: 1군 2회 / 2군 1회.')
        options=self.selection['options'];saved=self.selection['fixed']
        eligible_first=[o['player'].id for o in options if o['available'] and o['squad']=='first_team']
        mandatory=set(eligible_first) if len(eligible_first)<=self.selection['count'] else set()
        chosen=set(saved if saved is not None else self.choices.get(identity,mandatory))
        chosen=(chosen & {o['player'].id for o in options if o['available']}) | mandatory
        if saved is None and sum(o['available'] for o in options)<=self.selection['count']:chosen={o['player'].id for o in options if o['available']}
        self._loading=True
        sorting=self.lineup_table.isSortingEnabled();self.lineup_table.setSortingEnabled(False)
        fill_table(self.lineup_table,('선택','선수','소속','원본 평균','건강','연속 출전일','이번 경기 피로','상태','리더 추가'),[
            ('',display_name(o['player'].name,o['player'].franchise),'1군' if o['squad']=='first_team' else '2군',round(sum(o['player'].skills)/8,1),o['player'].health,
             o['condition']['streak'],f'-{round(o["condition"]["penalty"]*100)}%' if o['condition']['penalty'] else '0%', '출전 가능' if o['available'] else '부상 · 출전 불가',o['leader']) for o in options])
        self.lineup_table.blockSignals(True)
        for i,o in enumerate(options):
            p=o['player'];item=self.lineup_table.item(i,0);item.setData(Qt.ItemDataRole.UserRole,p.id)
            allowed=o['available'] and saved is None and p.id not in mandatory and not(o['squad']=='second_team' and len(eligible_first)>=self.selection['count'])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|(Qt.ItemFlag.ItemIsUserCheckable if allowed else Qt.ItemFlag.NoItemFlags))
            item.setCheckState(Qt.CheckState.Checked if p.id in chosen else Qt.CheckState.Unchecked)
            self.lineup_table.item(i,1).setIcon(QIcon(self.thumbnails.get(o['path'])))
            if not o['available']:
                for col in range(self.lineup_table.columnCount()):self.lineup_table.item(i,col).setForeground(QBrush(QColor('#949ba8')))
            item.setToolTip('원본 능력치는 유지하며 이번 경기 피로만 판정 확률에 적용합니다. 부상자는 선택할 수 없습니다. 1군 우선 선발은 필수입니다.')
        self.lineup_table.setSortingEnabled(sorting);self.lineup_table.blockSignals(False);self._loading=False
        for i,width in enumerate((65,210,70,95,80,110,120,160,90)):self.lineup_table.setColumnWidth(i,width)
        self.controls()

    def selected_ids(self):
        return tuple(self.lineup_table.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(self.lineup_table.rowCount()) if self.lineup_table.item(i,0).checkState()==Qt.CheckState.Checked)

    def lineup_changed(self,*_):
        if self._loading:return
        if self.current_round:self.choices[self.current_round['id']]=self.selected_ids()
        self.controls()

    def controls(self):
        if not hasattr(self,'start_button'):return
        busy=self.is_busy()
        for w in (self.event_combo,self.round_table,self.reload_button,self.lineup_table,self.current_button,self.stage_progress):w.setEnabled(not busy)
        event=next((e for e in self.specials.events() if e['id']==self.event_combo.currentData()),None)
        self.open_button.setEnabled(not busy and bool(event and event['today'] and event['status']=='scheduled'))
        self.start_button.setEnabled(False);self.skip_button.setEnabled(self.replaying)
        r=self.current_round
        if not r:self.hint.setText('특별전 당일 그룹을 확정하세요.');return
        if r['status']=='blocked':self.hint.setText(r['error']);return
        own=self.selection and self.selection['agency'] in r['agencies']
        self.start_button.setText('저장 결과 보기' if r['status']=='completed' else ('저장된 대결 재개' if r['status']=='prepared' else '경기 시작' if own else 'AI 경기 진행'))
        if r['status']=='completed':self.hint.setText('저장된 결과를 재조회합니다. 재계산하지 않습니다.');self.start_button.setEnabled(not busy);return
        if not event or not event['today']:self.hint.setText('현재 날짜의 특별전만 진행할 수 있습니다.');return
        selected=self.selected_ids();s=self.selection
        own=s and s['agency'] in r['agencies'];valid=True
        if own:
            first={o['player'].id for o in s['options'] if o['squad']=='first_team'}
            valid=len(selected)==s['count'] and len(set(selected)&first)==s['first_count']
            self.hint.setText(f'선택 {len(selected)} / {s["count"]}명 · 1군 {s["first_count"]}명 우선 · 결원은 가능한 인원만 참가합니다.')
        else:self.hint.setText('이번 대결에는 내 기획사가 참가하지 않습니다. AI 경기 진행을 눌러 주세요.')
        self.start_button.setEnabled(not busy and valid)

    def open_event(self):
        if self.is_busy():return
        self._run(SpecialJob(self.specials,self.event_combo.currentData(),start=True))

    def start_match(self):
        if self.is_busy() or not self.current_round:return
        r=self.current_round
        if r['status']=='completed':self.show_result(self.specials.result(r['id']));return
        if not self.start_button.isEnabled():return
        s=self.selection;lineups={s['agency']:self.selected_ids()} if s and s['agency'] in r['agencies'] and s['fixed'] is None else None
        self._run(SpecialJob(self.specials,r['id'],lineups=lineups))

    def _run(self,job):
        self.job=job;job.signals.finished.connect(self._finished);self.notice.setText('특별전 데이터를 계산·저장하는 중입니다…');self._busy();self.pool.start(job)

    def _finished(self,result,error):
        self.job=None
        if self._closing:return
        if error:
            self._busy();self.reload();self.notice.setText(error);self.state_changed.emit();QMessageBox.warning(self,'특별전 안내',error);return
        if result is None:
            self._busy();self.reload();self.notice.setText('상위·하위 그룹을 저장했습니다. 출전자를 선택해 각 대결을 시작하세요.');self.state_changed.emit();return
        self.current_result=result
        self.frames=replay_frames(result,base_attempts=self.current_round['base_attempts']);self.frame_index=0;self.scores=Counter()
        self.replaying=bool(self.frames);self.progress.setRange(0,len(self.frames));self.progress.setValue(0)
        self.timer.setInterval(500 if self.current_round['base_attempts']==30 else 250)
        self.tabs.setTabEnabled(1,True);self.tabs.setCurrentIndex(1)
        self.notice.setText('결과와 피로·부상·승점을 저장했습니다. 약 15초 동안 같은 판정 이벤트를 재생합니다.')
        self._busy();self._render_live()
        if self.replaying:self.timer.start()
        else:self._finish_replay()

    def _busy(self):self.controls();self.busy_changed.emit(self.is_busy());self.battle_active_changed.emit(self.replaying)

    def advance_frame(self):
        if not self.replaying or self.frame_index>=len(self.frames):return
        frame=self.frames[self.frame_index]
        for event in frame.events:self.scores[event.agency_id]+=int(event.success)
        for bonus in self.current_result.teamwork:
            if any(e.sequence==bonus['after_sequence'] for e in frame.events):self.scores[bonus['agency_id']]+=int(bonus['success'])
        self.frame_index+=1;self.progress.setValue(self.frame_index)
        self.phase_label.setText(f'기본 판정 {frame.tick} / {self.current_round["base_attempts"]}' if frame.phase=='regular' else f'동률 추가 판정 {frame.round_number}회차 · {frame.tick}/10')
        self._render_live()
        if self.frame_index==len(self.frames):self._finish_replay()

    def _render_live(self):
        agencies=self.current_round['agencies']
        self.score_label.setText(' / '.join(f'{self.names[a]} {self.scores[a]}회 성공' for a in agencies))
        phase_success=Counter((e.agency_id,e.phase) for f in self.frames[:self.frame_index] for e in f.events if e.success)
        fill_table(self.live_table,('기획사','주요 능력치 성공','일반 능력치 성공','리더 추가 성공','동률 추가 성공','전체 성공'),[(self.names[a],phase_success[(a,'main')],phase_success[(a,'support')],phase_success[(a,'leader')],phase_success[(a,'deathmatch')],self.scores[a]) for a in agencies])

    def skip(self):
        if not self.replaying:return
        self.scores=Counter({t['agency_id']:t['base_score']+t['tiebreak_score'] for t in self.current_result.teams})
        self.frame_index=len(self.frames);self.progress.setValue(self.frame_index);self._render_live();self._finish_replay()

    def _finish_replay(self):
        self.timer.stop();self.replaying=False;self._busy();self.show_result(self.current_result);self.state_changed.emit()

    def show_result(self,result):
        if result is None:return
        self.current_result=result
        event_id=self.event_combo.currentData();state=self.specials.state(event_id)
        self.event_state=state
        event=next(e for e in self.specials.events() if e['id']==event_id)
        self.event_combo.blockSignals(True)
        self.event_combo.setItemText(self.event_combo.currentIndex(),f'시즌 {event["season"]} · 정규 {event["week"]}주 일요일 · {event["event_type"]} · {STATES[event["status"]]}')
        self.event_combo.blockSignals(False)
        self.notice.setText('저장된 특별전 결과입니다. 다시 열거나 스킵해도 판정·승점은 중복 처리되지 않습니다.')
        with closing(self.service.database.connect()) as c:
            points={r[0]:r[1] for r in c.execute('SELECT agency_id,delta FROM special_points WHERE round_id=?',(result.round_id,))}
            names={r[0]:r[1] for r in c.execute('SELECT id,name FROM people')}
            total={r[0]:r[1] for r in c.execute('SELECT agency_id,SUM(delta) FROM special_points WHERE event_id=? GROUP BY agency_id',(event_id,))}
        fill_table(self.rank_table,('순위','기획사','기본·리더·팀워크','추가 판정 성공','단계 승점','몰수'),[(t['rank'],self.names[t['agency_id']],f"{t['base_score']} (팀워크 +{t.get('teamwork_score',0)})",t['tiebreak_score'],points.get(t['agency_id'],0),'몰수' if t['forfeit'] else '') for t in result.teams])
        for i,width in enumerate((70,240,160,150,110,90)):self.rank_table.setColumnWidth(i,width)
        phase_success=Counter((e.person_id,e.phase) for e in result.events if e.success)
        fill_table(self.records_table,('기획사','선수','기본 판정','주요 시도','일반 시도','주요 능력치 성공','일반 능력치 성공','기본 실패','리더 성공/시도','동률 성공/시도','성공률'),[
            (self.names[p['agency_id']],names.get(p['person_id'],p['person_id']),p['base_attempts'],p['main_attempts'],p['support_attempts'],phase_success[(p['person_id'],'main')],phase_success[(p['person_id'],'support')],p['base_failures'],f'{p["leader_successes"]}/{p["leader_attempts"]}',f'{p["deathmatch_successes"]}/{p["deathmatch_attempts"]}',f'{p["success_rate"]:.1%}') for p in result.players],people=[p['person_id'] for p in result.players],profile_columns=(1,))
        for i,width in enumerate((200,170,100,95,95,160,160,100,130,130,90)):self.records_table.setColumnWidth(i,width)
        counts=Counter((e.agency_id,e.person_id,e.phase,e.skill) for e in result.events);successes=Counter((e.agency_id,e.person_id,e.phase,e.skill) for e in result.events if e.success)
        fill_table(self.ability_table,('기획사','선수','판정','능력치','시도','성공','실패'),[(self.names[a],names[p],PHASE_NAMES[phase],KOREAN[skill],n,successes[(a,p,phase,skill)],n-successes[(a,p,phase,skill)]) for (a,p,phase,skill),n in counts.items()],people=[p for a,p,phase,skill in counts],profile_columns=(1,))
        for i,width in enumerate((210,160,120,100,90,90,90)):self.ability_table.setColumnWidth(i,width)
        follow=next((r for r in state['rounds'] if r['stage']=='final'),None)
        self.result_label.setText(('특별전 전체 완료. 다음 월요일로 진행할 수 있습니다.' if state['status']=='completed' else '저장 완료. 남은 단계를 계속 진행해 주세요.')
            + (' 단계 카드에서 참가 기획사와 순위를, 아래 표에서 실제 출전자·판정·승점을 확인하세요.' if follow else '\n상위·하위 그룹을 모두 완료하면 후속 대결이 확정됩니다.'))
        summary=self.specials.final_summary(event_id)
        fill_table(self.summary_table,('기획사','최초 그룹','그룹 최종 순위','후속 최종 순위','그룹 승점','후속 승점','총 가감점'),
            [(r['name'],'상위' if r['group']=='upper' else '하위',r['group_rank'] or '미완료',r['followup_rank'] or '—',r['group_points'],r['followup_points'],r['points']) for r in summary])
        for i,width in enumerate((230,90,130,130,110,110,110)):self.summary_table.setColumnWidth(i,width)
        self.record_tabs.setCurrentIndex(3 if state['status']=='completed' else 2)
        self.tabs.setTabEnabled(2,True);self.tabs.setCurrentIndex(2)
        # Refresh persisted stages without replacing the displayed result.
        self._loading=True
        sorting=self.round_table.isSortingEnabled();blocked=self.round_table.blockSignals(True)
        self.round_table.setSortingEnabled(False)
        fill_table(self.round_table,('단계','콘텐츠','필요 인원','참가 기획사','진행 상태'),[(STAGES[r['stage']],r['content_name'],r['required'],'\n'.join(self.names[a] for a in r['agencies']),STATES[r['status']]) for r in state['rounds']])
        selected=0
        for i,r in enumerate(state['rounds']):
            self.round_table.item(i,0).setData(Qt.ItemDataRole.UserRole,r['id'])
        self.round_table.setSortingEnabled(sorting);self.round_table.blockSignals(blocked)
        selected=next(i for i in range(self.round_table.rowCount()) if self.round_table.item(i,0).data(Qt.ItemDataRole.UserRole)==result.round_id)
        self.round_table.setCurrentCell(selected,0);self._loading=False
        self.current_round=next(r for r in state['rounds'] if r['id']==result.round_id)
        show_table_region(self.lineup_table,False);self.tabs.setTabVisible(0,False)
        self.render_progress()
        self.refresh_standings();self.controls()

    def choose_stage(self,identity):
        if self.is_busy():return
        for row in range(self.round_table.rowCount()):
            if self.round_table.item(row,0).data(Qt.ItemDataRole.UserRole)==identity:
                self.round_table.setCurrentCell(row,0);self.select_round();return

    def render_progress(self):
        day=self.service.calendar.state().date
        events=self.specials.events()
        event=next((e for e in events if e['id']==self.event_combo.currentData()),None)
        if not event:return
        when=regular_day(event['season'],event['week'],6)
        context='오늘의 특별전' if event['today'] else '지난 경기 결과 조회' if day and when<day.absolute_day else '다음 특별전 예정'
        upcoming=next((e for e in events if day and regular_day(e['season'],e['week'],6)>day.absolute_day),None)
        self.group_label.setText(f'현재 게임: {day}\n{context} · 시즌 {event["season"]} 정규 {event["week"]}주 일요일'
            +(f' · 다음 개최: 시즌 {upcoming["season"]} 정규 {upcoming["week"]}주 일요일' if upcoming else ''))
        cards=[]
        for key,title in STAGES.items():
            r=next((r for r in self.event_state['rounds'] if r['stage']==key),None)
            done=r and r['status']=='completed'
            result=self.specials.result(r['id']) if done else None
            body='\n'.join(f'{t["rank"]}위 {self.names[t["agency_id"]]}' for t in result.teams) if result else ('\n'.join(self.names[a] for a in r['agencies']) if r else '진출 기획사 미확정')
            cards.append(dict(title=('✓ ' if done else '')+title+' · '+('완료' if done else '진행 가능' if r and event['today'] and r['status']!='blocked' else '진행 예정'),body=body,
                active=bool(r and event['today'] and not done),button='경기 결과 보기' if done else '이 단계 선택',
                action=(lambda _=False,identity=r['id']:self.choose_stage(identity)) if r else None))
        cards.append(dict(title='✓ 최종 결과 확정' if self.event_state['status']=='completed' else '최종 결과 대기',body='저장된 승점·순위를 표시합니다.' if self.event_state['status']=='completed' else '세 단계를 완료해 주세요.'))
        self.stage_progress.update_cards(cards)

    def refresh_standings(self):
        event=next((e for e in self.specials.events() if e['id']==self.event_combo.currentData()),None)
        if not event:return
        rows=self.service.matches.standings(event['season'])
        fill_table(self.standings_table,('임시 순위','기획사','정규 경기 수','승','패','정규 승점','특별전 가감점','합계'),[(i+1,r['name'],r['played'],r['wins'],r['losses'],r['regular_points'],r['special_points'],r['points']) for i,r in enumerate(rows)])

    def _photos_changed(self):
        if self._closing or not self.selection:return
        options={o['player'].id:o for o in self.selection['options']}
        for i in range(self.lineup_table.rowCount()):
            identity=self.lineup_table.item(i,0).data(Qt.ItemDataRole.UserRole)
            if identity in options:self.lineup_table.item(i,1).setIcon(QIcon(self.thumbnails.get(options[identity]['path'])))

    def shutdown(self):
        self._closing=True;self.timer.stop();self.replaying=False;self.pool.waitForDone();self.job=None
