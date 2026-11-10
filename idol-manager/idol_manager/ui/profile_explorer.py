from PySide6.QtCore import Qt,Signal,QSize,QTimer,QEvent
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QPushButton,QTableWidgetItem
from .match_page import make_table,fill_table
from .draft_models import SKILL_NAMES
from .profile_dialog import bounds_text
from .roster_model import STATUS_LABELS


class SortItem(QTableWidgetItem):
    def __lt__(self,other):
        a=self.data(Qt.ItemDataRole.UserRole+1);b=other.data(Qt.ItemDataRole.UserRole+1)
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):return a<b
        return super().__lt__(other)


class ProfileExplorer(QWidget):
    profile_requested=Signal(str)
    compare_requested=Signal(object)
    def __init__(self,service,photos,parent=None):
        super().__init__(parent);self.service=service;self.photos=photos;self.rows=[]
        layout=QVBoxLayout(self);title=QLabel('아이돌 탐색 · 분석');title.setObjectName('title');layout.addWidget(title)
        layout.addWidget(QLabel('이름·사진 클릭: 공통 프로필 / 비교 체크 2명: 나란히 비교 · 미등장 인물은 검색에서 제외'))
        controls=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('모든 기획사 아이돌 이름 검색')
        self.agency=QComboBox();self.agency.addItem('전체 기획사',None)
        for a in service.agencies():self.agency.addItem(a.name,a.id)
        self.role=QComboBox();self.role.addItem('모든 신분',None)
        for key in ('first_team','second_team','trainee','fa','candidate','pro_pending','retired'):self.role.addItem(STATUS_LABELS.get(key,key),key)
        self.injury=QComboBox()
        for label,value in [('부상 전체',None),('부상 있음',True),('부상 없음(공개 선수)',False)]:self.injury.addItem(label,value)
        for w in (self.search,self.agency,self.role,self.injury):controls.addWidget(w)
        self.compare=QPushButton('선택한 2명 비교');self.compare.clicked.connect(self.compare_players);controls.addWidget(self.compare)
        refresh=QPushButton('새로고침');refresh.clicked.connect(self.reload);controls.addWidget(refresh);layout.addLayout(controls)
        self.table=make_table();self.table.setProperty('balancedCompanyColumns',True);self.table.setIconSize(QSize(44,52));self.table.verticalHeader().setDefaultSectionSize(62)
        layout.addWidget(self.table,1);self.notice=QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(150);self.timer.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda *_:self.timer.start())
        for combo in (self.agency,self.role,self.injury):combo.currentIndexChanged.connect(self.reload)
        self.table.itemChanged.connect(self.compare_state)
        self.photo_timer=QTimer(self);self.photo_timer.setSingleShot(True);self.photo_timer.timeout.connect(self.refresh_photos)
        photos.changed.connect(self.queue_photos);self.table.viewport().installEventFilter(self)
        self.table.verticalScrollBar().valueChanged.connect(self.queue_photos)
        self.notice.setText('아이돌 탐색 메뉴에 진입하면 저장된 공개 정보를 불러옵니다.')

    def reload(self,*_):
        from PySide6.QtGui import QIcon
        self.rows=list(self.service.profiles.search(name=self.search.text(),agency=self.agency.currentData(),role=self.role.currentData(),injured=self.injury.currentData()))
        self.table.blockSignals(True);self.table.setSortingEnabled(False)
        data=[]
        for p in self.rows:
            data.append(('', '',p['name'],p['agency_name'] or '소속 없음',STATUS_LABELS.get(p['role'],p['role']),p['age'],
                f'{p["average"]:.2f}' if p['exact'] and p['average'] is not None else bounds_text((sum(a for a,b in p['bounds'])/8,sum(b for a,b in p['bounds'])/8)) if all(a is not None for a,b in p['bounds']) else '미공개',
                *[bounds_text(x) for x in p['bounds']],p['health'] if p['health'] is not None else '미공개',
                p['registration_weeks'] if p['exact'] else '미공개',p['streak'] if p['exact'] else '미공개',
                '미공개' if p['injured'] is None else '부상(휴식)' if p.get('injury_rest') else '부상' if p['injured'] else '없음',p['risk_multiplier'] if p['risk_multiplier'] is not None else '미공개'))
        fill_table(self.table,('비교','사진','이름','기획사','신분','나이','CA / 추정 CA',*SKILL_NAMES,'건강','1군 연속 주차','연속 출전일','부상','현재 위험 배수'),data,
            people=[p['id'] for p in self.rows],profile_columns=(1,2))
        for row,p in enumerate(self.rows):
            item=self.table.item(row,0);item.setData(Qt.ItemDataRole.UserRole,p['id']);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked)
            self.table.item(row,1).setIcon(QIcon(self.photos.placeholder))
            sorts={5:p['age'],6:p['average'] if p['average'] is not None else -1,15:p['health'] if p['health'] is not None else -1,16:p['registration_weeks'] or 0,17:p['streak'] or 0,19:p['risk_multiplier'] if p['risk_multiplier'] is not None else -1}
            sorts.update({7+i:(a+b)/2 if a is not None else -1 for i,(a,b) in enumerate(p['bounds'])})
            for col,value in sorts.items():
                old=self.table.item(row,col);replacement=SortItem();replacement.setData(Qt.ItemDataRole.DisplayRole,old.data(Qt.ItemDataRole.DisplayRole));replacement.setData(Qt.ItemDataRole.UserRole+1,value);self.table.setItem(row,col,replacement)
        self.table.setSortingEnabled(True);self.table.blockSignals(False)
        for i in range(self.table.columnCount()):self.table.setColumnWidth(i,180 if i in (2,3) else 120 if i==6 else 90)
        self.notice.setText(f'{len(self.rows)}명 · 후보 CA/능력치 정렬에는 공개 추정 범위 중앙값만 사용합니다. 비공개 건강·부상 값은 정렬에 사용하지 않습니다.')
        self.compare_state()
        self.queue_photos()

    def queue_photos(self,*_):
        if self.isVisible() and not self.photo_timer.isActive():self.photo_timer.start(25)
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Paint,QEvent.Type.Resize,QEvent.Type.Show):self.queue_photos()
        return super().eventFilter(obj,event)

    def selected(self):return [self.table.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(self.table.rowCount()) if self.table.item(i,0).checkState()==Qt.CheckState.Checked]
    def compare_state(self,*_):self.compare.setEnabled(len(self.selected())==2)
    def compare_players(self):
        people=self.selected()
        if len(people)==2:self.compare_requested.emit(people)
    def refresh_photos(self):
        if not self.isVisible() or not self.table.isVisible() or self.table.isColumnHidden(1):return
        from PySide6.QtGui import QIcon
        paths={p['id']:p['photo_path'] for p in self.rows}
        blocked=self.table.blockSignals(True)
        try:
            for i in range(self.table.rowCount()):
                if self.table.isRowHidden(i):continue
                cell=self.table.item(i,1)
                if not cell or not self.table.visualItemRect(cell).intersects(self.table.viewport().rect()):continue
                person=self.table.item(i,0).data(Qt.ItemDataRole.UserRole)
                if person in paths:
                    image=self.photos.get(paths[person])
                    if cell.data(Qt.ItemDataRole.UserRole+3)!=image.cacheKey():
                        cell.setData(Qt.ItemDataRole.UserRole+3,image.cacheKey());cell.setIcon(QIcon(image))
        finally:self.table.blockSignals(blocked)
