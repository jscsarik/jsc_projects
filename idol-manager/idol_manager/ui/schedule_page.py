from .table_widgets import QTableView
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from ..game_clock import WEEKDAY_NAMES
from .draft_page import configure_table

STATUS_NAMES={"scheduled":"예정","in_progress":"진행 중","completed":"완료"}


class ScheduleModel(QAbstractTableModel):
    HEADERS=("정규 주차","요일","당일 순서","참가 기획사","경기 콘텐츠","주요 능력치","출전 인원","유형","경기 번호","진행 상태","경기 ID")

    def __init__(self,parent=None):
        super().__init__(parent)
        self.rows=[]

    def replace(self,rows):
        self.beginResetModel(); self.rows=list(rows); self.endResetModel()

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if orientation==Qt.Orientation.Horizontal and role==Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.rows):
            return None
        row=self.rows[index.row()]
        if role==Qt.ItemDataRole.DisplayRole:
            return (row.week,WEEKDAY_NAMES[row.weekday],f"{row.day_order}차 경기" if row.day_order else "특별전",
                    row.agencies,row.content,row.main_abilities,row.participants,row.match_type,
                    row.match_order if row.match_order else "—",STATUS_NAMES.get(row.status,row.status),row.id)[index.column()]
        if role==Qt.ItemDataRole.ToolTipRole and index.column()==10:
            return row.id
        return None


class DatePreviewDialog(QDialog):
    """Pure date arithmetic: deliberately has no CalendarService or DB handle."""
    def __init__(self,origin,parent=None):
        super().__init__(parent)
        self.setWindowTitle("테스트용 날짜 계산 · 저장 안 함")
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel("미리보기만 계산합니다. 게임 날짜와 경기 상태는 바뀌지 않습니다."))
        layout.addWidget(QLabel(f"기준: {origin}"))
        self.days=QSpinBox()
        self.days.setRange(0,217000)
        self.days.setSuffix("일 뒤")
        self.result=QLabel(str(origin))
        self.days.valueChanged.connect(lambda value:self.result.setText(str(origin.after(value))))
        layout.addWidget(self.days)
        layout.addWidget(self.result)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(600,220)


class SchedulePage(QWidget):
    def __init__(self,service,parent=None):
        super().__init__(parent)
        self.service=service
        self.calendar=service.calendar
        self.mode="current"
        self._updating=False
        layout=QVBoxLayout(self)
        layout.setContentsMargins(26,24,26,20)
        title=QLabel("경기 일정")
        title.setObjectName("title")
        layout.addWidget(title)
        self.date_label=QLabel()
        self.date_label.setObjectName("summary")
        self.date_label.setWordWrap(True)
        layout.addWidget(self.date_label)
        self.notice=QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        controls=QHBoxLayout()
        self.season_combo=QComboBox()
        self.week_combo=QComboBox()
        self.week_combo.addItem("주차 선택",None)
        for week in range(1,25):
            self.week_combo.addItem(f"정규 {week}주차",week)
        self.agency_combo=QComboBox()
        self.current_button=QPushButton("이번 주")
        self.all_button=QPushButton("전체 24주")
        self.preview_button=QPushButton("테스트용 날짜 미리보기")
        for widget in (self.season_combo,self.current_button,self.all_button,self.week_combo,self.agency_combo,self.preview_button):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.current_button.clicked.connect(self._current)
        self.all_button.clicked.connect(self._all)
        self.week_combo.currentIndexChanged.connect(self._week)
        self.season_combo.currentIndexChanged.connect(self._season)
        self.agency_combo.currentIndexChanged.connect(self._rows)
        self.preview_button.clicked.connect(self._preview)
        self.model=ScheduleModel(self)
        self.table=QTableView()
        self.table.setProperty('balancedCompanyColumns',True)
        self.table.setModel(self.model)
        configure_table(self.table,38)
        for column,width in enumerate((90,80,110,290,200,170,180,85,90,90,280)):
            self.table.setColumnWidth(column,width)
        layout.addWidget(self.table,1)
        self.count_label=QLabel()
        layout.addWidget(self.count_label)
        self.special_button=QPushButton('특별전 화면 열기');layout.addWidget(self.special_button)
        layout.addWidget(QLabel("특별전은 정규 585경기에서 제외됩니다. 특별전 메뉴에서 출전자와 결과를 확인하세요."))
        self.reload()

    def reload(self):
        self.calendar.initialize()
        state=self.calendar.state()
        old_season=self.season_combo.currentData()
        old_agency=self.agency_combo.currentData()
        self._updating=True
        self.season_combo.clear()
        for season in self.calendar.seasons():
            self.season_combo.addItem(f"시즌 {season}",season)
        target=old_season or (state.date.season if state.date else 1)
        self.season_combo.setCurrentIndex(max(0,self.season_combo.findData(target)))
        self.agency_combo.clear()
        self.agency_combo.addItem("전체 기획사",None)
        for agency in self.service.agencies():
            self.agency_combo.addItem(agency.name,agency.id)
        self.agency_combo.setCurrentIndex(max(0,self.agency_combo.findData(old_agency)))
        if self.mode=="current" and state.date and state.date.is_regular:
            self.week_combo.setCurrentIndex(self.week_combo.findData(state.date.week))
            self.season_combo.setCurrentIndex(self.season_combo.findData(state.date.season))
        self._updating=False
        self.date_label.setText(str(state.date) if state.date else "새 게임을 먼저 생성해 주세요.")
        self.notice.setText(state.reason if not state.schedule_ready else
            f"정규 585경기 · 기획사당 117경기 · 특별전 6회 · 현재까지 미처리 {state.unprocessed_count}건\n"
            "상대와 콘텐츠는 해당 주 월요일에 공개됩니다. 범위형 출전 인원은 경기 당일 양측 동일하게 확정됩니다.")
        self.preview_button.setEnabled(state.date is not None)
        self._rows()

    def _rows(self,*_):
        if self._updating:
            return
        season=self.season_combo.currentData() or 1
        rows=self.calendar.entries(season,week=self.week_combo.currentData() if self.mode=="week" else None,
                                   agency_id=self.agency_combo.currentData(),current_week=self.mode=="current")
        self.model.replace(rows)
        regular=sum(row.match_type=="정규" for row in rows)
        self.count_label.setText(f"{'이번 주' if self.mode=='current' else ('전체 24주' if self.mode=='all' else '선택 주차')} · 정규 {regular}경기 · 특별전 {len(rows)-regular}회")

    def _current(self):
        self.mode="current"; self.reload()

    def _all(self):
        self.mode="all"
        self._updating=True
        self.week_combo.setCurrentIndex(0)
        self._updating=False
        self._rows()

    def _week(self,*_):
        if not self._updating:
            self.mode="week" if self.week_combo.currentData() else "all"
            self._rows()

    def _season(self,*_):
        if not self._updating:
            self._all()

    def _preview(self):
        day=self.calendar.state().date
        if day:
            DatePreviewDialog(day,self).exec()

    def showEvent(self,event):
        super().showEvent(event)
        self.reload()
