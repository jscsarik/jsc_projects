"""Frozen award cards and read-only regular-season records."""
from collections import Counter
from fractions import Fraction
import sqlite3
from PySide6.QtCore import Qt,Signal,QSize
from PySide6.QtGui import QColor,QPen
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QComboBox,QTabWidget,QStackedWidget,QFrame,QDialog,QDialogButtonBox,QHeaderView,QMessageBox,QStyledItemDelegate)
from .battle_view import CardPhoto
from .match_page import make_table,fill_table
from ..awards import AWARDS,LABELS,AwardError
from ..config import SKILLS

CANDIDATE_ROLE=Qt.ItemDataRole.UserRole+91

class CandidateBorderDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        super().paint(painter,option,index)
        if not index.data(CANDIDATE_ROLE):return
        painter.save();painter.setPen(QPen(QColor('#39a568'),2))
        rect=option.rect.adjusted(1,1,-1,-1)
        painter.drawLine(rect.topLeft(),rect.topRight());painter.drawLine(rect.bottomLeft(),rect.bottomRight())
        header=option.widget.horizontalHeader()
        visible=[header.logicalIndex(i) for i in range(header.count()) if not header.isSectionHidden(header.logicalIndex(i))]
        if visible and index.column()==visible[0]:painter.drawLine(rect.topLeft(),rect.bottomLeft())
        if visible and index.column()==visible[-1]:painter.drawLine(rect.topRight(),rect.bottomRight())
        painter.restore()

def record_top_ten(records,kind,*,official_candidates=None):
    """Display-only ranking; never changes official award selection."""
    if kind=='winning_idol':
        return sorted((r for r in records if r['appearances']>0),
            key=lambda r:(-r['winning_idol'],r['name'],r['id']))[:10]
    ordered=sorted((r for r in records if r['skills'][kind]['attempts']>0),
        key=lambda r:(-r['skills'][kind]['attempts'],r['name'],r['id']))
    if official_candidates is not None:
        positions={r['id']:i for i,r in enumerate(official_candidates)}
        candidates=[r for r in ordered if r['id'] in positions]
    else:
        positions={};candidates=ordered[:5]
    candidates=sorted(candidates,key=lambda r:(-Fraction(r['skills'][kind]['successes'],r['skills'][kind]['attempts']),positions.get(r['id'],0),r['name'],r['id']))
    ids={r['id'] for r in candidates}
    return candidates+[r for r in ordered if r['id'] not in ids][:10-len(candidates)]

def reason(kind,r):
    if kind in ('mvp','rookie'):return f'승리 아이돌 {r["winning_idol"]}회 · 정규 출전 {r["appearances"]}경기'
    if kind=='leader':return f'리더 추가 성공 {r["leader_successes"]}/{r["leader_attempts"]}회'
    s=r['skills'][kind];return f'시도 {s["attempts"]}회 · 성공률 {100*s["successes"]/s["attempts"]:.2f}%'


class AwardCard(QFrame):
    def __init__(self,kind,page,photo_height):
        super().__init__();self.kind=kind;self.page=page;self.record=None
        self.setObjectName('awardCard');self.setStyleSheet('QFrame#awardCard {background:#f2f8ff;border:1px solid #d4e5f5;border-radius:14px;}')
        box=QVBoxLayout(self);box.setContentsMargins(10,8,10,8);box.setSpacing(4)
        title=QLabel(AWARDS[kind]);title.setStyleSheet('font-size:18px;font-weight:bold;color:#4c85b6;');box.addWidget(title)
        self.photo=CardPhoto(photo_height);self.photo.setMaximumHeight(photo_height);box.addWidget(self.photo,1)
        self.name=QPushButton('미확정');self.name.setFlat(True);self.name.clicked.connect(self.open_profile);self.photo.clicked.connect(self.open_profile);box.addWidget(self.name)
        self.team=QLabel();self.team.setWordWrap(True);box.addWidget(self.team)
        self.metric_label=QLabel();self.metric_label.setWordWrap(True);box.addWidget(self.metric_label)
        self.detail=QPushButton('선정 근거 · 후보 비교');self.detail.clicked.connect(self.open_detail);box.addWidget(self.detail)

    def render(self,record):
        if record and record.get('status')=='NO_ELIGIBLE_CANDIDATE':
            self.record=None;self.name.setEnabled(False);self.detail.setEnabled(False)
            self.name.setText('수상자 없음');self.team.setText('신인 자격을 갖춘 프로 아이돌 없음')
            self.metric_label.setText('NO_ELIGIBLE_CANDIDATE · 공식 처리 완료')
            self.photo.set_photo(self.page.photos.get(''));return
        self.record=record;self.name.setEnabled(record is not None);self.detail.setEnabled(record is not None)
        self.name.setText(record['stats']['name'] if record else '공식 수상 미확정')
        self.team.setText(('수상 당시 '+self.page.names.get(record['awarded_agency_id'],'FA·무소속')+f' · 정규 기준 {record["regular_rank"]}위') if record else '')
        self.metric_label.setText(reason(self.kind,record['stats']) if record else '')
        self.photo.set_photo(self.page.photos.get(record['stats']['photo_path'] or '') if record else self.page.photos.get(''))

    def open_profile(self):
        if self.record:self.page.profile_requested.emit(self.record['person_id'])
    def open_detail(self):
        if self.record:self.page.show_detail(self.record)


class AwardsPage(QWidget):
    profile_requested=Signal(str)
    def __init__(self,service,photos):
        super().__init__();self.service=service;self.names={a.id:a.name for a in service.agencies()};self.cards={}
        from .thumbnails import ThumbnailCache
        self.photos=ThumbnailCache(service.image_root,service.cache_dir/'award_thumbnails',self,image_size=QSize(300,400))
        layout=QVBoxLayout(self);layout.setContentsMargins(12,12,12,12)
        self.title=QLabel('시즌 개인 시상식');self.title.setObjectName('title');layout.addWidget(self.title)
        tools=QHBoxLayout();self.season=QComboBox();self.season.setAccessibleName('시상 대상 시즌');tools.addWidget(self.season)
        refresh=QPushButton('새로 확인');refresh.clicked.connect(self.reload);tools.addWidget(refresh)
        self.finalize_button=QPushButton('공식 시상 확정');self.finalize_button.clicked.connect(self.finalize);tools.addWidget(self.finalize_button);layout.addLayout(tools)
        self.notice=QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        main=QWidget();box=QVBoxLayout(main);mvp=AwardCard('mvp',self,150);self.cards['mvp']=mvp;box.addWidget(mvp,1)
        row=QHBoxLayout()
        for kind in ('rookie','leader'):
            card=AwardCard(kind,self,100);self.cards[kind]=card;row.addWidget(card,1)
        box.addLayout(row,1);self.tabs.addTab(main,'주요 개인상')
        skills=QWidget();box=QVBoxLayout(skills);nav=QHBoxLayout();previous=QPushButton('◀');next_=QPushButton('▶');self.skill_page_label=QLabel()
        nav.addWidget(previous);nav.addWidget(self.skill_page_label,1);nav.addWidget(next_);box.addLayout(nav)
        self.skill_pages=QStackedWidget();box.addWidget(self.skill_pages,1)
        for group in (SKILLS[:4],SKILLS[4:]):
            host=QWidget();grid=QGridLayout(host)
            for i,kind in enumerate(group):
                card=AwardCard(kind,self,120);self.cards[kind]=card;grid.addWidget(card,i//2,i%2)
            self.skill_pages.addWidget(host)
        previous.clicked.connect(lambda:self.skill_pages.setCurrentIndex(0));next_.clicked.connect(lambda:self.skill_pages.setCurrentIndex(1))
        self.skill_pages.currentChanged.connect(lambda i:self.skill_page_label.setText(f'능력치별 매력상 {i+1}/2'));self.skill_page_label.setText('능력치별 매력상 1/2');self.tabs.addTab(skills,'매력상 8종')
        records=QWidget();box=QVBoxLayout(records);nav=QHBoxLayout()
        self.record_previous=QPushButton('◀');self.record_previous.setAccessibleName('이전 기록 항목')
        self.record_kind=QComboBox();self.record_kind.addItem('승리 아이돌 Top 10 · MVP 참고','winning_idol')
        for kind in SKILLS:self.record_kind.addItem(LABELS[kind]+' 성공 Top 10',kind)
        self.record_next=QPushButton('▶');self.record_next.setAccessibleName('다음 기록 항목')
        nav.addWidget(self.record_previous);nav.addWidget(self.record_kind,1);nav.addWidget(self.record_next);box.addLayout(nav)
        self.record_notice=QLabel();self.record_notice.setWordWrap(True);box.addWidget(self.record_notice)
        self.table=make_table();self.table.setItemDelegate(CandidateBorderDelegate(self.table));box.addWidget(self.table,1);self.tabs.addTab(records,'정규 개인 기록')
        self.record_kind.currentIndexChanged.connect(self.render_records)
        self.record_previous.clicked.connect(lambda:self.record_kind.setCurrentIndex((self.record_kind.currentIndex()-1)%self.record_kind.count()))
        self.record_next.clicked.connect(lambda:self.record_kind.setCurrentIndex((self.record_kind.currentIndex()+1)%self.record_kind.count()))
        agencies=QWidget();box=QVBoxLayout(agencies);self.agency=QComboBox();self.agency.addItem('모든 기획사',None)
        for a in service.agencies():self.agency.addItem(a.name,a.id)
        box.addWidget(self.agency);self.agency_summary=QLabel();self.agency_summary.setWordWrap(True);box.addWidget(self.agency_summary)
        self.agency_table=make_table();box.addWidget(self.agency_table,1);self.tabs.addTab(agencies,'기획사·역대 수상')
        self.season.currentIndexChanged.connect(self.render);self.agency.currentIndexChanged.connect(self.render_history)
        self.photos.changed.connect(self.refresh_photos)

    def reload(self):
        selected=self.season.currentData();self.season.blockSignals(True);self.season.clear()
        for s in self.service.awards.seasons():self.season.addItem(f'시즌 {s}',s)
        self.season.setCurrentIndex(max(0,self.season.findData(selected)));self.season.blockSignals(False);self.render()

    def render(self,*_):
        season=self.season.currentData()
        if season is None:return
        self.data=self.service.awards.view(season);batch=self.data['batch'];self.title.setText(f'시즌 {season} 개인 시상식')
        self.notice.setText((f'공식 확정 · 정규 1위 {self.names.get(batch["regular_first"])} · 포스트시즌 챔피언 {self.names.get(batch["champion"])}\n정규 24주 기록만 사용 · 과거 수상 결과는 다시 추첨하지 않습니다.') if batch else '시즌 중 기록 조회 · 공식 수상자 미확정\n'+self.data['issue'])
        self.finalize_button.setEnabled(not batch)
        values={a['award_type']:a for a in self.data['awards']}
        for kind,card in self.cards.items():card.render(values.get(kind))
        self.render_records()
        self.render_history()

    def render_records(self,*_):
        if not hasattr(self,'data'):return
        kind=self.record_kind.currentData()
        official=next((a['candidates'] for a in self.data['awards'] if a['award_type']==kind),None)
        records=record_top_ten(self.data['records'],kind,official_candidates=official)
        if kind=='winning_idol':
            headers=('순위','이름','기획사','승리 아이돌','출전')
            rows=[(i,r['name'],self.names.get(r['agency'],'미확인'),r['winning_idol'],r['appearances']) for i,r in enumerate(records,1)]
            self.record_notice.setText('정규 시즌 승리 아이돌 횟수 순 · MVP 참고 기록 · 공식 시상 기준은 유지됩니다.')
        else:
            headers=('순위','이름','기획사','성공','이벤트 수','성공률')
            rows=[(i,r['name'],self.names.get(r['agency'],'미확인'),r['skills'][kind]['successes'],r['skills'][kind]['attempts'],f'{100*r["skills"][kind]["successes"]/r["skills"][kind]["attempts"]:.1f}%') for i,r in enumerate(records,1)]
            self.record_notice.setText('초록 테두리: 이벤트 수 상위 5명 후보 → 성공률 순 1~5위 · 나머지 6~10위: 이벤트 수 순\n시즌 중 동률은 이름순 임시 표시 · 확정 후 저장된 후보 반영 · 리더 추가·데스매치 제외')
        fill_table(self.table,headers,rows,people=[r['id'] for r in records],profile_columns=(1,))
        for row in range(self.table.rowCount()):
            rank=self.table.item(row,0).data(Qt.ItemDataRole.DisplayRole)
            candidate=kind!='winning_idol' and rank<=min(5,len(official) if official is not None else len(records))
            for column in range(self.table.columnCount()):
                item=self.table.item(row,column);item.setData(CANDIDATE_ROLE,candidate)
                if candidate:item.setToolTip('능력치별 시상 후보 · 이벤트 수 상위 5명')
        self.table.sortItems(0,Qt.SortOrder.AscendingOrder)
        self.table._queue_uniform_columns()

    def render_history(self,*_):
        rows=self.service.awards.history(agency=self.agency.currentData());season=self.season.currentData()
        counts=Counter(r['award_type'] for r in rows)
        self.agency_summary.setText(f'선택 시즌 수상 {sum(r["season"]==season for r in rows)}회 · 통산 {len(rows)}회\n'+' / '.join(f'{label} {counts[kind]}회' for kind,label in AWARDS.items()))
        fill_table(self.agency_table,('시즌','이름','개인상','수상 당시 기획사','정규 기준 기획사','정규 순위','핵심 기록'),
            [(r['season'],r['stats']['name'],r['label'],self.names.get(r['awarded_agency_id'],'FA·무소속'),self.names.get(r['regular_agency_id']),r['regular_rank'],reason(r['award_type'],r['stats'])) for r in rows],people=[r['person_id'] for r in rows],profile_columns=(1,))

    def finalize(self):
        try:self.service.awards.finalize(self.season.currentData());self.reload()
        except (AwardError,RuntimeError,sqlite3.Error) as error:QMessageBox.warning(self,'시상식 기록 확인',str(error))

    def refresh_photos(self):
        for card in self.cards.values():
            if card.record:card.photo.set_photo(self.photos.get(card.record['stats']['photo_path'] or ''))

    def show_detail(self,a):
        dialog=QDialog(self);dialog.setWindowTitle(a['label']+' · 확정 선정 근거');dialog.resize(800,680);box=QVBoxLayout(dialog)
        r=a['stats'];summary=QLabel(f'{r["name"]} · {reason(a["award_type"],r)}\n최초 프로 데뷔 시즌 {r["debut"]} · 정규 {r["appearances"]}경기 · 리더 출전 {r["leader_games"]}경기\n정규 최종 기준 {self.names.get(a["regular_agency_id"])} {a["regular_rank"]}위\n리더 추가 {r["leader_successes"]}/{r["leader_attempts"]} · 추가 성공률 '+(f'{100*r["leader_successes"]/r["leader_attempts"]:.2f}%' if r['leader_attempts'] else '해당 없음'))
        summary.setWordWrap(True);box.addWidget(summary)
        if a['award_type'] in SKILLS:
            v=r['skills'][a['award_type']];box.addWidget(QLabel(f'성공 {v["successes"]} / 실패 {v["attempts"]-v["successes"]} / 시도 {v["attempts"]} · 성공률 비교는 정확한 분수 사용'))
        def comparison(p):
            kind=a['award_type']
            if kind not in SKILLS:return reason(kind,p)
            v=p['skills'][kind];return f'시도 {v["attempts"]} · 성공 {v["successes"]} · 실패 {v["attempts"]-v["successes"]}\n성공률 {100*v["successes"]/v["attempts"]:.2f}%'
        table=make_table();fill_table(table,('후보 이름','정규 기준 기획사','데뷔 시즌','비교 기록'),[(p['name'],self.names.get(p['agency']),p['debut'] or '미확인',comparison(p)) for p in a['candidates']]);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);table.verticalHeader().setDefaultSectionSize(70);table.setWordWrap(True);box.addWidget(table,1)
        contributions=QLabel('소속별 실제 정규 출전·승리 아이돌: '+' / '.join(f'{self.names.get(team,team)} {v["appearances"]}경기·{v["winning_idol"]}회' for team,v in r['contributions'].items()));contributions.setWordWrap(True);box.addWidget(contributions)
        box.addWidget(QLabel(f'저장된 동률 추첨 기록 {len(a["draws"])}건 · 조회 시 재추첨 없음'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.close);box.addWidget(buttons);dialog.show();self.detail_dialog=dialog

