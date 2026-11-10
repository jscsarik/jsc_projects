"""A single, read-only profile component for every list and battle card."""
import json
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor,QFont
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,
    QScrollArea,QProgressBar,QComboBox,QPushButton,QDialogButtonBox,QGridLayout,QSizePolicy,QToolButton,QMenu,QCheckBox)
from .battle_view import CardPhoto
from .match_page import make_table as _make_table,fill_table as _fill_table
from .draft_models import SKILL_NAMES
from .roster_model import STATUS_LABELS
from .development_page import REASONS
from ..config import SKILLS
from ..game_clock import GameDate

KINDS={'regular':'정규','special':'특별전','postseason':'포스트시즌','tiebreak':'동률 결정전'}
PHASES={'main':'주요 능력치','support':'일반 능력치','leader':'리더 추가','deathmatch':'데스매치'}
GROWTH={'first_up':'1군 기본 상승','first_down':'1군 사용량 감소','first_no_appearance':'1군 무출전',
    'second_net':'2군 기본 훈련','trainee_up':'연습생 기본 훈련','additional':'추가 성장','aging':'노화',
    'second_leader':'2군 리더 추가 훈련','focus':'집중 훈련'}


def date_text(day):return str(GameDate(day)) if day is not None else '기록 없음'
def percent(value):return f'{value*100:.2f}%' if value is not None else '기록 없음'


def fit_profile_table(table):
    """Content-sized profile columns; do not change any other game table."""
    previous=getattr(table,'_restoring_columns',False);table._restoring_columns=True
    try:
        table.horizontalHeader().setStretchLastSection(False)
        table.resizeColumnsToContents()
        for column in range(table.columnCount()):
            table.horizontalHeader().resizeSection(column,max(26,min(340,table.columnWidth(column))))
    finally:table._restoring_columns=previous


def make_table():
    table=_make_table();table.setProperty('compactProfileTable',True)
    table.setStyleSheet('QTableView {font-size:13px;} QTableView::item {padding:2px 4px;} QHeaderView::section {font-size:12px;padding:3px 4px;}')
    table.setWordWrap(False);table.horizontalHeader().setMinimumSectionSize(26)
    table.verticalHeader().setDefaultSectionSize(28)
    return table


def fill_table(table,*args,**kwargs):
    _fill_table(table,*args,**kwargs)
    fit_profile_table(table)
def bounds_text(bounds):
    a,b=bounds
    return '미공개' if a is None else f'{a:g}' if a==b else f'{a:g}~{b:g}'

def show_detail(label,visible):
    label.setVisible(visible)
    wrapper=getattr(label,'_text_pages_wrapper',None)
    if wrapper is not None:wrapper.setVisible(visible)


class ProfilePanel(QWidget):
    def __init__(self,service,photos,person,parent=None,*,dock_namespace='profile/single'):
        super().__init__(parent);self.service=service;self.photos=photos;self.person=person;self.data=None
        self.setMinimumWidth(510)
        layout=QVBoxLayout(self);header=QHBoxLayout()
        self.photo=CardPhoto(210);self.photo.setFixedSize(150,190);self.photo.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed);header.addWidget(self.photo)
        heading=QVBoxLayout();self.name=QLabel();self.name.setObjectName('title');self.name.setWordWrap(True)
        self.identity=QLabel();self.identity.setWordWrap(True);self.publication=QLabel();self.publication.setWordWrap(True)
        heading.addWidget(self.name);heading.addWidget(self.identity);heading.addWidget(self.publication)
        self.state_badge=QLabel();self.state_badge.setWordWrap(True);heading.addWidget(self.state_badge)
        options=QHBoxLayout();self.season=QComboBox();options.addWidget(self.season)
        refresh=QPushButton('현재 기록 새로고침');refresh.clicked.connect(self.reload);options.addWidget(refresh)
        heading.addLayout(options);header.addLayout(heading,1);layout.addLayout(header)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.overview=self.text_tab('종합')
        self.skills_page=QWidget();skills=QVBoxLayout(self.skills_page);self.bars=[]
        for label in SKILL_NAMES:
            row=QHBoxLayout();title=QLabel(label);title.setFixedWidth(55);row.addWidget(title)
            bar=QProgressBar();bar.setRange(0,100);bar.setMinimumHeight(24);row.addWidget(bar,1)
            value=QLabel();value.setMinimumWidth(90);row.addWidget(value);skills.addLayout(row);self.bars.append((bar,value))
        self.analysis=QLabel();self.analysis.setWordWrap(True);skills.addWidget(self.analysis)
        self.recent_changes=QLabel();self.recent_changes.setWordWrap(True);skills.addWidget(self.recent_changes);skills.addStretch()
        self.scroll_tab('능력치',self.skills_page)
        condition=QWidget();box=QVBoxLayout(condition);self.condition_label=QLabel();self.condition_label.setWordWrap(True);self.condition_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);box.addWidget(self.condition_label)
        self.condition_label.setStyleSheet('font-size:14px;padding:10px;background:#f2f7fd;border-radius:10px;')
        self.condition_more=QToolButton();self.condition_more.setText('자세히 보기 · 확률 / 날짜 / 성장 제한');self.condition_more.setCheckable(True);box.addWidget(self.condition_more)
        self.condition_detail=QLabel();self.condition_detail.setWordWrap(True);self.condition_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);self.condition_detail.hide();box.addWidget(self.condition_detail)
        self.condition_more.toggled.connect(lambda visible:show_detail(self.condition_detail,visible))
        self.condition_more.toggled.connect(lambda opened:self.condition_more.setText('간단히 보기' if opened else '자세히 보기 · 확률 / 날짜 / 성장 제한'))
        self.injury_table=make_table();self.injury_table.setMinimumHeight(160);box.addWidget(QLabel('실제 부상 이력'));box.addWidget(self.injury_table)
        self.moves_table=make_table();self.moves_table.setMinimumHeight(160);box.addWidget(QLabel('저장된 선수단 이동 이력'));box.addWidget(self.moves_table)
        self.calendar_table=make_table();self.calendar_table.setMinimumHeight(120);box.addWidget(QLabel('최근 7일 실제 출전 기록'));box.addWidget(self.calendar_table)
        self.effective_table=make_table();self.effective_table.setMinimumHeight(220);box.addWidget(QLabel('원본과 현재 날짜의 경기 출전 시 유효 능력치'));box.addWidget(self.effective_table)
        self.scroll_tab('피로·부상',condition)
        matches=QWidget();box=QVBoxLayout(matches);filters=QHBoxLayout();self.match_kind=QComboBox();self.match_kind.addItem('전체 경기',None)
        for key,value in KINDS.items():self.match_kind.addItem(value,key)
        self.match_kind.setCurrentIndex(1)
        filters.addWidget(self.match_kind);box.addLayout(filters)
        self.match_summary=QLabel();self.match_summary.setWordWrap(True);box.addWidget(self.match_summary)
        self.record_tabs=QTabWidget();box.addWidget(self.record_tabs,1)
        self.season_history_table=make_table();self.record_tabs.addTab(self.season_history_table,'시즌별 · 통산')
        self.match_table=make_table();self.ability_table=make_table();self.content_table=make_table()
        for label,table in [('최근 실제 출전',self.match_table),('능력치·판정 구분',self.ability_table),('콘텐츠별 일반 판정',self.content_table)]:self.record_tabs.addTab(table,label)
        self.skill_total_table=make_table();self.record_tabs.addTab(self.skill_total_table,'능력치별 일반 합계')
        self.tabs.addTab(matches,'경기 기록')
        self.contract_label=self.text_tab('계약·경력')
        contract_box=self.contract_label.parentWidget().layout()
        self.contract_label.setStyleSheet('font-size:14px;padding:10px;background:#f2f7fd;border-radius:10px;')
        self.contract_more=QToolButton();self.contract_more.setText('자세히 보기 · 계약 / 지급 / 이적 / 수상');self.contract_more.setCheckable(True)
        self.contract_detail=QLabel();self.contract_detail.setWordWrap(True);self.contract_detail.hide()
        contract_box.insertWidget(1,self.contract_more);contract_box.insertWidget(2,self.contract_detail)
        self.contract_more.toggled.connect(lambda visible:show_detail(self.contract_detail,visible))
        self.contract_more.toggled.connect(lambda opened:self.contract_more.setText('간단히 보기' if opened else '자세히 보기 · 계약 / 지급 / 이적 / 수상'))
        growth=QWidget();box=QVBoxLayout(growth);self.growth_summary=QLabel();self.growth_summary.setWordWrap(True);box.addWidget(self.growth_summary)
        self.growth_summary.setStyleSheet('font-size:14px;padding:8px;background:#f2f7fd;border-radius:10px;')
        growth_tools=QHBoxLayout();self.growth_zero=QCheckBox('변화 없는 기록도 보기');self.growth_zero.toggled.connect(self.render_growth)
        self.growth_more=QToolButton();self.growth_more.setText('정산 설명 보기');self.growth_more.setCheckable(True)
        growth_tools.addWidget(self.growth_zero);growth_tools.addWidget(self.growth_more);growth_tools.addStretch();box.addLayout(growth_tools)
        self.growth_detail=QLabel();self.growth_detail.setWordWrap(True);self.growth_detail.hide();box.addWidget(self.growth_detail)
        self.growth_more.toggled.connect(lambda visible:show_detail(self.growth_detail,visible))
        self.growth_table=make_table();box.addWidget(self.growth_table,1);self.tabs.addTab(growth,'성장 이력')
        self.tabs.tabBar().moveTab(5,4)
        self.season.currentIndexChanged.connect(self.reload);self.match_kind.currentIndexChanged.connect(self.render_matches)
        photos.changed.connect(self.refresh_photo);self.reload()
        for key in ('injury_table','moves_table','calendar_table','effective_table','season_history_table','match_table','skill_total_table','ability_table','content_table','growth_table'):
            table=getattr(self,key)
            layout_key='profile/content_fit3/'+key
            table.bind_layout(service.settings_dir/'ui_layout.ini',layout_key)
            fit_profile_table(table)
        from .dock_install import install_profile_docks
        self.dock_layouts=install_profile_docks(self,service.settings_dir/'ui_layout.ini',dock_namespace)

    def scroll_tab(self,label,widget):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);self.tabs.addTab(scroll,label)

    def text_tab(self,label):
        widget=QWidget();layout=QVBoxLayout(widget);text=QLabel();text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(text);layout.addStretch()
        self.scroll_tab(label,widget);return text

    def reload(self,*_):
        self.data=self.service.profiles.get(self.person,season=self.season.currentData());d=self.data;p=d['identity'];self.name.setText(p.get('display_name',p['name']))
        self.season.blockSignals(True);self.season.clear()
        for season in d['seasons']:self.season.addItem(f'시즌 {season}',season)
        self.season.setCurrentIndex(self.season.findData(d['season']));self.season.blockSignals(False)
        role=STATUS_LABELS.get(p['career_status'],p['career_status']) if p['career_status'] not in ('unassigned',None) else '드래프트 후보'
        self.identity.setText(f'{p["age"]}세 · {p["agency_name"] or "소속 없음"} · {role}\n'+(' / '.join('1군 리더' if x['squad']=='first_team' else '2군 리더' for x in d['leaders']) or '리더 미지정'))
        self.publication.setText(('공개 현재 능력치 · CA ' if d['exact'] else '스카우팅 추정치 · 추정 CA ')+bounds_text(d['average']))
        self.publication.setToolTip('CA는 현재 8개 능력치의 산술평균입니다.' if d['exact'] else '저장된 추정 범위만 표시합니다. 막대는 범위의 중앙값이며 실제 수치를 표시하지 않습니다.')
        self.refresh_photo()
        for (bar,label),bounds in zip(self.bars,d['bounds']):
            low,high=bounds;bar.setValue(round((low+high)/2) if low is not None else 0)
            text=bounds_text(bounds);label.setText(text);bar.setFormat(text)
            bar.setToolTip('현재 능력치' if d['exact'] else '저장된 추정 범위의 중앙값으로 시각화합니다.')
        ranked=sorted(range(8),key=lambda i:sum(d['bounds'][i]) if d['bounds'][i][0] is not None else -1,reverse=True)
        self.analysis.setText(('공개 수치 기준' if d['exact'] else '추정 범위 기준')+' · 상위: '+' / '.join(SKILL_NAMES[i] for i in ranked[:3])+'\n하위: '+' / '.join(SKILL_NAMES[i] for i in ranked[-3:]) if all(a is not None for a,b in d['bounds']) else '능력치 분석 자료 미공개')
        condition=d['condition'];status='미공개' if condition is None else '부상 · 출전 불가' if condition['injured'] else ('1군 출전 가능' if p['career_status']=='first_team' else '현재 1군 아님 · 정규 출전 불가')
        self.state_badge.setText(f'건강 {str(d["health"])+"/90" if d["health"] is not None else "미공개"} · {status}\n계약: {d["contract"]["status"]}')
        if d['exact']:
            changed=[r for r in d['growth'] if any(r['deltas'])]
            latest=changed[0] if changed else None
            rises=' / '.join(SKILL_NAMES[i] for i,v in enumerate(latest['deltas']) if v>0) if latest else ''
            falls=' / '.join(SKILL_NAMES[i] for i,v in enumerate(latest['deltas']) if v<0) if latest else ''
            totals=[sum(r['deltas'][i] for r in d['growth']) for i in range(8)]
            self.recent_changes.setText(f'건강 {d["health"]} (CA 평균에 포함하지 않음)\n최근 상승: {rises or "기록 없음"} / 최근 감소: {falls or "기록 없음"}\n선택 시즌 저장된 정산 누계: '+' / '.join(f'{name} {v:+d}' for name,v in zip(SKILL_NAMES,totals))+'\n시즌 시작 대비: 시작 스냅샷 기록 없음 · 확인된 정산 누계를 별도 표시')
        else:self.recent_changes.setText('미공개 후보의 건강·실제 성장 이력은 공개하지 않습니다.')
        self.overview.setText(f'{d["date"]}\n\n{p["name"]} · {p["age"]}세\n소속: {p["agency_name"] or "소속 없음"} / {role}\n출전 상태: {status}\n건강: {d["health"] if d["health"] is not None else "미공개"}\n계약: {d["contract"]["status"]}\n\n이 화면은 저장 기록 조회 전용입니다. 과거 경기 결과를 다시 계산하지 않습니다.')
        self.render_condition();self.render_matches();self.render_contract();self.render_growth()

    def refresh_photo(self):
        if self.data:self.photo.set_photo(self.photos.get(self.data['identity']['photo_path']))

    def render_condition(self):
        d=self.data;c=d['condition']
        if c is None:
            self.condition_label.setText('미공개 후보의 건강·피로·부상 정보는 공개하지 않습니다.')
            self.condition_detail.clear();self.condition_more.setChecked(False);self.condition_more.hide()
            fill_table(self.injury_table,('날짜','구분'),());fill_table(self.moves_table,('날짜','이전','현재','사유'),())
            fill_table(self.calendar_table,('날짜','실제 출전'),());fill_table(self.effective_table,('능력치','원본','경기 유효값'),());return
        p=d['identity']
        self.condition_more.show()
        next_match=c['next_match'];weekly=c['weekly_growth']
        next_text='확인된 다음 일정 없음 · 다음 단계 피로를 단정하지 않습니다.' if next_match is None else f'{date_text(next_match["day"])} · {next_match["kind"]}에 실제 출전할 경우 -{percent(next_match["penalty"])} (그 사이 추가 출전을 가정하지 않음)'
        growth_note=('비시즌: 성장 정산 없음' if not weekly['active'] else '상승 2회 제한 사유 발생' if weekly['rise_restricted'] else '현재까지 상승 제한 사유 없음 (주간 결과는 미확정)')
        supplement=f'''\n\n현재 날짜의 경기 출전 시 피로: -{percent(c['preview_penalty'])}
다음 일정의 조건부 예상: {next_text}
이번 주 실제 출전 날짜: {c['week_appearance_days']}일
확인된 과거 등록 최고 기록: {str(c['recorded_peak_registration_weeks'])+'주' if c['recorded_peak_registration_weeks'] is not None else '기록 없음'}
필요 휴식: {c['remaining_rest_weeks']}주 (앞으로 더 쉬어야 하는 기간)
현재 1군 복귀: {'가능(기존 인원 제한·맞교환 필요)' if c['can_return_now'] else c['return_reason']}

기본 부상 확률과 현재 조건부 확률 (기존 엔진 그대로)
경기 출전: 기본 {percent(c['base_probabilities']['match'])} / 현재 {percent(c['probabilities']['match'])}
1군 비출전일: 기본 {percent(c['base_probabilities']['first_rest'])} / 현재 {percent(c['probabilities']['first_rest'])}
2군 소속일: 기본 {percent(c['base_probabilities']['second'])} / 현재 {percent(c['probabilities']['second'])}
2군은 현재 엔진의 소속별 판정식을 표시하며, 남아 있는 등록 단계가 반영될 수 있습니다.

이번 주 성장: {growth_note}
연속 출전 3일째 도달: {'있음' if weekly['three_consecutive_days'] else '없음'} / 이번 주 부상 발생: {'있음' if weekly['injury_occurred'] else '없음'}
주간 기본 성장 유형이 1군으로 확정되는 경우의 상승 제한입니다. 하락·별도 추가 성장 규칙은 바꾸지 않습니다.'''
        compact=f'''실제 출전과 등록은 별개입니다. 원본 능력치·건강을 변경하지 않습니다.
현재 실제 연속 출전 {c['streak']}일 / 최근 실제 출전 기준 피로 -{percent(c['current_penalty'])}
직전 출전: {date_text(c['last_day'])} / 오늘 실제 출전: {'있음' if c['today_played'] else '없음'}
하루 미출전으로 연속 기록 초기화: {'해당' if c['reset'] else '아직 해당 없음'}

현재 1군 등록 위험 단계 {c['registration_weeks']}주차 / {c['multiplier']}배
선택 시즌 확인된 등록 {c['season_registration_weeks']}주 / 실제 출전 {c['appearance_weeks']}주
마지막 승격: {date_text(c['promotion'])} / 마지막 강등: {date_text(c['demotion'])}
이력 확인 시작: {date_text(c['known_since'])}
필요 휴식 {c['remaining_rest_weeks']}주 (완료한 휴식은 차감)
현재 소속 유지 시 초기화 예상: {date_text(c['reset_expected'])}

건강 {d['health']} / {'부상 · 출전 불가' if c['injured'] else '부상 없음'} / 선택 시즌 부상 {c['season_injuries']}회
마지막 부상: {date_text(c['injury_day'])}
저장된 회복 가능일: {date_text(c['recovery_day'])}
저장된 1군 복귀 제한 해제일: {date_text(c['return_not_before'])}
부상 중·현재 소속에 해당하지 않는 확률은 실제 추가 판정이 아닙니다.'''
        status='부상 · 출전 불가' if c['injured'] else '정규 출전 가능' if p['career_status']=='first_team' else '부상 없음 · 현재 1군 아님'
        return_text='현재 1군' if p['career_status']=='first_team' else '가능 (정원·교체 규칙 적용)' if c['can_return_now'] else c['return_reason']
        summary=[f'건강 {d["health"]}/90 · {status}',
            f'실제 연속 출전 {c["streak"]}일 · 출전 시 피로 -{percent(c["preview_penalty"])}',
            f'1군 연속 등록 {c["registration_weeks"]}주 · 위험 {c["multiplier"]}배',
            f'필요 휴식 {c["remaining_rest_weeks"]}주',
            f'1군 복귀: {return_text}',f'직전 출전: {date_text(c["last_day"])}']
        if c['injured']:summary.append(f'회복 예정: {date_text(c["recovery_day"])}')
        if c['return_not_before'] is not None:summary.append(f'복귀 제한 해제: {date_text(c["return_not_before"])}')
        self.condition_label.setText('\n'.join(summary));self.condition_detail.setText(compact+supplement)
        fill_table(self.injury_table,('발생 날짜','실제 판정 구분','당시 선수단','당시 기획사 ID'),[(date_text(e['day']),{'match':'경기 출전','first_rest':'1군 미출전일','second':'2군 소속일'}.get(e['kind'],e['kind']),STATUS_LABELS.get(e['squad'],'기록 없음'),e['agency_id'] or '기록 없음') for e in c['injuries']])
        fill_table(self.calendar_table,('실제 게임 날짜','출전 여부'),[(date_text(e['day']),'실제 출전' if e['played'] else '기록 미확인' if not e['known'] else '미출전' if e['closed'] else '현재까지 미출전(진행 중)') for e in c['recent_calendar']])
        fill_table(self.effective_table,('능력치','원본 값','현재 날짜 경기 출전 시 유효값'),[(name,b[0],f'{value:.2f}') for name,b,value in zip(SKILL_NAMES,d['bounds'],c['today_effective_values'])])
        fill_table(self.moves_table,('실제 날짜','이전','현재','사유'),[(date_text(e['day']),STATUS_LABELS.get(e.get('from'),e.get('from')),STATUS_LABELS.get(e.get('to'),e.get('to')),e.get('reason','기록 없음')) for e in c['moves']])

    def render_matches(self,*_):
        if not self.data:return
        kind=self.match_kind.currentData();records=[r for r in self.data['matches'] if not kind or r['kind']==kind]
        seasons=self.service.records.player_seasons(self.person,kind=kind) if self.data['exact'] else []
        self.season_history_table.setSortingEnabled(False)
        fill_table(self.season_history_table,('시즌','당시 소속','실제 경기','주요 능력치 성공','일반 능력치 성공','승','패','기본 시도','기본 성공률','리더 추가 성공','DM 성공','승리 아이돌','패배 아이돌'),
            [(r['label'],r['team'],r['appearances'],r['main_successes'] if r['main_successes'] is not None else '기록 없음',r['support_successes'] if r['support_successes'] is not None else '기록 없음',r['wins'] or 0,r['losses'] or 0,r['attempts'],percent(r['rate']),r['leader_successes'],r['deathmatch_successes'],r['winning_idol'],r['losing_idol']) for r in seasons])
        self.season_history_table.setSortingEnabled(False)
        for row,r in enumerate(seasons):
            if r['row_type']!='team':
                for col in range(self.season_history_table.columnCount()):
                    item=self.season_history_table.item(row,col);item.setBackground(QColor('#fff0ca' if r['row_type']=='career' else '#edf3fc'));font=QFont();font.setBold(True);item.setFont(font)
        stats=self.service.profiles.statistics(records);abilities=stats['abilities']
        def totals(phases):return sum(r['successes'] for r in abilities if r['phase'] in phases),sum(r['attempts'] for r in abilities if r['phase'] in phases)
        success,attempts=totals(('main','support'));leader,leader_n=totals(('leader',));dm,dm_n=totals(('deathmatch',))
        main,main_n=totals(('main',));support,support_n=totals(('support',))
        self.match_summary.setText(f'시즌 {self.data["season"]} 실제 출전 {len(records)}경기 · '+ ' / '.join(f'{KINDS[k]} {v}' for k,v in stats['appearances'].items())+
            f'\n주요 능력치 성공 {main}/{main_n} · 일반 능력치 성공 {support}/{support_n} · 기본 성공률 {percent(success/attempts if attempts else None)}\n리더 추가 {leader}/{leader_n} · DM {dm}/{dm_n} (별도 집계) · 시즌별 표는 전체 시즌, 상세 기록은 선택 시즌입니다.')
        rows=[]
        for r in records:
            basic=[x for x in r['judgments'] if x['phase'] in ('main','support')];n=sum(x['attempts'] for x in basic);k=sum(x['successes'] for x in basic)
            rows.append((date_text(r['day']),KINDS[r['kind']],r['content'],' / '.join(r['opponents']),{'win':'승','loss':'패'}.get(r['outcome'],r['outcome']),'실제 출전',sum(x['successes'] for x in basic if x['phase']=='main'),sum(x['successes'] for x in basic if x['phase']=='support'),percent(k/n if n else None),sum(x['attempts'] for x in r['judgments'] if x['phase']=='leader'),'있음' if r['injured_after'] else '없음'))
        rows=[row+tuple('O' if r.get(key) else '' for key in ('winning_idol','losing_idol')) for row,r in zip(rows,records)]
        fill_table(self.match_table,('날짜','경기 종류','콘텐츠','상대','결과','출전','주요 능력치 성공','일반 능력치 성공','기본 성공률','리더 추가 시도','경기 후 부상','승리 아이돌','패배 아이돌'),rows)
        fill_table(self.ability_table,('능력치','판정','시도','성공','실패','성공률','성장 정산 반영 시도','성장 미정산 시도'),[(SKILL_NAMES[SKILLS.index(r['skill'])],PHASES[r['phase']],r['attempts'],r['successes'],r['failures'],percent(r['successes']/r['attempts'] if r['attempts'] else None),r['growth_attempts'],r['pending_growth_attempts']) for r in abilities])
        fill_table(self.skill_total_table,('능력치','주요 시도','일반 시도','기본 합계','기본 성공 합계','기본 실패','성공률','성장 반영','미정산'),[(SKILL_NAMES[SKILLS.index(r['skill'])],r['main_attempts'],r['random_attempts'],r['attempts'],r['successes'],r['failures'],percent(r['successes']/r['attempts'] if r['attempts'] else None),r['growth_attempts'],r['pending_growth_attempts']) for r in stats['skill_totals']])
        contents=self.service.profiles.content_statistics(self.person,season=self.data['season'],kind=kind) if self.data['exact'] else []
        fill_table(self.content_table,('콘텐츠','구간','실제 출전','주요 능력치 성공','일반 능력치 성공','기본 시도','기본 실패','기본 성공률'),[(r['content_name'],KINDS[r['kind']],r['appearances'],r['main_successes'] if r['main_successes'] is not None else '기록 없음',r['support_successes'] if r['support_successes'] is not None else '기록 없음',r['attempts'],r['attempts']-r['successes'],percent(r['rate'])) for r in contents])

    def render_contract(self):
        d=self.data;draft=d['draft'];p=d['identity']
        text=f'현재 소속: {p["agency_name"] or "소속 없음"}\n계약 상태: {d["contract"]["status"]}\n계약 시작/만료 시즌: 기록 없음\n계약 기간/잔여 시즌: 기록 없음\n계약 연봉: 기록 없음\n계약금: 기록 없음\n시장연봉 / 시장가치: 기록 없음\n계약 갱신 / FA 예정: 기록 없음\n\n계약 시스템이 아직 저장하지 않은 정보를 가상으로 채우지 않습니다.'
        if draft:text+=f'\n\n최초 지명: {draft["agency_name"]} · {draft["round_number"]}라운드 · 전체 {draft["pick_number"]}순번'
        elif d.get('trainee_debut_season'):text+=f'\n\n최초 지명: 시즌 {d["trainee_debut_season"]} 연습생 데뷔'
        else:text+='\n\n최초 지명: 기록 없음'
        names={a.id:a.name for a in self.service.agencies()}
        for pick in d.get('annual_drafts',[]):
            text+=f'\n시즌 {pick["target_season"]} · 통합 드래프트 {pick["round_number"]}라운드 · 전체 {pick["pick_number"]}순위 · {names.get(pick["agency_id"],pick["agency_id"])} 지명 · {pick["status"]}'
        text+='\n등장·계약·이적·데뷔 시즌: 기록 없음\n선수단 이동은 컨디션 탭의 저장 이력을 참조하세요.'
        if d['exact'] and d['contract']['salary'] is not None:
            contract=d['contract']
            text=text.replace('계약 연봉: 기록 없음',f'회계 계약 연봉: {contract["salary"]:,}원')
            text=text.replace('계약 시작/만료 시즌: 기록 없음',f'계약 시작/만료 시즌: {contract.get("start_season") or "기록 없음"} / {contract.get("end_season") or "미정"}')
            text+=f'\n\n회계 적용 시작: {GameDate(contract["start"])} · 과거 지급 소급 없음'
        if d['exact']:
            names={a.id:a.name for a in self.service.agencies()}
            for row in self.service.finance.payroll(person=self.person):
                text+=f'\n시즌 {row["season"]} / {row["cycle"]}회 · {names.get(row["agency_id"],row["agency_id"])}: 기본 {row["base_krw"]:,} · 지급 {row["paid_krw"]:,} · 미지급 {row["due_krw"]-row["paid_krw"]:,}원'
            for record in self.service.market.history(self.person):
                text+=f'\n{GameDate(record["absolute_day"])} · {record["kind"]} · {names.get(record["from_agency"],"미소속")} → {names.get(record["to_agency"],"미소속")} · 당시 연봉 {(record["annual"] or 0):,}원'
        from ..awards import AWARDS
        totals=d.get('award_totals',{})
        text+='\n\n시즌 개인상 · 통산 '+str(sum(totals.values()))+'회\n'+' / '.join(f'{label} {totals.get(kind,0)}회' for kind,label in AWARDS.items())
        for award in d.get('awards',[]):
            names={a.id:a.name for a in self.service.agencies()}
            record=award['stats'];kind=award['award_type']
            if kind in ('mvp','rookie'):reason=f'승리 아이돌 {record["winning_idol"]}회'
            elif kind=='leader':reason=f'리더 추가 성공 {record["leader_successes"]}/{record["leader_attempts"]}회'
            else:reason=f'시도 {record["skills"][kind]["attempts"]} · 성공 {record["skills"][kind]["successes"]}'
            text+=f'\n시즌 {award["season"]} — {award["label"]} · 수상 당시 {names.get(award["awarded_agency_id"],"FA·무소속")} · 정규 {award["regular_rank"]}위 · {reason} · 확정 {GameDate(award["finalized_day"])}'
        self.contract_detail.setText(text if d['exact'] else '')
        self.contract_more.setVisible(d['exact'])
        if not d['exact']:
            self.contract_more.setChecked(False);self.contract_label.setText('미지명 후보 · 계약 및 경력 정보 미공개');return
        contract=d['contract'];salary=contract['salary']
        amount=f'{salary//10000:,}만원' if salary is not None and salary%10000==0 else f'{salary:,}원' if salary is not None else '유효 계약 기록 없음'
        summary=[f'현재 소속: {p["agency_name"] or "미소속"}',f'현재 연봉: {amount}']
        if salary is not None:summary.append(f'계약: 시즌 {contract.get("start_season") or "기록 없음"} ~ {contract.get("end_season") or "만료 미정"}')
        if draft:summary.append(f'최초 지명: {draft["agency_name"]} · {draft["round_number"]}라운드 {draft["pick_number"]}순위')
        elif d.get('trainee_debut_season'):summary.append(f'최초 지명: 시즌 {d["trainee_debut_season"]} 연습생 데뷔')
        if d.get('annual_drafts'):
            pick=d['annual_drafts'][-1];summary.append(f'통합 드래프트: 시즌 {pick["target_season"]} · {pick["round_number"]}라운드 {pick["pick_number"]}순위')
        summary.append(f'시즌 개인상 · 통산 {sum(totals.values())}회')
        self.contract_label.setText('\n'.join(summary))

    def render_growth(self,*_):
        if not self.data:return
        growth=self.data['growth']
        totals=[sum(r['deltas'][i] for r in growth) for i in range(8)]
        nonzero=' · '.join(f'{name} {value:+d}' for name,value in zip(SKILL_NAMES,totals) if value)
        self.growth_summary.setText((f'시즌 {self.data["season"]} · 순변화 {sum(totals):+d} (능력치 합계)\n'+(nonzero or '저장된 능력치 변화 없음')) if self.data['exact'] else '미공개 후보의 성장 이력은 공개하지 않습니다.')
        self.growth_detail.setText(('저장된 정산의 능력치별 순변화입니다. 시즌 시작 CA를 역산하지 않습니다.\n'+' / '.join(f'{name} {value:+d}' for name,value in zip(SKILL_NAMES,totals))) if self.data['exact'] else '')
        self.growth_more.setVisible(self.data['exact']);self.growth_zero.setVisible(self.data['exact'])
        if not self.data['exact']:self.growth_more.setChecked(False)
        rows=[]
        for r in growth:
            detail=' / '.join(f'{SKILL_NAMES[SKILLS.index(c["skill"])]} {c["applied"]:+d}: {GROWTH.get(c["kind"],c["kind"])}' for c in r['changes'] if c['applied'])
            actual=' · '.join(f'{name} {value:+d}' for name,value in zip(SKILL_NAMES,r['deltas']) if value)
            if r['age_before']!=r['age_after']:actual+=(' · ' if actual else '')+f'나이 {r["age_before"]}→{r["age_after"]}'
            if not actual and not self.growth_zero.isChecked():continue
            rows.append((date_text(r['day']),{'growth':'성장','aging':'노화','birthday':'나이 증가'}[r['kind']],STATUS_LABELS.get(r['role'],r['role']),actual or '변화 없음',detail or ' / '.join(REASONS.get(e,e) for e in r['reasons']) or '—'))
        fill_table(self.growth_table,('정산 날짜','종류','당시 신분','실제 변화','상세 사유'),rows)
        self.growth_table.verticalHeader().setDefaultSectionSize(28)
        for row in range(self.growth_table.rowCount()):
            for column in (3,4):
                item=self.growth_table.item(row,column);item.setToolTip(item.text())


class ProfileDialog(QDialog):
    def __init__(self,service,photos,people,parent=None):
        super().__init__(parent);self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('아이돌 상세 프로필' if len(people)==1 else '아이돌 비교');self.resize(1400 if len(people)==1 else 1300,800 if len(people)==1 else 850)
        self.setMinimumSize(640,480);layout=QVBoxLayout(self)
        scroll=QScrollArea();scroll.setWidgetResizable(True);host=QWidget();row=QHBoxLayout(host)
        self.panels=[ProfilePanel(service,photos,person,host,dock_namespace='profile/single' if len(people)==1 else f'profile/compare{i}') for i,person in enumerate(people)]
        for panel in self.panels:row.addWidget(panel,1)
        scroll.setWidget(host);layout.addWidget(scroll,1)
        footer=QHBoxLayout();self.panel_layout_button=QToolButton();self.panel_layout_button.setText('패널 배치 ▾');self.panel_layout_button.clicked.connect(self.layout_menu)
        footer.addWidget(self.panel_layout_button);footer.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(self.close);footer.addWidget(buttons);layout.addLayout(footer)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')

    def layout_menu(self):
        menu=QMenu(self)
        for panel in self.panels:
            group=panel.dock_layouts.make_menu(menu);group.setTitle(panel.name.text());menu.addMenu(group)
        menu.exec(self.panel_layout_button.mapToGlobal(self.panel_layout_button.rect().bottomLeft()));menu.deleteLater()

    def closeEvent(self,event):
        for panel in getattr(self,'panels',[]):
            if hasattr(panel,'dock_layouts'):panel.dock_layouts.shutdown()
        super().closeEvent(event)
