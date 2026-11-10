"""Seven market workspaces; all writes are explicit confirmed facade calls."""
import json,uuid,sqlite3
from PySide6.QtCore import Qt,QSize,Signal,QTimer
from PySide6.QtGui import QIcon,QColor,QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTabWidget,
 QSpinBox,QMessageBox,QListWidget,QListWidgetItem,QAbstractItemView,QLineEdit,QSizePolicy)
from ..market_rules import acceptance,raised_offer
from ..game_clock import GameDate
from .match_page import make_table,fill_table,PROFILE_ROLE,SKILL_NAMES
from .finance_page import manwon
from .battle_view import CardPhoto
from .profile_explorer import SortItem

STATE={'open':'진행 중','accepted':'계약 수락','failed':'실패','abandoned':'포기','proposed':'제안','countered':'역제안','accepted_pending':'합의 · 월요일 대기','completed':'완료','rejected':'거절','void':'실행 불가'}
ROLES={'first_team':'1군','second_team':'2군','pro_pending':'편성 전','trainee':'연습생','fa':'FA','unassigned':'신규 후보','retired':'은퇴'}
STATE['expired']='기한 만료'
class MarketPage(QWidget):
    state_changed=Signal()
    profile_requested=Signal(str)
    def __init__(self,service,thumbnails,parent=None):
        super().__init__(parent);self.service=service;self.photos=thumbnails;self._loading=False
        layout=QVBoxLayout(self);layout.setContentsMargins(16,10,16,10);title=QLabel('선수 시장');title.setObjectName('title');layout.addWidget(title)
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        views=QHBoxLayout();views.addWidget(QLabel('선수 표 보기'));self.people_view=QComboBox()
        self.people_view.addItem('능력치 · 사진 크게','abilities');self.people_view.addItem('계약 · 입찰 정보','contracts')
        self.people_view.currentIndexChanged.connect(self.apply_people_view);views.addWidget(self.people_view)
        hint=QLabel('후보는 추정 범위만 표시 · 이름 클릭: 상세 프로필');hint.setWordWrap(True);views.addWidget(hint,1);layout.addLayout(views)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.fa_table=make_table();fa=QWidget();box=QVBoxLayout(fa);box.addWidget(self.fa_table,1)
        controls=QHBoxLayout();self.bid_amount=self.amount();self.bid_duration=self.duration();bid=QPushButton('공개 입찰 확정');bid.clicked.connect(self.bid)
        direct=QPushButton('선택 선수 직접 협상');direct.clicked.connect(self.start_fa_selected)
        self.bid_button=bid;self.direct_button=direct
        for w in (QLabel('연봉(만원)'),self.bid_amount,QLabel('계약 시즌'),self.bid_duration,bid,direct):controls.addWidget(w)
        box.addLayout(controls);self.tabs.addTab(fa,'FA 시장')
        negotiation=QWidget();box=QVBoxLayout(negotiation)
        controls=QHBoxLayout();self.person=QComboBox();self.purpose=QComboBox()
        for name,value in (('창단 상위 지명 계약','founding'),('FA 직접 협상','fa'),('재계약','renew'),('프로 데뷔','debut')):self.purpose.addItem(name,value)
        self.purpose.setCurrentIndex(self.purpose.findData('fa'))
        start=QPushButton('협상 열기');start.clicked.connect(self.start_negotiation)
        self.start_button=start
        for w in (self.person,self.purpose,start):controls.addWidget(w)
        box.addLayout(controls);self.negotiation_table=make_table();box.addWidget(self.negotiation_table,1)
        controls=QHBoxLayout();self.offer_amount=self.amount();self.offer_duration=self.duration();self.chance=QLabel();offer=QPushButton('계약 제안 확정');self.offer_button=offer;offer.clicked.connect(self.offer);abandon=QPushButton('협상 포기');abandon.clicked.connect(self.abandon)
        for w in (QLabel('연봉(만원)'),self.offer_amount,self.offer_duration,self.chance,offer,abandon):controls.addWidget(w)
        box.addLayout(controls);self.tabs.addTab(negotiation,'계약 협상')
        trade=QWidget();box=QVBoxLayout(trade);self.other=QComboBox();box.addWidget(self.other)
        self.trade_lineups=QWidget();self.trade_lineups.setMinimumHeight(238)
        self.trade_lineups.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Minimum)
        row=QHBoxLayout(self.trade_lineups);row.setContentsMargins(0,0,0,0);row.setSpacing(10)
        self.pro_a=QComboBox();self.pro_b=QComboBox()
        self.photo_a=CardPhoto(120);self.photo_b=CardPhoto(120);self.photo_a.clicked.connect(lambda:self.profile_requested.emit(self.pro_a.currentData()) if self.pro_a.currentData() else None);self.photo_b.clicked.connect(lambda:self.profile_requested.emit(self.pro_b.currentData()) if self.pro_b.currentData() else None);self.photo_a.setFixedSize(96,120);self.photo_b.setFixedSize(96,120)
        for photo in (self.photo_a,self.photo_b):photo.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.extra_a=QListWidget();self.extra_b=QListWidget()
        self.trade_summary_a=QLabel();self.trade_summary_b=QLabel()
        for summary in (self.trade_summary_a,self.trade_summary_b):summary.setWordWrap(True)
        for items in (self.extra_a,self.extra_b):
            items.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection);items.setMinimumHeight(50);items.setMaximumHeight(70)
        for index,(pro,photo,extra,caption) in enumerate(((self.pro_a,self.photo_a,self.extra_a,'보내는 선수'),(self.pro_b,self.photo_b,self.extra_b,'받는 선수'))):
            if index:
                mark=QLabel('↔');mark.setStyleSheet('font-size:26px;font-weight:bold;color:#9766b1;');row.addWidget(mark)
            card=QWidget();card.setMinimumHeight(150);column=QVBoxLayout(card);column.setContentsMargins(4,2,4,2);column.setSpacing(4)
            column.addWidget(QLabel(caption));body=QHBoxLayout();body.setSpacing(10)
            body.addWidget(photo,0,Qt.AlignmentFlag.AlignVCenter)
            fields=QVBoxLayout();fields.setSpacing(4);fields.addWidget(pro)
            fields.addWidget(self.trade_summary_a if index==0 else self.trade_summary_b)
            body.addLayout(fields,1);column.addLayout(body)
            column.addWidget(QLabel('추가 연습생 · 최대 3명 (선택 사항)'));column.addWidget(extra)
            row.addWidget(card,1)
        box.addWidget(self.trade_lineups)
        self.trade_detail=QLabel();self.trade_detail.setWordWrap(True);self.trade_detail.hide();box.addWidget(self.trade_detail)
        controls=QHBoxLayout();self.trade_cash=self.amount(signed=True);send=QPushButton('트레이드 제안');send.clicked.connect(self.send_trade)
        self.trade_send_button=send;self.trade_reply_buttons=[]
        controls.addWidget(QLabel('보상 현금(만원, +우리→상대 / -상대→우리)'));controls.addWidget(self.trade_cash);controls.addWidget(send);box.addLayout(controls)
        self.trade_table=make_table();self.trade_table.setProperty('balancedCompanyColumns',True);self.trade_table._default_row_height=64;self.trade_table.setIconSize(QSize(40,52));box.addWidget(self.trade_table,1);controls=QHBoxLayout()
        for label,action in (('제안 수락','accept'),('제안 거절','reject'),('현재 구성으로 역제안','counter')):
            button=QPushButton(label);button.clicked.connect(lambda _,a=action:self.reply_trade(a));controls.addWidget(button)
            self.trade_reply_buttons.append(button)
        box.addLayout(controls);self.tabs.addTab(trade,'트레이드')
        self.renew_table=make_table();renew_page=QWidget();renew_layout=QVBoxLayout(renew_page)
        renew_tools=QHBoxLayout();self.renew_all_button=QPushButton('전체 선택');self.renew_clear_button=QPushButton('선택 해제');self.renew_count=QLabel('선택 0명')
        self.renew_all_button.clicked.connect(lambda:self.check_renew_all(True));self.renew_clear_button.clicked.connect(lambda:self.check_renew_all(False))
        renew_tools.addWidget(self.renew_all_button);renew_tools.addWidget(self.renew_clear_button);renew_tools.addWidget(self.renew_count);renew_tools.addStretch();renew_layout.addLayout(renew_tools)
        renew_layout.addWidget(self.renew_table,1);renew_button=QPushButton('선택 선수 재계약 협상');renew_button.clicked.connect(self.start_renew_selected);renew_layout.addWidget(renew_button);self.tabs.addTab(renew_page,'재계약')
        release=QWidget();box=QVBoxLayout(release);self.release_table=make_table();box.addWidget(self.release_table,1);controls=QHBoxLayout();self.release_method=QComboBox();self.release_method.addItem('즉시 일시불','immediate');self.release_method.addItem('다음 월요일부터 10주 분할','installments');release_button=QPushButton('선택 선수 방출');release_button.clicked.connect(self.release)
        force=QPushButton('채무 강제 매각 실행');force.clicked.connect(self.force_sale)
        self.renew_button=renew_button;self.release_button=release_button;self.force_button=force;self.abandon_button=abandon
        for w in (self.release_method,release_button,force):controls.addWidget(w)
        box.addLayout(controls);self.tabs.addTab(release,'방출')
        trainee=QWidget();box=QVBoxLayout(trainee);self.trainee_table=make_table();box.addWidget(self.trainee_table,1);controls=QHBoxLayout()
        self.trainee_status=QLabel();self.trainee_status.setWordWrap(True);box.insertWidget(0,self.trainee_status)
        recruit=QPushButton('이번 회차 신청 추가');self.recruit_button=recruit;recruit.clicked.connect(self.recruit)
        remove=QPushButton('선택 후보 신청 취소');self.remove_application_button=remove;remove.clicked.connect(self.remove_application)
        clear=QPushButton('신청 전체 취소');self.clear_application_button=clear;clear.clicked.connect(lambda:self.action('신청 전체 취소',lambda:self.service.recruitment.apply(self.agency(),(),expected_revision=self.service.recruitment.state(self.agency())['revision'])))
        results=QPushButton('마감 결과 확인');results.clicked.connect(self.show_recruitment_results)
        debut=QPushButton('선택 연습생 데뷔 협상');debut.clicked.connect(self.debut)
        self.debut_button=debut
        controls.addWidget(recruit);controls.addWidget(remove);controls.addWidget(clear);controls.addWidget(results);controls.addWidget(debut);box.addLayout(controls);self.tabs.addTab(trainee,'연습생 영입·데뷔')
        self.history_table=make_table();self.tabs.addTab(self.history_table,'거래 기록')
        self.negotiation_table.itemSelectionChanged.connect(self.select_negotiation)
        self.purpose.currentIndexChanged.connect(self.update_actions)
        self.offer_amount.valueChanged.connect(self.preview);self.person.currentIndexChanged.connect(self.preview)
        self.other.currentIndexChanged.connect(self.trade_people);self.pro_a.currentIndexChanged.connect(self.trade_preview);self.pro_b.currentIndexChanged.connect(self.trade_preview)
        self.renew_table.itemSelectionChanged.connect(self.select_renew)
        self.renew_table.itemChanged.connect(self.renew_checked)
        self.trade_table.itemSelectionChanged.connect(self.select_trade)
        self.photo_refresh_timer=QTimer(self);self.photo_refresh_timer.setSingleShot(True);self.photo_refresh_timer.setInterval(40)
        self.photo_refresh_timer.timeout.connect(self.refresh_market_photos)
        self.photos.changed.connect(self.queue_market_photos)
        self.negotiation_id=None
    def amount(self,signed=False):
        box=QSpinBox();box.setRange(-1000000 if signed else 1,1000000);box.setValue(0 if signed else 3000);box.setSingleStep(10);return box
    def duration(self):box=QSpinBox();box.setRange(1,2);box.setSuffix('시즌');return box
    def showEvent(self,event):super().showEvent(event);self.reload()
    def agency(self):
        agency=self.service.draft_session.player_agency()
        if agency is None:raise ValueError('플레이어 기획사를 먼저 선택해 주세요.')
        return agency
    def selected(self,table):
        row=table.currentRow()
        if row<0 or table.item(row,0) is None:raise ValueError('선수를 먼저 선택해 주세요.')
        return table.item(row,0).data(Qt.ItemDataRole.UserRole)
    def action(self,label,fn):
        try:
            answer=QMessageBox.question(self,label,label+'을 실행하시겠습니까? 실제 계약·소속·장부에 저장됩니다.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
            result=fn();self.reload();self.state_changed.emit();QMessageBox.information(self,label,STATE.get(result,result) if isinstance(result,str) else '처리를 저장했습니다. 결과와 기록을 확인해 주세요.')
        except (ValueError,RuntimeError,OSError,sqlite3.Error) as error:QMessageBox.warning(self,label,str(error))
    def table_people(self,table,people):
        renewal=table is self.renew_table
        checked=set(self.checked_renew_ids()) if renewal else set()
        values=[]
        for p in people:
            estimate=(f'{sum(r[0] for r in p["ranges"])/8:.1f}~{sum(r[1] for r in p["ranges"])/8:.1f}' if all(p['ranges']) else '미공개') if not p['exact'] else round(p['average'],1)
            highest=self.auctions_by_person.get(p['id']);bids=highest['bids'] if highest else []
            top=max((b['annual'] for b in bids),default=0)
            teams=' / '.join(self.names.get(b['agency_id'],b['agency_id']) for b in bids if b['annual']==top)
            values.append(('',p['name'],p['age'],ROLES.get(p['career_status'],p['career_status']),self.names.get(p['agency_id'] or p['last_agency'],'—'),estimate,
                ('추정 ' if not p['exact'] else '')+manwon(p['market']) if p['market'] else '프로 데뷔 3,000',manwon(p['annual']),p['end_season'] or '미정',
                '부상' if p['injured'] else '정상' if p['exact'] else '미공개',manwon(top),teams or '없음',(str(GameDate(highest['deadline']))+f' · {max(0,highest["deadline"]-self.current_day)}일') if highest else '미개설',STATE.get(highest['status'],highest['status'])+(' · '+self.names.get(highest['winner'],highest['winner']) if highest['winner'] else '') if highest else '미개설',
                *[p['skills'][i] if p['exact'] else f'{p["ranges"][i][0]}~{p["ranges"][i][1]}' if p['ranges'][i] else '미공개' for i in range(8)],p['health'] if p['exact'] else '미공개'))
        table.setSortingEnabled(False)
        fill_table(table,('선택·사진' if renewal else '사진','이름','나이','신분','소속·이전 팀','평균 / 추정 평균','기준 연봉(만원)','계약 연봉(만원)','종료 시즌','부상','최고 입찰(만원)','최고 입찰 팀','입찰 종료','낙찰 상태',*SKILL_NAMES,'건강'),values,people=[p['id'] for p in people],profile_columns=(1,) if renewal else (0,1))
        table.setSortingEnabled(False)
        for i,p in enumerate(people):
            table.item(i,0).setData(Qt.ItemDataRole.UserRole,p['id']);table.item(i,0).setIcon(QIcon(self.photos.get(p['photo_path'])))
            if renewal:
                item=table.item(i,0);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if p['id'] in checked else Qt.CheckState.Unchecked)
                item.setToolTip('재계약할 선수를 체크하세요. 이름을 클릭하면 상세 프로필을 엽니다.')
            for column in (5,*range(14,23)):
                previous=table.takeItem(i,column);item=SortItem();item.setData(Qt.ItemDataRole.DisplayRole,previous.data(Qt.ItemDataRole.DisplayRole));table.setItem(i,column,item)
                if column==5:item.setData(Qt.ItemDataRole.UserRole+1,p['average'])
                elif column<22:item.setData(Qt.ItemDataRole.UserRole+1,p['skills'][column-14])
                font=QFont();font.setPixelSize(15);font.setBold(True);item.setFont(font)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if p['exact'] and column>=14:
                    value=p['skills'][column-14] if column<22 else p['health']
                    item.setForeground(QColor('#24745a' if value>=80 else '#345b85' if value>=60 else '#685673'))
        self.style_people_table(table)
        table.setSortingEnabled(True)

    def style_people_table(self,table):
        table.setProperty('balancedCompanyColumns',True)
        table._default_row_height=64
        table.setIconSize(QSize(46,56));table.verticalHeader().setDefaultSectionSize(64)
        for row in range(table.rowCount()):table.setRowHeight(row,64)
        table.setStyleSheet('QTableView {font-size:14px;} QHeaderView::section {font-size:13px;padding:8px;}')
        widths={0:72,1:135,2:60,3:88,4:140,5:125,6:120,7:120,8:90,9:80,10:125,11:160,12:220,13:115}
        for column in range(table.columnCount()):table.setColumnWidth(column,widths.get(column,76))
        visible=set(range(6))|set(range(14,23)) if self.people_view.currentData()=='abilities' else set(range(14))
        hidden=set(range(table.columnCount()))-visible
        controller=getattr(self.window(),'portrait_layout',None);pager=controller.tables.get(table) if controller else None
        if pager and pager.enabled:
            pager.original_columns=hidden;pager.column_page=0;pager.signature=None;pager.revision+=1;pager.queue()
        else:
            for c in range(table.columnCount()):table.setColumnHidden(c,c in hidden)

    def apply_people_view(self,*_):
        for name in ('fa_table','renew_table','release_table','trainee_table'):
            table=getattr(self,name,None)
            if table is not None:self.style_people_table(table)
    def reload(self):
        self._loading=True
        try:
            agency=self.service.draft_session.player_agency();self.people=self.service.market.public_people();self.by_id={p['id']:p for p in self.people};self.names={a.id:a.name for a in self.service.agencies()}
            auctions=self.service.market.auctions();self.auctions_by_person={}
            for a in auctions:self.auctions_by_person.setdefault(a['person_id'],a)
            day=self.service.calendar.state().date;self.current_day=day.absolute_day if day else 0
            self.info.setText(f'{day} · {self.names.get(agency,"플레이어 미선택")} · 표 금액: 만원\n미지명 후보는 추정 범위, 지명·소속 이력이 있는 선수는 공개 현재 능력치를 표시합니다.')
            own=[p for p in self.people if p['agency_id']==agency] if agency else []
            first=sum(p['career_status']=='first_team' for p in own);second=sum(p['career_status']=='second_team' for p in own);pros=sum(p['career_status'] in ('pro_pending','first_team','second_team') for p in own)
            missing_contracts=sum(p['career_status'] in ('pro_pending','first_team','second_team') and p['contract_id'] is None for p in own)
            self.info.setText(self.info.text()+f'\n선수단 점검: 프로 {pros}/16 · 1군 {first}/5 · 2군 {second}/11 · 계약 누락 {missing_contracts}명'+(' · 다음 정규 시즌 전 1군 5명과 양군 리더를 준비해 주세요.' if first!=5 else ''))
            recent={a['person_id'] for a in auctions if day and a['season']==day.season}
            self.table_people(self.fa_table,[p for p in self.people if p['age']>=17 and (p['agency_id'] is None or p['id'] in recent)])
            self.table_people(self.renew_table,[p for p in own if p['career_status'] in ('first_team','second_team','pro_pending') or p.get('inherited_debut')])
            self.table_people(self.release_table,[p for p in own if p['career_status'] in ('first_team','second_team','pro_pending')])
            from contextlib import closing
            juniors={p.id for p in self.service.recruitment.candidates()}
            application=self.service.recruitment.state(agency) if agency else None
            self.trainee_status.setText((f"{application['round_number']}차 연습생 신청 {application['count']}/2 · "+('추첨 완료' if application['closed'] else '접수 마감 · 추첨 대기' if application['submitted'] else '하루 진행 시 신청 마감')+'\n신청 중: '+(' / '.join(p['name'] for p in application['targets']) or '없음')) if application else '플레이어 기획사를 선택해 주세요.')
            can_apply=bool(agency and application and application['can_apply'] and self.service.draft.state().status=='completed')
            for button in (self.recruit_button,self.remove_application_button,self.clear_application_button):
                button.setEnabled(can_apply);button.setToolTip('하루 진행 전에는 신청을 변경할 수 있습니다.' if can_apply else '창단 수·금요일 또는 일반 월요일의 마감 전에 신청할 수 있습니다.')
            if day and day.is_founding:
                from ..founding import stage_hint
                setup=self.service.founding.state()
                hint=stage_hint(day) if setup and setup['protocol']==2 else '기존 창단 세이브: 첫 월요일 계약·편성·리더 지정 절차를 유지합니다.'
                self.info.setText(self.info.text()+'\n'+hint)
            self.table_people(self.trainee_table,[p for p in self.people if p['career_status']=='trainee' and p['agency_id']==agency or p['id'] in juniors])
            selected=self.person.currentData();self.person.clear()
            for p in self.people:
                if p['agency_id'] in (None,agency):self.person.addItem(p['name'],p['id'])
            self.person.setCurrentIndex(max(0,self.person.findData(selected)))
            selected=self.other.currentData();self.other.clear()
            for a in self.service.agencies():
                if a.id!=agency:self.other.addItem(a.name,a.id)
            self.other.setCurrentIndex(max(0,self.other.findData(selected)))
            self.sessions=self.service.market.negotiations(agency) if agency else ()
            data=[]
            for n in self.sessions:
                offers=n['offers'];last=offers[-1] if offers else None
                data.append((n['id'],self.by_id.get(n['person_id'],{}).get('name',n['person_id']),n['purpose'],STATE.get(n['status'],n['status']),len(offers),3-len(offers),manwon(last['annual']) if last else '미제안','수락' if last and last['accepted'] else '거절' if last else '대기'))
            fill_table(self.negotiation_table,('협상 ID','이름','종류','상태','시도','잔여','직전 연봉(만원)','결과'),data,people=[n['person_id'] for n in self.sessions],profile_columns=(1,))
            if self.negotiation_id:
                for row in range(self.negotiation_table.rowCount()):
                    if self.negotiation_table.item(row,0).text()==self.negotiation_id:self.negotiation_table.setCurrentCell(row,0)
            self.trades=[t for t in self.service.market.trades() if agency in (t['agency_a'],t['agency_b'])]
            trade_rows=[]
            for t in self.trades:
                terms=json.loads(t['versions'][-1]['terms_json'])
                names=lambda ids:' / '.join(self.by_id.get(p,{}).get('name',p) for p in ids) or '없음'
                money_flow=f'{self.names[t["agency_a"]]} → {self.names[t["agency_b"]]}' if terms.get('cash',0)>=0 else f'{self.names[t["agency_b"]]} → {self.names[t["agency_a"]]}'
                trade_rows.append((t['id'],self.names[t['agency_b'] if agency==t['agency_a'] else t['agency_a']],STATE.get(t['status'],t['status']),t['version'],self.names[t['proposer']],names([terms['pro_a']]),names([terms['pro_b']]),f'{money_flow} · {manwon(abs(terms.get("cash",0)))}만원',names(terms.get('trainees_a',())),names(terms.get('trainees_b',())),str([(v['version'],v['response']) for v in t['versions']])))
            fill_table(self.trade_table,('거래 ID','상대','상태','차수','현재 제안자','A측 프로','B측 프로','현금 보상','A측 연습생','B측 연습생','응답 이력'),trade_rows)
            self.trade_table.setSortingEnabled(False)
            for row in range(self.trade_table.rowCount()):
                identity=self.trade_table.item(row,0).text()
                trade=next(t for t in self.trades if t['id']==identity)
                terms=json.loads(trade['versions'][-1]['terms_json'])
                for column,key in ((5,'pro_a'),(6,'pro_b')):
                    person=self.by_id.get(terms[key])
                    if person:
                        item=self.trade_table.item(row,column);item.setIcon(QIcon(self.photos.get(person['photo_path'])))
                        item.setData(PROFILE_ROLE,person['id'])
            self.trade_table.setSortingEnabled(True)
            history=self.service.market.history()
            fill_table(self.history_table,('날짜','선수','유형','이전 팀','새 팀','당시 연봉(만원)','현금(만원)','위약금(만원)','관련 거래'),[(str(GameDate(h['absolute_day'])),self.by_id.get(h['person_id'],{}).get('name',h['person_id']),h['kind'],self.names.get(h['from_agency'],'—'),self.names.get(h['to_agency'],'—'),manwon(h['annual'] or 0),manwon(h['cash']),manwon(h['penalty']),h['related_id'] or '—') for h in history],people=[h['person_id'] for h in history],profile_columns=(1,))
        finally:self._loading=False
        self.trade_people();self.select_negotiation();self.preview();self.update_actions()

    def update_actions(self,*_):
        if self._loading:return
        agency=self.agency()
        for purpose,buttons in (('fa',(self.bid_button,self.direct_button)),('renew',(self.renew_button,)),
            ('release',(self.release_button,self.force_button)),('trade',(self.trade_send_button,*self.trade_reply_buttons)),
            ('debut',(self.debut_button,)),(self.purpose.currentData(),(self.start_button,))):
            reason=self.service.market.action_reason(agency,purpose)
            for button in buttons:button.setEnabled(not reason);button.setToolTip(reason)
        count=len(self.checked_renew_ids());self.renew_count.setText(f'선택 {count}명')
        self.renew_button.setText(f'선택 {count}명 재계약 협상 열기' if count else '선택 선수 재계약 협상')
        self.renew_all_button.setEnabled(self.renew_table.rowCount()>0);self.renew_clear_button.setEnabled(count>0)
        n=next((n for n in getattr(self,'sessions',()) if n['id']==getattr(self,'negotiation_id',None)),None)
        reason=self.service.market.action_reason(agency,n['purpose']) if n else '진행할 협상을 선택해 주세요.'
        for button in (self.offer_button,self.abandon_button):button.setEnabled(bool(n and n['status']=='open' and not reason));button.setToolTip(reason)
        row=self.trade_table.currentRow()
        t=next((t for t in getattr(self,'trades',()) if row>=0 and t['id']==self.trade_table.item(row,0).text()),None)
        if t and t.get('ai_window'):
            w=t['ai_window'];day=self.service.calendar.state().date
            active=bool(day and t['status'] in ('proposed','countered') and t['created_day']<=day.absolute_day<=w['deadline_day'])
            for i,button in enumerate(self.trade_reply_buttons):
                button.setEnabled(active and (i!=2 or w['counter_count']<3))
                button.setToolTip('AI 선제 제안: 다음 주 월요일 마감까지 협상 · 역제안 최대 3회')
    def preview(self,*_):
        if self._loading:return
        p=getattr(self,'by_id',{}).get(self.person.currentData())
        if p and p['exact'] and p['market']:
            basis=30000000 if self.purpose.currentData()=='debut' else p['market']
            ratio=self.offer_amount.value()*10000/basis;self.chance.setText(f'기준 대비 {ratio:.1%} · 수락 {acceptance(self.offer_amount.value()*10000,basis):.1%}')
        else:self.chance.setText('신규 후보 실제 기준·수락 확률 비공개')
    def select_negotiation(self):
        if self._loading:return
        row=self.negotiation_table.currentRow()
        n=next((n for n in getattr(self,'sessions',()) if row>=0 and n['id']==self.negotiation_table.item(row,0).text()),None)
        self.offer_button.setEnabled(bool(n and n['status']=='open' and not self.service.market.action_reason(self.agency(),n['purpose'])))
        if not n:return
        self.negotiation_id=n['id'];self.person.setCurrentIndex(self.person.findData(n['person_id']))
        self.purpose.setCurrentIndex(self.purpose.findData(n['purpose']))
        prior=n['offers'][-1] if n['offers'] else None
        annual=30000000 if n['purpose']=='debut' else raised_offer(prior['annual']) if prior and n['status']=='open' else prior['annual'] if prior else self.by_id[n['person_id']]['market'] or 30000000
        self.offer_amount.setValue(annual//10000)
        if prior:self.offer_duration.setValue(prior['duration'])

    def trade_people(self,*_):
        if self._loading:return
        agency=self.service.draft_session.player_agency();other=self.other.currentData()
        for combo,extras,team in ((self.pro_a,self.extra_a,agency),(self.pro_b,self.extra_b,other)):
            combo.blockSignals(True);old=combo.currentData();combo.clear();extras.clear()
            for p in getattr(self,'people',()):
                if p['agency_id']!=team:continue
                if p['career_status'] in ('first_team','second_team','pro_pending'):combo.addItem(QIcon(self.photos.get(p['photo_path'])),p['name'],p['id'])
                elif p['career_status']=='trainee':item=QListWidgetItem(QIcon(self.photos.get(p['photo_path'])),p['name']);item.setData(Qt.ItemDataRole.UserRole,p['id']);extras.addItem(item)
            combo.setCurrentIndex(max(0,combo.findData(old)));combo.blockSignals(False)
        self.trade_preview()
        self.update_actions()
    def queue_market_photos(self):
        if not self.photo_refresh_timer.isActive():self.photo_refresh_timer.start()

    def refresh_market_photos(self):
        self.trade_preview()
        for table in (self.fa_table,self.renew_table,self.release_table,self.trainee_table):
            blocked=table.blockSignals(True)
            try:
                for row in range(table.rowCount()):
                    item=table.item(row,0)
                    person=getattr(self,'by_id',{}).get(item.data(Qt.ItemDataRole.UserRole)) if item else None
                    if person:item.setIcon(QIcon(self.photos.get(person['photo_path'])))
            finally:table.blockSignals(blocked)

    def trade_preview(self,*_):
        if self._loading:return
        parts=[]
        for combo,photo,summary in ((self.pro_a,self.photo_a,self.trade_summary_a),(self.pro_b,self.photo_b,self.trade_summary_b)):
            p=getattr(self,'by_id',{}).get(combo.currentData())
            if not p:
                photo.original=None;photo.clear();summary.setText('선수를 선택해 주세요.');continue
            photo.set_photo(self.photos.get(p['photo_path']))
            summary.setText(f'{p["name"]} · {p["age"]}세 · {ROLES.get(p["career_status"],p["career_status"])} · 평균 {p["average"]:.1f}\n'
                +' / '.join(f'{SKILL_NAMES[i]} {p["skills"][i]}' for i in range(4))+'\n'
                +' / '.join(f'{SKILL_NAMES[i]} {p["skills"][i]}' for i in range(4,8))+'\n'
                +f'건강 {p["health"]} · {"부상" if p["injured"] else "정상"} · 연봉 {manwon(p["annual"])}만원 · 잔여 {p["remaining_seasons"] or "미정"}시즌')
            strengths=sorted(range(8),key=lambda i:(-p['skills'][i],i))[:2]
            parts.append('강점: '+' / '.join(f'{SKILL_NAMES[i]} {p["skills"][i]}' for i in strengths)+f' · 건강 {p["health"]} · 잔여 {p["remaining_seasons"] or "미정"}시즌')
            parts.append(f'{p["name"]} · {p["age"]}세 · 평균 {p["average"]:.1f} · 연봉 {manwon(p["annual"])}만원 · 종료 {p["end_season"] or "미정"} · {"부상" if p["injured"] else "정상"}')
        self.trade_detail.setText('\n'.join(parts))
    def bid(self):self.action('공개 입찰',lambda:self.service.market.bid(self.agency(),self.selected(self.fa_table),self.bid_amount.value()*10000,self.bid_duration.value(),request_id=uuid.uuid4().hex))
    def start_renew_selected(self):
        checked=self.checked_renew_ids()
        if checked:
            names='\n'.join(self.by_id[p]['name'] for p in checked)
            answer=QMessageBox.question(self,'재계약 일괄 선택',f'{len(checked)}명의 재계약 협상을 여시겠습니까?\n{names}\n\n연봉·계약기간 제안과 계약 확정은 계약 협상 탭에서 개별 진행합니다.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
            opened=[];errors=[]
            for person in checked:
                try:opened.append(self.service.market.start_negotiation(self.agency(),person,'renew'))
                except (ValueError,RuntimeError,OSError,sqlite3.Error) as error:errors.append(f'{self.by_id[person]["name"]}: {error}')
            self.reload()
            if opened:self.tabs.setCurrentIndex(1);self.state_changed.emit()
            message=f'협상 {len(opened)}명 확인 완료. 연봉·계약기간은 각 협상에서 제안해 주세요.'
            if errors:QMessageBox.warning(self,'재계약 처리 결과',message+'\n\n진행하지 못한 선수:\n'+'\n'.join(errors))
            else:QMessageBox.information(self,'재계약 처리 결과',message)
            return
        try:person=self.selected(self.renew_table)
        except ValueError as error:QMessageBox.warning(self,'재계약',str(error));return
        self.person.setCurrentIndex(self.person.findData(person));self.purpose.setCurrentIndex(self.purpose.findData('renew'))
        self.start_negotiation()

    def checked_renew_ids(self):
        return tuple(self.renew_table.item(row,0).data(Qt.ItemDataRole.UserRole) for row in range(self.renew_table.rowCount()) if self.renew_table.item(row,0) and self.renew_table.item(row,0).checkState()==Qt.CheckState.Checked)

    def check_renew_all(self,checked):
        self.renew_table.blockSignals(True)
        for row in range(self.renew_table.rowCount()):self.renew_table.item(row,0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.renew_table.blockSignals(False);self.update_actions()

    def renew_checked(self,item):
        if not self._loading and item.column()==0:self.update_actions()
    def start_fa_selected(self):
        try:person=self.selected(self.fa_table)
        except ValueError as error:QMessageBox.warning(self,'직접 협상',str(error));return
        self.person.setCurrentIndex(self.person.findData(person));self.purpose.setCurrentIndex(self.purpose.findData('fa'))
        self.start_negotiation()
    def start_negotiation(self):
        def run():self.negotiation_id=self.service.market.start_negotiation(self.agency(),self.person.currentData(),self.purpose.currentData());self.tabs.setCurrentIndex(1);return '협상을 열었습니다. 아직 수락 판정은 하지 않았습니다.'
        self.action('협상 열기',run)
    def offer(self):
        def run():
            row=self.negotiation_table.currentRow()
            if row<0:raise ValueError('협상을 먼저 선택해 주세요.')
            identity=self.negotiation_table.item(row,0).text();result=self.service.market.offer(identity,self.offer_amount.value()*10000,self.offer_duration.value(),request_id=uuid.uuid4().hex)
            return '계약 수락' if result['accepted'] else '거절 · 다음 제안은 5% 인상, 최대 3회입니다. 데뷔 연봉은 3,000만원 고정입니다.'
        self.action(f'연봉 {self.offer_amount.value():,}만원 · {self.offer_duration.value()}시즌 계약 제안',run)
    def abandon(self):self.action('협상 포기',lambda:self.service.market.abandon(self.negotiation_table.item(self.negotiation_table.currentRow(),0).text(),self.agency()))
    def select_renew(self):
        if self._loading:return
        try:p=self.selected(self.renew_table)
        except ValueError:return
        self.person.setCurrentIndex(self.person.findData(p));self.purpose.setCurrentIndex(self.purpose.findData('renew'))
    def select_trade(self):
        if self._loading:return
        row=self.trade_table.currentRow()
        if row<0:return
        t=next((t for t in self.trades if t['id']==self.trade_table.item(row,0).text()),None)
        if not t:return
        terms=json.loads(t['versions'][-1]['terms_json']);own=self.agency()==t['agency_a']
        self.other.setCurrentIndex(self.other.findData(t['agency_b'] if own else t['agency_a']))
        self.pro_a.setCurrentIndex(self.pro_a.findData(terms['pro_a'] if own else terms['pro_b']))
        self.pro_b.setCurrentIndex(self.pro_b.findData(terms['pro_b'] if own else terms['pro_a']))
        self.trade_cash.setValue((terms.get('cash',0) if own else -terms.get('cash',0))//10000)
        for listing,ids in ((self.extra_a,terms.get('trainees_a' if own else 'trainees_b',())),(self.extra_b,terms.get('trainees_b' if own else 'trainees_a',()))):
            for i in range(listing.count()):listing.item(i).setSelected(listing.item(i).data(Qt.ItemDataRole.UserRole) in ids)
        self.trade_preview()
        self.update_actions()

    def terms(self):return dict(pro_a=self.pro_a.currentData(),pro_b=self.pro_b.currentData(),cash=self.trade_cash.value()*10000,trainees_a=[i.data(Qt.ItemDataRole.UserRole) for i in self.extra_a.selectedItems()],trainees_b=[i.data(Qt.ItemDataRole.UserRole) for i in self.extra_b.selectedItems()])
    def send_trade(self):
        def run():
            identity=self.service.market.propose_trade(self.agency(),self.other.currentData(),self.terms(),request_id=uuid.uuid4().hex)
            return self.service.market.ai_trade_reply(identity,self.other.currentData())
        self.action('트레이드 제안',run)
    def reply_trade(self,action):
        def run():
            row=self.trade_table.currentRow()
            if row<0:raise ValueError('받은 제안을 선택해 주세요.')
            identity=self.trade_table.item(row,0).text();t=next(t for t in self.trades if t['id']==identity);terms=self.terms()
            if self.agency()!=t['agency_a']:terms=dict(pro_a=terms['pro_b'],pro_b=terms['pro_a'],cash=-terms['cash'],trainees_a=terms['trainees_b'],trainees_b=terms['trainees_a'])
            return self.service.market.trade_reply(identity,self.agency(),action,terms=terms,expected_version=t['ai_window']['revision'] if t.get('ai_window') else t['version'])
        row=self.trade_table.currentRow()
        if row<0:QMessageBox.warning(self,'트레이드','받은 제안을 선택해 주세요.');return
        details=' · '.join(self.trade_table.item(row,col).text() for col in (1,5,6,7,8,9))
        self.action('트레이드 '+action+' · '+details,run)
    def release(self):
        try:
            person=self.selected(self.release_table);quote=self.service.market.release_quote(self.agency(),person)
        except ValueError as error:QMessageBox.warning(self,'방출 조건',str(error));return
        method=self.release_method.currentData()
        self.action(f'선수 방출 · 위약금 {quote["total"]:,}원 · {"즉시 지급" if method=="immediate" else "10주 분할"}',lambda:self.service.market.release(self.agency(),person,method,request_id=uuid.uuid4().hex))
    def force_sale(self):self.action('채무 강제 매각',lambda:self.service.market.force_sale(self.agency(),request_id=uuid.uuid4().hex))
    def recruit(self):
        self.action('연습생 계약 신청',lambda:self.service.market.sign_trainee(self.agency(),self.selected(self.trainee_table),request_id=uuid.uuid4().hex))
    def remove_application(self):
        def remove():
            agency=self.agency();state=self.service.recruitment.state(agency);person=self.selected(self.trainee_table)
            return self.service.recruitment.apply(agency,[p['person_id'] for p in state['targets'] if p['person_id']!=person],expected_revision=state['revision'])
        self.action('신청 취소',remove)
    def show_recruitment_results(self):
        from contextlib import closing
        agency=self.service.draft_session.player_agency()
        with closing(self.service.database.connect()) as c:
            row=c.execute("SELECT w.absolute_day FROM trainee_weeks w LEFT JOIN trainee_rounds r ON r.game_id=w.game_id AND r.round_key=w.absolute_day WHERE w.status='finalized' ORDER BY COALESCE(r.draw_day,w.absolute_day) DESC LIMIT 1").fetchone()
        if row is None:
            QMessageBox.information(self,'월요일 추첨','아직 마감된 신청이 없습니다. 다른 기획사 신청은 마감 후 공개합니다.');return
        results=self.service.recruitment.results(agency,row[0])
        state=self.service.recruitment.state(agency,row[0]);lines=[str(GameDate(state['application_day']))+' 신청 결과']
        for r in results:
            lines.append(self.by_id.get(r['person_id'],{}).get('name',r['person_id'])+' · '+('영입: '+self.names.get(r['winner'],'없음') if r['status']=='signed' else '영입 불가')+' · 신청: '+', '.join(self.names.get(a,a) for a in r['applicants']))
        QMessageBox.information(self,'월요일 추첨 결과','\n'.join(lines) if results else '신청 없음')
    def debut(self):
        person=self.by_id.get(self.selected(self.trainee_table))
        if person and person.get('inherited_debut'):
            self.action('기존 계약 승계 · 프로 2군 승격',lambda:self.service.market.promote_contracted_trainee(self.agency(),person['id'],expected_contract=person['contract_id']));return
        def run():self.person.setCurrentIndex(self.person.findData(self.selected(self.trainee_table)));self.purpose.setCurrentIndex(self.purpose.findData('debut'));self.negotiation_id=self.service.market.start_negotiation(self.agency(),self.person.currentData(),'debut');self.tabs.setCurrentIndex(1)
        self.action('프로 데뷔 협상',run)

import sqlite3
