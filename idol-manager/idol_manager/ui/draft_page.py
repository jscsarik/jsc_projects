from .table_widgets import QTableView, QTableWidget
from collections import Counter
import sqlite3

from PySide6.QtCore import QSize, QSortFilterProxyModel, QTimer, Qt, Signal,QModelIndex
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSizePolicy, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget,QSpinBox,
)

from ..draft import DraftError
from .draft_models import BlindCandidateModel, DraftHistoryModel,DraftCandidateProxy,SKILL_NAMES


class PortraitLabel(QLabel):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.original = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(160,160)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #eaf0f8; border-radius: 8px; padding: 6px;")
        self.setText("후보를 선택하세요")

    def show_photo(self, relative_path=None):
        self.original = QPixmap()
        if relative_path:
            reader = QImageReader(str(self.root / relative_path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(size.scaled(720,900,Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if not image.isNull():
                self.original = QPixmap.fromImage(image)
        self._fit()
        if self.original.isNull():
            self.setText("사진을 불러올 수 없습니다" if relative_path else "후보를 선택하세요")

    def _fit(self):
        if not self.original.isNull():
            self.setPixmap(self.original.scaled(self.contentsRect().size(),Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        else:
            self.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.original.isNull():
            self._fit()


def configure_table(table, row_height=34):
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.horizontalHeader().setStretchLastSection(True)


class DraftPage(QWidget):
    changed = Signal()

    def __init__(self, service, thumbnails, parent=None):
        super().__init__(parent)
        self.service, self.session = service, service.draft_session
        self.snapshot = None
        self._busy = False
        self._active = False
        self._paused = False
        self._fast = False
        self._completion_checked = False
        self.ai_timer = QTimer(self)
        self.ai_timer.timeout.connect(self._ai_tick)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26,24,26,20)
        layout.setSpacing(12)
        title = QLabel("최초 드래프트")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("16라운드 스네이크 드래프트 · 현재 능력치는 5개 정수의 추정 범위로 공개됩니다. 범위 상한은 잠재력이 아닙니다."))

        selection = QHBoxLayout()
        self.agency_combo = QComboBox()
        self.agency_combo.setAccessibleName("플레이어 운영 기획사 선택")
        self.save_agency_button = QPushButton("운영 기획사 선택")
        self.save_agency_button.clicked.connect(self._save_agency)
        self.player_label = QLabel("운영 기획사 미선택")
        selection.addWidget(self.agency_combo,1)
        selection.addWidget(self.save_agency_button)
        selection.addWidget(self.player_label,1)
        layout.addLayout(selection)

        summary = QFrame()
        summary.setObjectName("draftSummary")
        summary.setStyleSheet("QFrame#draftSummary { background: #e8f3ef; border-radius: 8px; }")
        summary_layout = QHBoxLayout(summary)
        self.round_label, self.turn_label, self.current_label, self.remaining_label = (QLabel() for _ in range(4))
        for label in (self.player_label,self.current_label):label.setWordWrap(True);label.setMinimumWidth(0)
        for label in (self.round_label,self.turn_label,self.current_label,self.remaining_label):
            label.setWordWrap(True)
            label.setStyleSheet("background: transparent; padding: 7px;")
            summary_layout.addWidget(label,1)
        layout.addWidget(summary)
        actions = QHBoxLayout()
        self.start_button = QPushButton("드래프트 시작")
        self.pick_button = QPushButton("지명하기")
        self.fast_button = QPushButton("다음 내 차례까지 빠르게")
        self.pause_button = QPushButton("AI 일시정지")
        for button, slot in ((self.start_button,self._start),(self.pick_button,self._pick),
                             (self.fast_button,self._fast_forward),(self.pause_button,self._toggle_pause)):
            button.clicked.connect(slot)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.notice = QLabel("기획사를 선택한 뒤 최초 드래프트를 시작해 주세요.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        horizontal = QSplitter(Qt.Orientation.Horizontal)
        left = QSplitter(Qt.Orientation.Vertical)
        candidates_panel = QWidget()
        candidates_layout = QVBoxLayout(candidates_panel)
        candidates_layout.setContentsMargins(0,0,0,0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("후보 이름 검색")
        self.search.setClearButtonEnabled(True)
        candidates_layout.addWidget(self.search)
        filters=QHBoxLayout();self.min_age=QSpinBox();self.max_age=QSpinBox()
        for box in (self.min_age,self.max_age):box.setRange(0,100);box.setSuffix('세')
        self.min_age.setPrefix('최소 ');self.max_age.setPrefix('최대 ');self.max_age.setValue(100)
        self.status_filter=QComboBox()
        for label,value in (('지명 가능','available'),('전체 후보','all'),('지명 완료','picked')):self.status_filter.addItem(label,value)
        for w in (self.min_age,self.max_age,self.status_filter):filters.addWidget(w)
        candidates_layout.addLayout(filters)
        self.candidate_model = BlindCandidateModel(thumbnails,self)
        self.proxy = DraftCandidateProxy(self)
        self.proxy.setSourceModel(self.candidate_model)
        self.proxy.setFilterKeyColumn(1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search.textChanged.connect(self._search)
        self.min_age.valueChanged.connect(self._filter_changed);self.max_age.valueChanged.connect(self._filter_changed)
        self.status_filter.currentIndexChanged.connect(self._filter_changed)
        self.candidate_table = QTableView()
        self.candidate_table.setModel(self.proxy)
        configure_table(self.candidate_table,62)
        self.candidate_table.setIconSize(QSize(44,52))
        self.candidate_table.setSortingEnabled(True)
        self.candidate_table.sortByColumn(1,Qt.SortOrder.AscendingOrder)
        self.candidate_table.setColumnWidth(0,74)
        self.candidate_table.setColumnWidth(1,230)
        self.candidate_table.setColumnWidth(2,70)
        for column in range(3,13):self.candidate_table.setColumnWidth(column,105)
        self.candidate_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.candidate_table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.candidate_table.clicked.connect(self._selection_changed)
        candidates_layout.addWidget(self.candidate_table,1)
        self.search_result = QLabel()
        candidates_layout.addWidget(self.search_result)
        left.addWidget(candidates_panel)
        history_panel = QWidget()
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(0,4,0,0)
        history_layout.addWidget(QLabel("지금까지 지명한 선수"))
        self.history_model = DraftHistoryModel(self)
        self.history_table = QTableView()
        self.history_table.setModel(self.history_model)
        configure_table(self.history_table)
        self.history_table.setColumnWidth(0,90)
        self.history_table.setColumnWidth(1,75)
        self.history_table.setColumnWidth(2,200)
        self.history_table.selectionModel().selectionChanged.connect(self._history_selected)
        history_layout.addWidget(self.history_table)
        left.addWidget(history_panel)
        left.setSizes([370,210])
        horizontal.addWidget(left)
        right = QWidget()
        right.setMinimumWidth(285)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4,0,0,0)
        self.portrait = PortraitLabel(service.image_root)
        right_layout.addWidget(self.portrait,1)
        self.selected_label = QLabel("선택한 후보 없음")
        self.selected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.selected_label)
        self.detail_label=QLabel('현재 능력치 추정 · 잠재력 비공개');self.detail_label.setWordWrap(True);right_layout.addWidget(self.detail_label)
        self.detail_table=QTableWidget(9,2);self.detail_table.setHorizontalHeaderLabels(('능력치','추정 범위'))
        configure_table(self.detail_table,24);self.detail_table.setMinimumHeight(170);self.detail_table.setMaximumHeight(280)
        right_layout.addWidget(self.detail_table)
        self.order_label = QLabel("기획사별 지명 순서 · 인원")
        right_layout.addWidget(self.order_label)
        self.order_table = QTableWidget(10,3)
        self.order_table.setHorizontalHeaderLabels(("순서","기획사","지명"))
        configure_table(self.order_table,26)
        self.order_table.setFixedHeight(316)
        self.order_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.order_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.order_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        right_layout.addWidget(self.order_table)
        horizontal.addWidget(right)
        horizontal.setSizes([770,330])
        layout.addWidget(horizontal,1)
        self.reload()

    def selected_candidate(self):
        index = self.candidate_table.currentIndex()
        if not index.isValid():
            return None
        source = self.proxy.mapToSource(index)
        return self.candidate_model.rows[source.row()] if source.isValid() else None

    def reload(self):
        previous = self.selected_candidate()
        old_history_count = self.history_model.rowCount()
        snapshot = self.session.snapshot()
        self.snapshot = snapshot
        state = snapshot.state
        names = {agency.id:agency.name for agency in snapshot.agencies}
        self.agency_combo.blockSignals(True)
        self.agency_combo.clear()
        self.agency_combo.addItem("운영할 기획사를 선택하세요",None)
        for agency in snapshot.agencies:
            self.agency_combo.addItem(agency.name,agency.id)
        self.agency_combo.setCurrentIndex(max(0,self.agency_combo.findData(snapshot.player_agency_id)))
        self.agency_combo.blockSignals(False)
        player = names.get(snapshot.player_agency_id)
        self.player_label.setText(f"운영 기획사: {player}" if player else "운영 기획사 미선택")
        self.candidate_model.replace(snapshot.candidates if self.status_filter.currentData()=='available' else snapshot.prospects)
        self.history_model.replace(snapshot.history,names)
        if old_history_count != len(snapshot.history):
            self.history_table.scrollToBottom()
        if previous:
            for row, candidate in enumerate(self.candidate_model.rows):
                if candidate.id == previous.id:
                    index = self.proxy.mapFromSource(self.candidate_model.index(row,1))
                    if index.isValid():
                        self.candidate_table.setCurrentIndex(index)
                    break
        self._selection_changed()
        turn = state.next_turn
        round_number = turn.round_number if turn else (16 if state.status == "completed" else None)
        self.round_label.setText(f"라운드 {round_number if round_number else '—'} / 16")
        self.turn_label.setText(f"전체 지명 {turn.pick_number if turn else state.picks_made} / 160\n저장 완료 {state.picks_made}명")
        self.current_label.setText("현재 지명 기획사\n" + (names[turn.agency_id] if turn else ("드래프트 완료" if state.status == "completed" else "시작 전")))
        self.remaining_label.setText(f"남은 후보 {len(snapshot.candidates)}명")
        counts = Counter(pick.agency_id for pick in snapshot.history)
        order = [item for item in snapshot.order if item.round_number == round_number]
        agency_ids = [item.agency_id for item in order] or [agency.id for agency in snapshot.agencies]
        self.order_label.setText(f"{round_number}라운드 순서 · 기획사별 지명 인원" if round_number else "기획사별 지명 인원 · 시작 시 순서 추첨")
        for row, agency_id in enumerate(agency_ids):
            for column, text in enumerate((str(row+1) if order else "—",names[agency_id],f"{counts[agency_id]} / 16")):
                item = QTableWidgetItem(text)
                if agency_id == snapshot.player_agency_id:
                    item.setBackground(Qt.GlobalColor.transparent)
                    font = item.font(); font.setBold(True); item.setFont(font)
                self.order_table.setItem(row,column,item)
        if state.status == "completed":
            if not self._completion_checked:
                self.session.validate_completion()
                self._completion_checked = True
            self.notice.setText("드래프트 완료 · 10개 기획사에 각 16명 배정 · 미지명 40명 보존 · 1·2군 편성 대기")
        elif state.status == "in_progress":
            self._completion_checked = False
            if not player:
                self.notice.setText("진행 중인 저장에 플레이어 기획사 정보가 없습니다. 기획사 변경 없이 저장 상태를 확인해 주세요.")
            elif turn.agency_id == snapshot.player_agency_id:
                self.notice.setText("내 지명 차례입니다. 후보를 선택한 뒤 지명하기를 눌러 주세요.")
            else:
                self.notice.setText("AI 지명 일시정지 중입니다." if self._paused else "AI가 플레이어와 동일한 추정 범위로 평가합니다. 내 차례에 자동으로 멈춥니다.")
        self._controls()
        self._search(self.search.text())
        self._sync_ai()

    def _controls(self):
        if self.snapshot is None:
            return
        state = self.snapshot.state
        not_started = state.status == "not_started"
        has_game = self.service.database.has_game()
        turn = state.next_turn
        player_turn = bool(turn and turn.agency_id == self.snapshot.player_agency_id)
        active = state.status == "in_progress" and bool(self.snapshot.player_agency_id)
        self.agency_combo.setEnabled(not_started and has_game and not self._busy)
        self.save_agency_button.setEnabled(not_started and has_game and not self._busy)
        self.start_button.setEnabled(not_started and has_game and bool(self.snapshot.player_agency_id) and not self._busy)
        candidate=self.selected_candidate()
        self.pick_button.setEnabled(active and player_turn and candidate is not None and candidate.pick_number is None and not self._busy)
        self.fast_button.setEnabled(active and not player_turn and not self._busy)
        self.pause_button.setEnabled(active and not player_turn and not self._busy)
        self.pause_button.setText("AI 계속" if self._paused else "AI 일시정지")

    def _search(self, text):
        self.proxy.setFilterFixedString(text.strip())
        self.search_result.setText(f"검색·필터 결과 {self.proxy.rowCount()}명 / 지명 가능 {len(self.snapshot.candidates) if self.snapshot else 0}명")
        self._controls()

    def _filter_changed(self,*_):
        self.proxy.min_age=self.min_age.value();self.proxy.max_age=self.max_age.value();self.proxy.status=self.status_filter.currentData()
        if self.snapshot:self.candidate_model.replace(self.snapshot.candidates if self.proxy.status=='available' else self.snapshot.prospects)
        self.proxy.invalidate();self._search(self.search.text());self._selection_changed()

    def _selection_changed(self, *_):
        candidate = self.selected_candidate()
        self.portrait.show_photo(candidate.photo_path if candidate else None)
        self.selected_label.setText(f"{candidate.name} · {candidate.age}세" if candidate else "선택한 후보 없음")
        self._detail(candidate)
        self._controls()

    def _detail(self,candidate):
        self.detail_table.clearContents()
        if candidate is None:
            self.detail_label.setText('현재 능력치 추정 · 잠재력 비공개')
            self.detail_table.setHorizontalHeaderLabels(('능력치','추정 범위'))
            return
        revealed=candidate.agency_id==self.snapshot.player_agency_id and candidate.pick_number is not None
        if revealed:
            try:
                _,skills,overall=self.session.revealed_player(candidate.id)
            except DraftError as error:
                self.detail_label.setText(str(error));return
            values=(*skills,overall)
        else:values=(*(str(e) for e in candidate.estimates),candidate.estimated_overall)
        self.detail_label.setText('소속 지명 선수 · 실제 현재 능력치 · 잠재력 비공개' if revealed else '현재 능력치 추정 범위 · 상한은 잠재력이 아닙니다.\n추정 종합: 범위 중간값 8개의 평균')
        self.detail_table.setHorizontalHeaderLabels(('능력치','실제 현재 값' if revealed else '추정 범위'))
        for row,(name,value) in enumerate(zip((*SKILL_NAMES,'종합' if revealed else '추정 종합'),values)):
            self.detail_table.setItem(row,0,QTableWidgetItem(name));self.detail_table.setItem(row,1,QTableWidgetItem(str(value)))

    def _history_selected(self,*_):
        row=self.history_table.currentIndex().row()
        if not self.snapshot or not 0<=row<len(self.history_model.rows):return
        self.candidate_table.setCurrentIndex(QModelIndex())
        self._show_pick(self.history_model.rows[row].person_id)

    def _show_pick(self,person_id):
        candidate=next((p for p in self.snapshot.prospects if p.id==person_id),None)
        if candidate:
            self.portrait.show_photo(candidate.photo_path);self.selected_label.setText(f'{candidate.name} · {candidate.age}세 · {candidate.status}')
            self._detail(candidate)

    def _save_agency(self):
        try:
            agency_id = self.agency_combo.currentData()
            if agency_id is None:
                raise DraftError("운영할 기획사를 선택해 주세요.")
            self.session.select_agency(agency_id)
            self.reload()
            self.changed.emit()
        except (DraftError,sqlite3.Error,OSError) as error:
            self._error(error)

    def _confirm_age_correction(self, issues):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("최초 후보 나이 확인 및 보정 승인")
        dialog.setIcon(QMessageBox.Icon.Warning)
        lines = "\n".join(f"• {person.name}: 16세 → 17세" for person in issues)
        dialog.setText(f"다음 {len(issues)}명의 나이가 드래프트 규칙에 맞지 않습니다.\n\n{lines}\n\n"
                       "변경 전에 현재 DB의 백업을 생성합니다. 승인한 후보의 나이만 변경하고 드래프트를 시작합니다.\n"
                       "능력치·잠재력·후보 ID는 유지됩니다. 취소하면 데이터는 변경되지 않습니다.")
        dialog.setDetailedText("변경 대상 ID\n" + "\n".join(f"{p.name} | {p.id}" for p in issues))
        cancel = dialog.addButton("취소",QMessageBox.ButtonRole.RejectRole)
        approve = dialog.addButton("16세 후보를 17세로 보정하고 시작",QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        return dialog.clickedButton() == approve

    def _start(self):
        self.ai_timer.stop()
        try:
            if self.session.player_agency() is None:
                raise DraftError("운영할 기획사를 먼저 선택해 저장해 주세요.")
            issues = self.service.draft.age_issues()
            if issues:
                if any(person.age != 16 for person in issues):
                    raise DraftError("후보 중 16세 이외의 나이 오류가 있어 자동 보정할 수 없습니다. 규칙은 17~26세입니다.")
                if not self._confirm_age_correction(issues):
                    return
                result = self.service.draft.correct_legacy_ages(approved=True,person_ids=tuple(p.id for p in issues))
                self.notice.setText(f"{len(result.corrected_ids)}명 나이 보정 완료 · 백업: {result.backup_path}")
            self.session.start()
            self._paused = False
            self.reload()
            self.changed.emit()
        except (DraftError,sqlite3.Error,OSError) as error:
            self._error(error)

    def _pick(self):
        candidate = self.selected_candidate()
        if candidate is None or candidate.pick_number is not None or self.snapshot is None or self.snapshot.state.next_turn is None:
            return
        turn = self.snapshot.state.next_turn
        if turn.agency_id != self.snapshot.player_agency_id:
            return
        answer = QMessageBox.question(self,"아이돌 지명 확인",
                                      f"{candidate.name} ({candidate.age}세)를 지명할까요?\n지명 결과는 즉시 저장됩니다.",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.session.pick_player(candidate.id,expected_pick_number=turn.pick_number)
            self.reload()
            self._show_pick(candidate.id)
            self.changed.emit()
        except (DraftError,sqlite3.Error,OSError) as error:
            self._error(error)

    def _fast_forward(self):
        self._fast, self._paused = True, False
        self.reload()

    def _toggle_pause(self):
        self._paused = not self._paused
        self.reload()

    def _sync_ai(self):
        snapshot = self.snapshot
        turn = snapshot.state.next_turn if snapshot else None
        should_run = bool(self._active and not self._busy and not self._paused and snapshot
                          and snapshot.player_agency_id and snapshot.state.status == "in_progress"
                          and turn and turn.agency_id != snapshot.player_agency_id)
        if should_run:
            self.ai_timer.start(15 if self._fast else 350)
        else:
            self.ai_timer.stop()

    def _ai_tick(self):
        if not self._active or self._busy or self._paused:
            self.ai_timer.stop()
            return
        try:
            self.session.pick_ai_turn()
            self.reload()
            self.changed.emit()
        except (DraftError,sqlite3.Error,OSError) as error:
            self._paused = True
            self._error(error)

    def _error(self, error):
        self.ai_timer.stop()
        self._paused = True
        message = str(error) if isinstance(error,DraftError) else (
            "다른 창에서 저장 중이거나 저장 파일에 접근할 수 없습니다. 현재 진행 상태를 다시 확인한 뒤 재시도해 주세요."
            if isinstance(error,sqlite3.Error) else "백업 또는 사진·저장 파일에 접근할 수 없습니다. 폴더 권한과 남은 공간을 확인해 주세요.")
        try:
            self.reload()
        except (DraftError,sqlite3.Error,OSError):
            pass
        self.ai_timer.stop()
        QMessageBox.warning(self,"드래프트 진행 안내",message)

    def set_busy(self, busy):
        self._busy = busy
        self._controls()
        self._sync_ai()

    def shutdown(self):
        self._active = False
        self.ai_timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._active = True
        self.reload()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self,"order_table") and not hasattr(self.order_table,"dock_panel"):
            # Show all ten rows in a large window; retain scrolling at smaller sizes.
            self.order_table.setFixedHeight(max(130,min(260,self.height()-820)))

    def hideEvent(self, event):
        self.shutdown()
        super().hideEvent(event)
