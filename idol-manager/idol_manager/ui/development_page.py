"""Read-only public development history. No settlement or PA queries in UI."""
import json
from PySide6.QtCore import QSize,Qt,QTimer,QEvent
from PySide6.QtGui import QIcon,QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QCheckBox,QPushButton
from ..game_clock import GameDate
from .match_page import make_table,fill_table
from .draft_models import SKILL_NAMES

KINDS={'growth':'주간 성장','aging':'능력치 노화','birthday':'시즌 나이 증가'}
ROLES={'first_team':'1군','second_team':'2군','trainee':'연습생'}
REASONS={'injury':'부상으로 상승 보너스 제외','three_consecutive_days':'연속 3일 출전으로 상승 보너스 제외',
    'no_appearance':'실제 무출전: 기본 감소','postseason_waiting':'포스트시즌 부전승·대기: 무출전 감소 제외',
    'partial_role_history':'확인 가능한 소속 이력만 집계'}


class DevelopmentPage(QWidget):
    def __init__(self,service,thumbnails,parent=None):
        super().__init__(parent);self.service=service;self.thumbnails=thumbnails;self.rows=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(26,18,26,18)
        title=QLabel('주간 성장 · 노화 기록');title.setObjectName('title');layout.addWidget(title);self.heading=title
        self.notice=QLabel('지난주 월~일 기록을 다음 월요일에 정산합니다. 개별 성장 상한은 공개하지 않습니다.')
        self.notice.setWordWrap(True);layout.addWidget(self.notice)
        controls=QHBoxLayout();self.period=QComboBox();self.period.setMinimumContentsLength(35)
        self.agency=QComboBox();self.changed=QCheckBox('변화·제외 사유 있는 선수만');self.changed.setChecked(True)
        refresh=QPushButton('기록 새로고침');refresh.clicked.connect(self.reload)
        for widget in (self.period,self.agency,self.changed,refresh):controls.addWidget(widget)
        layout.addLayout(controls);self.table=make_table();self.table.setIconSize(QSize(44,52));self.table.verticalHeader().setDefaultSectionSize(58)
        layout.addWidget(self.table,1);self.empty=QLabel();self.empty.setWordWrap(True);layout.addWidget(self.empty)
        self.period.currentIndexChanged.connect(self.render);self.agency.currentIndexChanged.connect(self.render);self.changed.toggled.connect(self.render)
        self.photo_timer=QTimer(self);self.photo_timer.setSingleShot(True);self.photo_timer.timeout.connect(self.photos)
        self.thumbnails.changed.connect(self.queue_photos);self.table.viewport().installEventFilter(self)
        self.table.verticalScrollBar().valueChanged.connect(self.queue_photos);self.reload()

    def reload(self,*_):
        current=self.period.currentData();agency=self.agency.currentData()
        self.period.blockSignals(True);self.agency.blockSignals(True)
        self.period.clear()
        for row in self.service.development.periods():
            self.period.addItem(f'{GameDate(row["absolute_day"])} · {KINDS[row["kind"]]}',row['id'])
        if current:self.period.setCurrentIndex(max(0,self.period.findData(current)))
        self.agency.clear();self.agency.addItem('전체 기획사',None)
        for a in self.service.agencies():self.agency.addItem(a.name,a.id)
        if agency:self.agency.setCurrentIndex(max(0,self.agency.findData(agency)))
        self.period.blockSignals(False);self.agency.blockSignals(False);self.render()

    def render(self,*_):
        settlement=self.period.currentData()
        self.rows=list(self.service.development.history(settlement,agency=self.agency.currentData(),changed_only=self.changed.isChecked())) if settlement else []
        data=[]
        for r in self.rows:
            before=json.loads(r['ca_before_json']);after=json.loads(r['ca_after_json']);deltas=json.loads(r['deltas_json'])
            reasons=' / '.join(REASONS.get(x,x) for x in json.loads(r['reasons_json']))
            if not reasons:reasons='기본 상승 판정 적용' if r['bonus_applied'] else '기본 규칙 적용'
            facts=json.loads(r['facts_json'])
            data.append(('',r['name'],ROLES.get(r['role'],r['role']),f'{r["age_before"]} → {r["age_after"]}',
                *[f'{v:+d}' if v else '—' for v in deltas],f'{sum(before)/8:.2f} → {sum(after)/8:.2f}',
                facts.get('actual_games','—'),len(facts.get('appearance_dates',[])) if 'appearance_dates' in facts else '—',reasons))
        self.table.setSortingEnabled(False)
        fill_table(self.table,('사진','이름','주간 적용 신분','나이',*SKILL_NAMES,'평균 전 → 후','실제 출전 경기','출전 일수','정산 안내'),data)
        for i,r in enumerate(self.rows):
            self.table.item(i,0).setData(Qt.ItemDataRole.UserRole,r['person_id'])
            self.table.item(i,0).setIcon(QIcon(self.thumbnails.placeholder))
            for column,value in enumerate(json.loads(r['deltas_json']),4):
                self.table.item(i,column).setForeground(QColor('#367f69' if value>0 else '#af5974' if value<0 else '#8491a5'))
        self.table.setSortingEnabled(True)
        for column,width in enumerate((65,145,140,95,*([80]*8),180,120,95,410)):self.table.setColumnWidth(column,width)
        self.empty.setText(f'{len(self.rows)}명 표시 · 이 화면은 저장된 결과를 읽으며 정산을 재실행하지 않습니다.' if settlement else '아직 정산 기록이 없습니다. 활동 주간을 마치고 다음 월요일이 되면 결과가 저장됩니다.')
        self.queue_photos()

    def queue_photos(self,*_):
        if self.isVisible() and not self.photo_timer.isActive():self.photo_timer.start(25)
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Paint,QEvent.Type.Resize,QEvent.Type.Show):self.queue_photos()
        return super().eventFilter(obj,event)

    def photos(self):
        if not self.isVisible() or not self.table.isVisible() or self.table.isColumnHidden(0):return
        paths={r['person_id']:r['photo_path'] for r in self.rows}
        for row in range(self.table.rowCount()):
            cell=self.table.item(row,0)
            if self.table.isRowHidden(row) or not cell or not self.table.visualItemRect(cell).intersects(self.table.viewport().rect()):continue
            person=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
            if person in paths:
                image=self.thumbnails.get(paths[person])
                if cell.data(Qt.ItemDataRole.UserRole+3)!=image.cacheKey():
                    cell.setData(Qt.ItemDataRole.UserRole+3,image.cacheKey());cell.setIcon(QIcon(image))
