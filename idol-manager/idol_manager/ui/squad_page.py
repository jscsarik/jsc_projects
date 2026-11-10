from .table_widgets import QTableView
from collections import Counter
import sqlite3

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,QScrollArea,QTabBar,
)

from ..squads import SquadError
from ..game_clock import is_monday
from .draft_page import configure_table
from .squad_model import SquadFilter, SquadModel


class FormationSignals(QObject):
    finished = Signal(str)


class FormationJob(QRunnable):
    def __init__(self, squads, agency_id, identities):
        super().__init__()
        self.squads,self.agency_id,self.identities = squads,agency_id,identities
        self.signals = FormationSignals()

    def run(self):
        try:
            self.squads.confirm_initial(self.identities,expected_agency_id=self.agency_id)
        except Exception as error:
            self.signals.finished.emit(str(error))
        else:
            self.signals.finished.emit("")


class SquadPage(QWidget):
    busy_changed = Signal(bool)
    state_changed = Signal()

    def __init__(self, service, thumbnails, parent=None):
        super().__init__(parent)
        self.service,self.squads = service,service.squads
        self.snapshot = None
        self.job = None
        self._external_busy = False
        self._closing = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.content=QWidget();self.content.setMinimumHeight(800)
        self.page_scroll=QScrollArea();self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setProperty('responsivePageScroll',True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_scroll.setWidget(self.content);outer.addWidget(self.page_scroll)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(26,24,26,20)
        layout.setSpacing(12)
        title = QLabel("선수단 관리")
        title.setObjectName("title")
        layout.addWidget(title)
        header = QHBoxLayout()
        self.logo = QLabel("로고 없음")
        self.logo.setFixedSize(100,64)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.agency_label = QLabel("운영 기획사 미선택")
        self.agency_label.setWordWrap(True);self.agency_label.setMinimumWidth(0)
        self.agency_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.date_label = QLabel()
        header.addWidget(self.logo)
        header.addWidget(self.agency_label,1)
        header.addWidget(self.date_label)
        layout.addLayout(header)
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.squad_tabs=QTabBar()
        self.squad_tabs.addTab('프로 선수단');self.squad_tabs.addTab('연습생')
        self.squad_tabs.setExpanding(False)
        layout.addWidget(self.squad_tabs)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("소속 선수 이름 검색")
        self.search.setClearButtonEnabled(True)
        self.filter_combo = QComboBox()
        for name,key in (("프로 전체","pro"),("1군","first_team"),("2군","second_team"),("연습생 · 별도 선수단","trainee")):
            self.filter_combo.addItem(name,key)
        self.selection_label = QLabel("1군 선택 0 / 5명")
        self.confirm_button = QPushButton("1군 5명 확정 · AI 자동 편성")
        self.confirm_button.clicked.connect(self._confirm_initial)
        tools.addWidget(self.search,1)
        tools.addWidget(self.filter_combo)
        tools.addWidget(self.selection_label)
        tools.addWidget(self.confirm_button)
        layout.addLayout(tools)
        self.model = SquadModel(thumbnails,self)
        self.proxy = SquadFilter(self)
        self.proxy.setSourceModel(self.model)
        self.search.textChanged.connect(self.proxy.set_query)
        self.filter_combo.currentIndexChanged.connect(self._filter_changed)
        self.squad_tabs.currentChanged.connect(self._squad_tab_changed)
        self.model.selection_changed.connect(self._controls)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        configure_table(self.table,62)
        self.table.setIconSize(QSize(44,52))
        self.table.setStyleSheet('QTableView {font-size:14px;} QHeaderView::section {font-size:13px;}')
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(2,Qt.SortOrder.AscendingOrder)
        for column in range(self.model.columnCount()):
            self.table.setColumnWidth(column,150 if column==2 else (94 if column==4 else 72))
        for column in range(15,self.model.columnCount()):self.table.setColumnWidth(column,132)
        self.table.selectionModel().selectionChanged.connect(self._controls)
        layout.addWidget(self.table,1)

        lower = QHBoxLayout()
        moves = QGroupBox("1군·2군 교체 · 월요일 / 최종전 금요일")
        self.moves_group=moves
        move_layout = QVBoxLayout(moves)
        swap_row = QHBoxLayout()
        self.first_combo,self.second_combo = QComboBox(),QComboBox()
        self.swap_button = QPushButton("두 선수 맞교환")
        self.swap_button.clicked.connect(self._swap)
        swap_row.addWidget(self.first_combo,1)
        swap_row.addWidget(self.second_combo,1)
        swap_row.addWidget(self.swap_button)
        move_layout.addLayout(swap_row)
        move_row = QHBoxLayout()
        self.promote_button = QPushButton("선택 선수 → 1군")
        self.demote_button = QPushButton("선택 선수 → 2군")
        self.promote_button.clicked.connect(lambda: self._move("first_team"))
        self.demote_button.clicked.connect(lambda: self._move("second_team"))
        move_row.addWidget(self.promote_button)
        move_row.addWidget(self.demote_button)
        move_layout.addLayout(move_row)
        self.move_notice=QLabel('일반 교체는 선수당 같은 월요일에 한 번만 가능합니다.');self.move_notice.setWordWrap(True);move_layout.addWidget(self.move_notice)
        lower.addWidget(moves,1)
        leaders = QGroupBox("리더 지정 · 월요일 / 최종전 금요일")
        self.leaders_group=leaders
        leaders_layout = QVBoxLayout(leaders)
        self.leader_notice = QLabel()
        self.leader_notice.setWordWrap(True)
        leaders_layout.addWidget(self.leader_notice)
        self.first_leader_combo,self.second_leader_combo = QComboBox(),QComboBox()
        self.first_leader_button,self.second_leader_button = QPushButton("1군 리더 저장"),QPushButton("2군 리더 저장")
        for combo,button,squad in ((self.first_leader_combo,self.first_leader_button,"first_team"),
                                   (self.second_leader_combo,self.second_leader_button,"second_team")):
            row = QHBoxLayout()
            row.addWidget(combo,1)
            row.addWidget(button)
            button.clicked.connect(lambda checked=False,s=squad: self._leader(s))
            leaders_layout.addLayout(row)
        lower.addWidget(leaders,1)
        layout.addLayout(lower)
        self.action_status = QLabel()
        self.action_status.setWordWrap(True)
        layout.addWidget(self.action_status)
        self.first_combo.currentIndexChanged.connect(self._controls)
        self.second_combo.currentIndexChanged.connect(self._controls)
        self.reload()

    def selected_member(self):
        index = self.table.currentIndex()
        source = self.proxy.mapToSource(index)
        return self.model.rows[source.row()] if source.isValid() else None

    def _squad_tab_changed(self,index):
        target='trainee' if index==1 else 'pro'
        self.filter_combo.setCurrentIndex(self.filter_combo.findData(target))
        self._update_squad_view()

    def _filter_changed(self,*_):
        target=self.filter_combo.currentData()
        self.proxy.set_squad(target)
        self.squad_tabs.blockSignals(True)
        self.squad_tabs.setCurrentIndex(1 if target=='trainee' else 0)
        self.squad_tabs.blockSignals(False)
        self._update_squad_view()

    def _update_squad_view(self):
        if not hasattr(self,'leaders_group') or self.snapshot is None:return
        trainee=self.squad_tabs.currentIndex()==1
        for widget in (self.moves_group,self.leaders_group,self.selection_label,self.confirm_button,self.filter_combo):
            widget.setVisible(not trainee)
        required=[0,2] if self.snapshot.ready and not self.snapshot.initialized and not trainee else []
        self.table.setProperty('requiredVisibleColumns',required)
        self.table.setColumnHidden(0,not required)
        for column in (15,16):self.table.setColumnHidden(column,trainee)
        self._controls()
        if trainee:self.notice.setText('확정 영입된 소속 연습생입니다. 프로 16명과 별도로 관리하며, 정식 데뷔 전에는 1군·2군에 편성하지 않습니다.')

    def reload(self):
        snapshot = self.squads.snapshot()
        self.snapshot = snapshot
        self.changed_today=self.squads.normal_changes_today()
        conditions=self.squads.condition_summaries([m.id for m in snapshot.members])
        self.model.replace(snapshot.members,snapshot.ready and not snapshot.initialized and not self.is_busy(),conditions)
        self.table.setProperty('requiredVisibleColumns',[0,2] if snapshot.ready and not snapshot.initialized else [])
        self.table.setColumnHidden(0,snapshot.initialized or not snapshot.ready)
        if snapshot.agency:
            self.agency_label.setText(snapshot.agency.name)
            pixmap = QPixmap(str(self.service.image_root/snapshot.agency.logo_path))
            if pixmap.isNull():
                self.logo.setText("로고 없음")
            else:
                self.logo.setPixmap(pixmap.scaled(100,64,Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
        else:
            self.agency_label.setText("운영 기획사 미선택")
            self.logo.clear()
        day = snapshot.management_date
        self.date_label.setText(str(day) if day is not None else "게임 날짜 없음")
        counts = Counter(member.squad for member in snapshot.members)
        names = {member.id:member.name for member in snapshot.members}
        leaders = dict(snapshot.leaders)
        pro = sum(counts.get(s,0) for s in ("pro_pending","first_team","second_team"))
        self.squad_tabs.setTabText(0,f'프로 선수단 ({pro}명)')
        self.squad_tabs.setTabText(1,f"연습생 ({counts['trainee']}명)")
        self.summary.setText(f"프로 {pro} / 16명  ·  1군 {counts['first_team']} / 5명  ·  2군 {counts['second_team']} / 11명"
                             f"  ·  연습생 {counts['trainee']}명 (별도)\n"
                             f"1군 리더: {names.get(leaders.get('first_team'),'미지정')}  ·  "
                             f"2군 리더: {names.get(leaders.get('second_team'),'미지정')}")
        if not snapshot.ready:
            self.notice.setText(snapshot.reason)
        elif not snapshot.initialized:
            self.notice.setText("최초 선수단 미편성: 계약된 소속 프로 중 정확히 5명을 체크해 주세요. "
                                "월요일 또는 창단 준비 일요일에 확정하면 나머지 보유 프로와 AI 9개 기획사가 자동 편성됩니다."
                                + (" 현재는 월요일이 아닙니다." if not is_monday(day) else ""))
        elif day is not None and day.is_preparation and not day.is_founding and counts['first_team']<5:
            self.notice.setText('시즌 준비: 2군 선수를 선택하고 「선택 선수 → 1군」으로 빈자리를 채워 주세요. 확보한 2군 자리에 연습생 데뷔가 가능합니다. 일반 맞교환·강등은 기존 관리일에만 가능합니다.')
        elif day is not None and not is_monday(day) and self.squads.change_reason():
            self.notice.setText("현재는 월요일이 아닙니다. 일반 교체·리더 변경은 제한되며, 준비·중간 정비 기간의 빈 리더 자리는 지정할 수 있습니다.")
        elif day is not None and day.is_founding and day.weekday()==6 and len(snapshot.leaders)<2:
            self.notice.setText('창단 준비 일요일: 최초 편성과 최초 리더 지정을 완료해 주세요. 일반 선수 교체는 월요일에만 가능합니다.')
        elif counts['first_team']<5:
            self.notice.setText("1군 인원이 부족합니다. 1군에 자리가 있으면 2군 선수를 올릴 수 있습니다.")
        else:
            self.notice.setText("1군 5명·2군 11명일 때는 두 선수를 맞교환하세요. 선수단을 떠난 리더 지정은 자동으로 해제됩니다.")
        for combo,squad,with_empty in ((self.first_combo,"first_team",False),(self.second_combo,"second_team",False),
                                       (self.first_leader_combo,"first_team",True),(self.second_leader_combo,"second_team",True)):
            combo.clear()
            if with_empty:
                combo.addItem("리더 미지정",None)
            for member in snapshot.members:
                if member.squad==squad:
                    combo.addItem(member.name,member.id)
            if with_empty:
                combo.setCurrentIndex(max(0,combo.findData(leaders.get(squad))))
        self._controls()
        self._update_squad_view()

    def is_busy(self):
        return self._external_busy or self.job is not None

    def _controls(self,*_):
        if self.snapshot is None or not hasattr(self,"swap_button"):
            return
        snapshot = self.snapshot
        monday = is_monday(snapshot.management_date) or bool(snapshot.management_date and snapshot.management_date.is_founding and snapshot.management_date.weekday()==6)
        busy = self.is_busy()
        self.model.editable = snapshot.ready and not snapshot.initialized and not busy and self.squad_tabs.currentIndex()==0
        self.selection_label.setText(f"1군 선택 {len(self.model.selected_ids)} / 5명" if not snapshot.initialized else "최초 편성 완료")
        contract_reason=self.squads.initial_contract_reason() if snapshot.agency and not snapshot.initialized else ''
        if contract_reason:self.notice.setText(contract_reason)
        self.confirm_button.setToolTip(contract_reason or '월요일 또는 창단 일요일에 소속 프로 16명 중 5명을 1군으로 확정합니다.')
        self.confirm_button.setEnabled(snapshot.ready and not snapshot.initialized and monday and len(self.model.selected_ids)==5 and not busy and not contract_reason)
        can_change = snapshot.ready and snapshot.initialized and not self.squads.change_reason() and not busy
        self.swap_button.setEnabled(can_change and self.first_combo.count()>0 and self.second_combo.count()>0)
        for widget in (self.first_combo,self.second_combo,self.first_leader_combo,self.second_leader_combo,
                       self.first_leader_button,self.second_leader_button):
            widget.setEnabled(can_change)
        for squad,combo,button in (('first_team',self.first_leader_combo,self.first_leader_button),('second_team',self.second_leader_combo,self.second_leader_button)):
            block=self._leader_block_reason(squad);combo.setEnabled(not block);button.setEnabled(not block)
            combo.setToolTip(block or '해당 선수단에서 리더를 선택해 저장하세요.');button.setToolTip(combo.toolTip())
        reason = self._leader_block_reason()
        self.leader_notice.setText(reason or ("최초 편성 완료 · 리더 미지정: 각 선수단에서 리더를 선택하고 저장하세요."
                                             if len(snapshot.leaders)<2 else "최초 편성·리더 지정 완료 · 허용된 관리일 변경 가능"))
        member = self.selected_member()
        counts = Counter(m.squad for m in snapshot.members)
        promotion_reason=self.squads.promotion_reason()
        can_promote=snapshot.ready and snapshot.initialized and not promotion_reason and not busy
        self.promote_button.setEnabled(can_promote and member is not None and member.squad=="second_team" and counts['first_team']<5)
        self.promote_button.setToolTip(promotion_reason or '선택한 2군 선수로 1군의 빈자리를 채웁니다. 부상 복귀 제한은 유지됩니다.')
        self.demote_button.setEnabled(can_change and member is not None and member.squad=="first_team" and counts['second_team']<11)
        locked=getattr(self,'changed_today',set())
        swap_locked=bool({self.first_combo.currentData(),self.second_combo.currentData()}&locked)
        reason='오늘 이미 변경한 선수입니다. 같은 월요일에는 다시 일반 교체할 수 없습니다.'
        if swap_locked:self.swap_button.setEnabled(False)
        self.swap_button.setToolTip(reason if swap_locked else '각 선수는 같은 월요일에 한 번만 일반 교체할 수 있습니다.')
        if member and member.id in locked:
            self.promote_button.setEnabled(False);self.demote_button.setEnabled(False)
        self.move_notice.setText(reason if swap_locked or (member and member.id in locked) else '일반 교체는 선수당 같은 월요일에 한 번만 가능합니다. 부상 교체·특별전은 별도 처리합니다.')

    def _confirm_initial(self):
        if self.is_busy() or not self.snapshot or not self.snapshot.agency:
            return
        identities = tuple(sorted(self.model.selected_ids))
        if len(identities)!=5:
            self._error(SquadError("정확히 5명을 선택해 주세요."))
            return
        names = [m.name for m in self.snapshot.members if m.id in identities]
        answer = QMessageBox.question(self,"최초 선수단 편성 확정",
            "1군으로 다음 5명을 확정할까요?\n\n"+"\n".join(names)+
            "\n\n나머지 11명은 2군으로 배정하고, AI 9개 기획사도 자동 편성합니다.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:
            return
        self.job = FormationJob(self.squads,self.snapshot.agency.id,identities)
        self.job.signals.finished.connect(self._formation_finished)
        self.action_status.setText("선수단과 AI 9개 기획사를 편성하고 저장하는 중입니다…")
        self._controls()
        self.busy_changed.emit(True)
        self.pool.start(self.job)

    def _formation_finished(self,error):
        self.job = None
        if self._closing:
            return
        self.busy_changed.emit(False)
        if error:
            self._error(SquadError(error))
        else:
            self.reload()
            self.action_status.setText("최초 편성을 저장했습니다. AI 9개 기획사의 편성과 리더 지정도 완료했습니다.")
            self.state_changed.emit()

    def _run(self,operation,message):
        try:
            operation()
            self.reload()
            self.action_status.setText(message)
            self.state_changed.emit()
        except (SquadError,sqlite3.Error,OSError) as error:
            self._error(error)

    def _swap(self):
        first,second = self.first_combo.currentData(),self.second_combo.currentData()
        revision = self.snapshot.revision
        answer = QMessageBox.question(self,"1군·2군 맞교환",
            f"{self.first_combo.currentText()}와 {self.second_combo.currentText()}를 맞교환할까요?\n"
            "선수단을 떠나는 리더의 지정은 해제됩니다.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:
            self._run(lambda:self.squads.swap(first,second,expected_revision=revision),"맞교환을 저장했습니다. 필요한 리더를 다시 지정해 주세요.")

    def _move(self,target):
        member = self.selected_member()
        if member is None:
            return
        revision = self.snapshot.revision
        answer = QMessageBox.question(self,"선수단 이동 확인",f"{member.name}를 {'1군' if target=='first_team' else '2군'}으로 이동할까요?",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:
            self._run(lambda:self.squads.move(member.id,target,expected_revision=revision),"선수단 이동을 저장했습니다.")

    def _leader(self,squad):
        reason = self._leader_block_reason(squad)
        if reason:
            self._error(SquadError(reason))
            return
        combo = self.first_leader_combo if squad=="first_team" else self.second_leader_combo
        identity,revision = combo.currentData(),self.snapshot.revision
        agency_id = self.snapshot.agency.id
        self._run(lambda:self.squads.set_leader(squad,identity,expected_revision=revision,
                                              expected_agency_id=agency_id),"리더 지정을 저장했습니다.")

    def _leader_block_reason(self,squad=None):
        snapshot = self.snapshot
        if snapshot is None or snapshot.agency is None:
            return "플레이어 기획사가 선택되지 않았습니다."
        if self.is_busy():
            return "저장 작업이 진행 중입니다. 완료 후 리더를 지정해 주세요."
        if not snapshot.ready:
            return snapshot.reason
        reasons = []
        if not snapshot.initialized:
            reasons.append("1군 최초 편성이 완료되지 않았습니다.")
        if snapshot.management_date is None:
            reasons.append("저장된 게임 날짜가 없습니다.")
        else:
            checks=[self.squads.leader_change_reason(s) for s in ((squad,) if squad else ('first_team','second_team'))]
            if all(checks):reasons.append(checks[0])
        return " ".join(reasons)

    def _error(self,error):
        try:
            self.reload()
        except (SquadError,sqlite3.Error,OSError,ValueError):
            pass
        message = str(error) if isinstance(error,SquadError) else "저장 중 충돌이 발생했습니다. 명단을 다시 불러온 뒤 재시도해 주세요."
        QMessageBox.warning(self,"선수단 관리 안내",message)

    def set_busy(self,busy):
        self._external_busy = busy
        self._controls()

    def shutdown(self):
        self._closing = True
        self.pool.waitForDone()
        self.job = None

    def showEvent(self,event):
        super().showEvent(event)
        self._closing = False
        self.reload()
