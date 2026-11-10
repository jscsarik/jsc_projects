"""Three-round pick window using shared public candidates and market offers."""
import uuid,sqlite3
from PySide6.QtCore import Qt,QTimer,QSize,Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QTabWidget,QSpinBox,QMessageBox
from .match_page import make_table,fill_table
from .battle_view import CardPhoto
from .thumbnails import ThumbnailCache
from ..config import SKILLS
from ..awards import LABELS
from ..market_rules import raised_offer,acceptance

STATUSES={'scheduled':'지명 대기','negotiating':'계약 협상','signed':'계약 완료','failed':'계약 실패'}


class AnnualDraftPage(QWidget):
    state_changed=Signal();profile_requested=Signal(str)
    def __init__(self,service):
        super().__init__();self.service=service;self.api=service.annual_draft;self.data=None;self.selected=None;self.busy=False;self._loading=False
        self.names={a.id:a.name for a in service.agencies()}
        self.photos=ThumbnailCache(service.image_root,service.cache_dir/'annual_thumbnails',self,image_size=QSize(300,400))
        self.timer=QTimer(self);self.timer.setInterval(180);self.timer.timeout.connect(self.ai_tick)
        layout=QVBoxLayout(self);layout.setContentsMargins(12,10,12,10)
        self.title=QLabel('통합 드래프트');self.title.setObjectName('title');layout.addWidget(self.title)
        self.notice=QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice)
        controls=QHBoxLayout();self.season=QComboBox();self.rescan_button=QPushButton('사진 추가 · 다시 스캔');self.start_button=QPushButton('3라운드 시작');self.auto=QPushButton('AI 다음 내 차례까지');self.auto.setCheckable(True)
        self.rescan_button.clicked.connect(self.rescan);self.start_button.clicked.connect(self.start);self.auto.clicked.connect(self.queue_ai)
        self.auto.setChecked(True)
        for w in (self.season,self.rescan_button,self.start_button,self.auto):controls.addWidget(w)
        layout.addLayout(controls);self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        candidates=QWidget();box=QVBoxLayout(candidates);self.search=QLineEdit();self.search.setPlaceholderText('후보 이름 검색');self.search.textChanged.connect(self.render_candidates);box.addWidget(self.search)
        row=QHBoxLayout();self.candidate_table=make_table();self.candidate_table.setIconSize(QSize(40,48));self.candidate_table.verticalHeader().setDefaultSectionSize(58)
        self.candidate_table.itemSelectionChanged.connect(self.select_candidate);row.addWidget(self.candidate_table,3)
        detail=QWidget();right=QVBoxLayout(detail);self.portrait=CardPhoto(230);right.addWidget(self.portrait,1)
        self.detail_label=QLabel('후보를 선택해 주세요.');self.detail_label.setWordWrap(True);right.addWidget(self.detail_label)
        profile=QPushButton('선택 선수 프로필');profile.clicked.connect(self.open_profile);self.portrait.clicked.connect(self.open_profile);right.addWidget(profile)
        self.registration=QComboBox();self.registration.addItem('프로 등록','pro');self.registration.addItem('연습생 등록 · 협상 연봉 유지','trainee');right.addWidget(self.registration)
        self.pick_button=QPushButton('지명 확정');self.pick_button.clicked.connect(self.pick);right.addWidget(self.pick_button);row.addWidget(detail,2);box.addLayout(row,1)
        self.tabs.addTab(candidates,'후보 선택')
        self.history_table=make_table();self.tabs.addTab(self.history_table,'30턴 · 지명 이력')
        self.order_table=make_table();self.tabs.addTab(self.order_table,'기획사별 지명')
        self.contract_notice=QLabel();self.contract_notice.setWordWrap(True);layout.addWidget(self.contract_notice)
        contract=QHBoxLayout();self.annual=QSpinBox();self.annual.setRange(3000,1000000);self.annual.setValue(3000);self.annual.setSuffix('만 원 / 연')
        self.duration=QSpinBox();self.duration.setRange(1,2);self.duration.setSuffix('시즌');self.offer_button=QPushButton('계약 제안 확정');self.offer_button.clicked.connect(self.offer)
        contract.addWidget(self.annual);contract.addWidget(self.duration);contract.addWidget(self.offer_button);layout.addLayout(contract)
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.season.currentIndexChanged.connect(self.reload)
        self.photos.changed.connect(self.refresh_photos)

    def showEvent(self,event):
        super().showEvent(event);self.reload()
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def shutdown(self):self.timer.stop();self.photos.close()

    def reload(self,*_):
        if self._loading:return
        self._loading=True
        try:
            selected=self.season.currentData();years=self.service.calendar.seasons();self.season.blockSignals(True);self.season.clear()
            for season in sorted(years,reverse=True):self.season.addItem(f'시즌 {season+1} 지명 · {season}년 비시즌',season)
            self.season.setCurrentIndex(max(0,self.season.findData(selected)));self.season.blockSignals(False)
            self.data=self.api.state(self.season.currentData());d=self.data;t=d['turn'];current=self.service.calendar.state().date
            active=bool(current and current.season==d['season'] and current.is_offseason and current.week==2)
            event=d['event'];session=d['session'];self.title.setText(f'시즌 {d["target_season"]} 통합 드래프트')
            next_turn=next((r for r in d['turns'] if t and r['pick_number']==t['pick_number']+1),None)
            if t:
                self.notice.setText(f'{t["round_number"]}/3라운드 · 전체 {t["pick_number"]}/30턴 · 현재 {self.names.get(t["agency_id"])} · 다음 {self.names.get(next_turn["agency_id"]) if next_turn else "없음"}\n남은 지명 {sum(r["status"] in ("scheduled","negotiating") for r in d["turns"])}회 · 남은 후보 {len(d["candidates"])}명 · 정규 역순/정순/역순')
            else:self.notice.setText('통합 드래프트 완료 · 결과 자동 저장' if session else event['issue'] if event and event['issue'] else '비시즌 1주차 신규 70명 · 2주차 3라운드 · 3주차 FA 시장. 창단 16라운드는 유지합니다.')
            if current and current.season<d['first_season']:self.notice.setText(f'기존 진행 보호: 시즌 {d["first_season"]} 종료 비시즌부터 신규 규칙을 적용합니다.')
            self.start_button.setEnabled(active and not session and bool(event and event['status']=='completed'))
            self.rescan_button.setEnabled(bool(current and current.season==d['season'] and current.is_offseason and current.week in (1,2)))
            own=bool(t and t['agency_id']==d['player'] and active)
            self._can_pick=own and t['status']=='scheduled'
            self.pick_button.setEnabled(own and t['status']=='scheduled');self.registration.setEnabled(own and t['status']=='scheduled');self.offer_button.setEnabled(own and t['status']=='negotiating')
            self.auto.setEnabled(bool(active and session and session['status']!='completed'))
            self.render_candidates()
            self.render_selected()
            fill_table(self.history_table,('순번','라운드','기획사','이름','지명 나이','계약 상태','계약 종류','지명 당시 공개','확정 게임 일'),
                [(r['pick_number'],r['round_number'],self.names.get(r['agency_id']),r['name'] or '미지명',r['picked_age'] or '—',STATUSES[r['status']],r['contract_kind'] or '—','정확 수치' if r['was_public'] else '추정 범위' if r['person_id'] else '—',r['completed_day'] if r['completed_day'] is not None else '—') for r in d['turns']],people=[r['person_id'] for r in d['turns']],profile_columns=(3,))
            fill_table(self.order_table,('기획사','행사한 지명권','계약 완료','계약 실패','지명 선수'),
                [(self.names[a.id],sum(r['agency_id']==a.id and r['person_id'] is not None for r in d['turns']),sum(r['agency_id']==a.id and r['status']=='signed' for r in d['turns']),sum(r['agency_id']==a.id and r['status']=='failed' for r in d['turns']),' / '.join(r['name'] for r in d['turns'] if r['agency_id']==a.id and r['name'])) for a in self.service.agencies()])
            n=d['negotiation']
            if n:
                offers=n['offers'];self.contract_notice.setText(f'{self.names.get(t["agency_id"])} · {t["pick_number"]}순위 연봉 계약 협상 · 제안 {len(offers)}/3회 · 세 번 거절되면 지명권 소모·FA 유지\n계약 성공 전에는 소속이 바뀌지 않습니다. 프로 등록 시 16명·2군 11명 제한, 연습생 등록 시 협상 연봉·계약기간을 유지합니다.')
                if offers:self.annual.setValue(raised_offer(offers[-1]['annual'])//10000)
                else:
                    candidates=self.service.market.public_people(available=True);p=next((p for p in candidates if p['id']==t['person_id']),None)
                    if p:self.annual.setValue((p['market'] or 30000000)//10000)
            else:self.contract_notice.setText('14~16세 신규 지명자는 연 2,000만 원 드래프트 연습생 자동 계약 · 프로 데뷔가 아닙니다.')
        finally:self._loading=False
        self.queue_ai()

    def render_candidates(self,*_):
        if not self.data:return
        query=self.search.text().casefold();self.visible_candidates=[p for p in self.data['candidates'] if query in p['name'].casefold()]
        rows=[]
        for p in self.visible_candidates:
            values=p['skills'] if p['exact'] else [f'{a}~{b}' for a,b in p['ranges']]
            average=f'{p["average"]:.1f}' if p['exact'] else f'{sum(r[0] for r in p["ranges"])/8:.1f}~{sum(r[1] for r in p["ranges"])/8:.1f}'
            rows.append(('',p['name'],p['age'],'신규 70명' if p['new'] else '기존 FA·미소속',average,*values))
        sorting=self.candidate_table.isSortingEnabled();self.candidate_table.setSortingEnabled(False)
        fill_table(self.candidate_table,('사진','이름','나이','구분','CA / 추정 CA',*[LABELS[s] for s in SKILLS]),rows,people=[p['id'] for p in self.visible_candidates],profile_columns=(0,1))
        for i,p in enumerate(self.visible_candidates):
            self.candidate_table.item(i,0).setData(Qt.ItemDataRole.UserRole,p['id']);self.candidate_table.item(i,0).setIcon(QIcon(self.photos.get(p['photo_path'] or '')))
        self.candidate_table.setSortingEnabled(sorting)
        if self.selected:
            row=next((i for i in range(self.candidate_table.rowCount()) if self.candidate_table.item(i,0).data(Qt.ItemDataRole.UserRole)==self.selected),None)
            if row is not None:self.candidate_table.setCurrentCell(row,0)

    def select_candidate(self):
        if self._loading:return
        if self.candidate_table.currentRow()<0:return
        item=self.candidate_table.item(self.candidate_table.currentRow(),0)
        if item is None:return
        self.selected=item.data(Qt.ItemDataRole.UserRole)
        self.render_selected()

    def render_selected(self):
        p=next((p for p in self.data['candidates'] if p['id']==self.selected),None) if self.data else None
        if p is None and self.selected:p=self.api.person(self.selected)
        eligible=bool(self.data and any(c['id']==self.selected for c in self.data['candidates']))
        self.pick_button.setEnabled(bool(getattr(self,'_can_pick',False) and eligible))
        if not p:return
        prior=p.get('debut_season') is not None
        self.registration.model().item(1).setEnabled(not prior)
        if prior:self.registration.setCurrentIndex(0)
        self.registration.setToolTip('기존 프로 경력자는 연습생으로 되돌릴 수 없습니다.' if prior else '계약 성공 시 선택한 신분으로 등록합니다. 연습생도 협상한 연봉을 지급합니다.')
        values=[str(v) for v in p['skills']] if p['exact'] else [f'{a}~{b}' for a,b in p['ranges']]
        ca=f'{p["average"]:.1f}' if p['exact'] else f'{sum(r[0] for r in p["ranges"])/8:.1f}~{sum(r[1] for r in p["ranges"])/8:.1f}'
        self.detail_label.setText(f'{p["name"]} · {p["age"]}세\n'+('공개 현재 능력치' if p['exact'] else '저장된 5칸 추정 범위')+f' · CA {ca}\n'+'\n'.join(f'{LABELS[s]} {v}' for s,v in zip(SKILLS,values))+f'\n상태: {p["career_status"]}\n이전 기획사: {self.names.get(p["last_agency"],"없음")}')
        self.portrait.set_photo(self.photos.get(p['photo_path'] or ''))

    def open_profile(self):
        if self.selected:self.profile_requested.emit(self.selected)
    def refresh_photos(self):self.select_candidate()
    def action(self,fn):
        if self.busy:return
        self.busy=True
        try:fn();self.message.setText('저장했습니다.');self.state_changed.emit()
        except (ValueError,RuntimeError,OSError,sqlite3.Error) as error:
            self.auto.setChecked(False);self.timer.stop();self.message.setText(str(error));QMessageBox.warning(self,'통합 드래프트',str(error))
        finally:self.busy=False;self.reload()
    def rescan(self):self.action(self.api.rescan)
    def start(self):self.action(self.api.start)
    def pick(self):
        if not self.selected or not self.data or not self.data['turn']:return
        p=next((p for p in self.data['candidates'] if p['id']==self.selected),None)
        if p and QMessageBox.question(self,'지명 확정',p['name']+' 선수를 지명할까요? 확정 후 선수 변경은 불가능합니다.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            t=self.data['turn'];self.action(lambda:self.api.pick(self.data['player'],p['id'],expected_pick=t['pick_number'],registration=self.registration.currentData()))
    def offer(self):
        if not self.data or not self.data['turn']:return
        if QMessageBox.question(self,'계약 제안',f'연 {self.annual.value():,}만 원 · {self.duration.value()}시즌을 제안할까요?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            t=self.data['turn'];self.action(lambda:self.api.offer(self.data['player'],self.annual.value()*10000,self.duration.value(),expected_pick=t['pick_number'],request_id=str(uuid.uuid4())))
    def queue_ai(self,*_):
        t=self.data['turn'] if self.data else None
        if self.isVisible() and self.auto.isChecked() and self.auto.isEnabled() and t and t['agency_id']!=self.data['player'] and not self.busy:self.timer.start()
        else:self.timer.stop()
    def ai_tick(self):
        if self.busy or not self.isVisible():return
        self.action(self.api.ai_step)
