from .table_widgets import QTableView
from PySide6.QtCore import QObject, QRunnable, QSize, QSortFilterProxyModel, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)
import sqlite3

from ..service import GameService
from .roster_model import RosterModel
from .thumbnails import ThumbnailCache
from .draft_page import DraftPage
from .squad_page import SquadPage
from .schedule_page import SchedulePage
from .match_page import MatchPage
from .special_page import SpecialPage
from .finals_page import FinalsPage
from .development_page import DevelopmentPage
from .bgm_controls import BgmControls,MusicToast
from ..bgm import BgmManager
from ..calendar_service import CalendarError
from ..game_clock import GameDate


class GameSignals(QObject):
    finished = Signal(str)


class NewGameJob(QRunnable):
    def __init__(self, service):
        super().__init__()
        self.service = service
        self.signals = GameSignals()

    def run(self):
        try:
            self.service.new_game()
        except Exception as error:
            self.signals.finished.emit(str(error))
        else:
            self.signals.finished.emit("")


class CompetitionAIJob(NewGameJob):
    def run(self):
        from ..competition_actions import play_pending_ai
        try:play_pending_ai(self.service)
        except Exception as error:self.signals.finished.emit(str(error))
        else:self.signals.finished.emit('')


class MainWindow(QMainWindow):
    closed=Signal()
    menu_requested=Signal()
    def __init__(self, service: GameService, *, bgm=None,slot_mode=False,before_close=None):
        super().__init__()
        self.slot_mode=slot_mode
        self.before_close=before_close
        self.returning_to_menu=False
        self.service = service
        self.job = None
        self._closing = False
        self.pool = QThreadPool(self)
        self.bgm=bgm or BgmManager(service.root,service.settings_dir/'bgm_settings.json',self,music_folder=service.user_music_dir)
        self.setWindowTitle("IDOL Manager")
        self.resize(900, 1560)
        self.setMinimumSize(700, 700)
        self.thumbnails = ThumbnailCache(service.image_root, service.cache_dir / "thumbnails", self)
        self.model = RosterModel(self.thumbnails, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 16, 10, 12)
        side.setSpacing(6)
        brand = QLabel("IDOL ♡\nMANAGER")
        brand.setObjectName("brand")
        from .theme_manager import settings_button
        side.addWidget(brand)
        self.game_date_label = QLabel()
        self.game_date_label.setWordWrap(True)
        self.game_date_label.setObjectName("game_date")
        self.game_date_label.setAccessibleName("현재 게임 날짜")
        self.day_button = QPushButton("하루 진행  →")
        self.day_button.setObjectName("advanceDay")
        self.day_button.clicked.connect(self.advance_day)
        self.recovery_button = QPushButton("초기 날짜 복구")
        self.recovery_button.clicked.connect(self.recover_initial_date)
        side.addSpacing(6)
        self.roster_menu = QPushButton("아이돌 명단")
        self.draft_menu = QPushButton("드래프트")
        self.squad_menu = QPushButton("선수단 관리")
        self.schedule_menu = QPushButton("경기 일정")
        self.match_menu = QPushButton("정규 경기")
        self.special_menu = QPushButton("특별전")
        self.finals_menu = QPushButton('포스트시즌')
        self.development_menu=QPushButton('성장 · 노화 · 훈련');self.development_menu.clicked.connect(self.show_development)
        self.training_menu=QPushButton('훈련',self);self.training_menu.clicked.connect(self.show_training)
        self.training_menu.hide()
        self.market_menu=QPushButton('선수 시장');self.market_menu.clicked.connect(self.show_market)
        self.awards_menu=QPushButton('시상식');self.awards_menu.clicked.connect(self.show_awards)
        self.annual_menu=QPushButton('통합 드래프트');self.annual_menu.clicked.connect(self.show_annual)
        self.records_menu=QPushButton('기록실');self.records_menu.clicked.connect(self.show_records)
        self.finance_menu=QPushButton('기획사 재정');self.finance_menu.clicked.connect(self.show_finance)
        self.explorer_menu=QPushButton('아이돌 탐색 · 분석');self.explorer_menu.clicked.connect(self.show_explorer)
        self.finals_menu.clicked.connect(self.show_finals)
        self.roster_menu.clicked.connect(self.show_roster)
        self.draft_menu.clicked.connect(self.show_draft_menu)
        self.squad_menu.clicked.connect(self.show_squads)
        self.schedule_menu.clicked.connect(self.show_schedule)
        self.match_menu.clicked.connect(self.show_matches)
        self.special_menu.clicked.connect(self.show_specials)
        self.roster_menu.hide()
        self.annual_menu.hide()
        self.midseason_menu=QPushButton('중간점검');self.midseason_menu.clicked.connect(lambda:self.show_season_hub(False))
        self.wrapup_menu=QPushButton('시즌 마무리');self.wrapup_menu.clicked.connect(lambda:self.show_season_hub(True))
        nav_body=QWidget();nav_layout=QVBoxLayout(nav_body);nav_layout.setContentsMargins(0,0,0,0);nav_layout.setSpacing(6)
        self.nav_scroll=QScrollArea();self.nav_scroll.setWidgetResizable(True);self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.nav_scroll.setWidget(nav_body);side.addWidget(self.nav_scroll,1)
        self.nav_sections=(
            ('아이돌',(self.explorer_menu,self.market_menu,self.draft_menu)),
            ('매니저',(self.squad_menu,self.schedule_menu,self.development_menu,self.finance_menu)),
            ('경기',(self.match_menu,self.special_menu,self.finals_menu)),
            ('시즌 관리',(self.midseason_menu,self.wrapup_menu)),
            ('연말시즌',(self.awards_menu,)),
        )
        for name,buttons in self.nav_sections:
            group=QFrame();group.setObjectName('navGroup')
            group.setStyleSheet('QFrame#navGroup {background:#faf4fd;border:1px solid #e2d4ee;border-radius:12px;}')
            group_layout=QVBoxLayout(group);group_layout.setContentsMargins(7,5,7,7);group_layout.setSpacing(4)
            label=QLabel(name);label.setStyleSheet('color:#805095;font-weight:bold;background:transparent;padding:2px 4px;');group_layout.addWidget(label)
            for button in buttons:
                button.setProperty('navGroup',name)
                button.setStyleSheet('padding:7px 4px;border-radius:9px;')
                group_layout.addWidget(button)
            nav_layout.addWidget(group)
        nav_layout.addStretch()
        other=QFrame();other.setObjectName('navGroup');other.setStyleSheet(group.styleSheet());footer=QVBoxLayout(other);footer.setContentsMargins(7,5,7,7);footer.setSpacing(4)
        other_label=QLabel('기타');other_label.setStyleSheet(label.styleSheet());footer.addWidget(other_label);footer.addWidget(self.records_menu);side.addWidget(other)
        self.records_menu.setProperty('navGroup','기타')
        self.utility_row=QHBoxLayout();self.utility_row.setSpacing(4);footer.addLayout(self.utility_row)
        self.new_button = QPushButton("새 게임 생성")
        self.new_button.clicked.connect(self.request_new_game)
        if self.slot_mode:self.new_button.setText('메인 메뉴로 돌아가기')
        footer.addWidget(self.new_button)
        side.addWidget(QLabel("MAKE YOUR STARS SHINE ✦"))
        outer.addWidget(sidebar)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 28, 30, 22)
        layout.setSpacing(16)
        title = QLabel("아이돌 명단")
        title.setObjectName("title")
        layout.addWidget(title)
        self.subtitle = QLabel("드래프트 후보 · 사진과 가상 나이 공개")
        layout.addWidget(self.subtitle)
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.roster_selector = QComboBox()
        self.roster_selector.setAccessibleName("조회할 후보 목록 또는 기획사")
        self.roster_selector.currentIndexChanged.connect(self._view_changed)
        layout.addWidget(self.roster_selector)
        self.search = QLineEdit()
        self.search.setPlaceholderText("이름으로 검색")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._search)
        layout.addWidget(self.search)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setIconSize(QSize(44, 52))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(66)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((80, 260, 130, 210)):
            self.table.setColumnWidth(column, width)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.table, 1)
        self.empty = QLabel()
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        disclaimer = QLabel("모든 나이와 수치는 실제 인물의 현실 정보와 무관한 게임용 가상 정보입니다.")
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)
        self.pages = QStackedWidget()
        self.pages.addWidget(content)
        self.draft_page = DraftPage(service,self.thumbnails)
        self.pages.addWidget(self.draft_page)
        self.squad_page = SquadPage(service,self.thumbnails)
        self.squad_page.busy_changed.connect(self._squad_busy)
        self.squad_page.state_changed.connect(self.refresh_calendar)
        self.pages.addWidget(self.squad_page)
        self.schedule_page = SchedulePage(service)
        self.pages.addWidget(self.schedule_page)
        self.match_page = MatchPage(service,self.thumbnails)
        self.match_page.busy_changed.connect(self._match_busy)
        self.match_page.state_changed.connect(self._matches_changed)
        self.pages.addWidget(self.match_page)
        self.special_page=SpecialPage(service,self.thumbnails)
        self.pages.addWidget(self.special_page)
        self.finals_page=FinalsPage(service,self.thumbnails);self.pages.addWidget(self.finals_page)
        self.development_page=DevelopmentPage(service,self.thumbnails)
        from .training_page import TrainingPage
        self.training_page=TrainingPage(service,thumbnails=self.thumbnails)
        self.development_hub=QWidget();hub_layout=QVBoxLayout(self.development_hub)
        hub_layout.setContentsMargins(26,18,26,18)
        for widget in (self.development_page.heading,self.development_page.notice):
            self.development_page.layout().removeWidget(widget);hub_layout.addWidget(widget)
        self.development_tabs=QTabWidget();hub_layout.addWidget(self.development_tabs,1)
        self.development_tabs.addTab(self.development_page,'성장·노화 기록')
        self.development_tabs.addTab(self.training_page,'집중 훈련')
        self.development_page.layout().setContentsMargins(0,8,0,0)
        self.training_page.layout().setContentsMargins(0,8,0,0);self.training_page.heading.hide()
        self.development_tabs.currentChanged.connect(lambda index:self.training_page.reload() if index==1 else self.development_page.reload())
        self.pages.addWidget(self.development_hub)
        from .profile_explorer import ProfileExplorer
        self.explorer_page=ProfileExplorer(service,self.thumbnails);self.pages.addWidget(self.explorer_page)
        from .finance_page import FinancePage
        self.finance_page=FinancePage(service,self.thumbnails);self.pages.addWidget(self.finance_page)
        from .market_page import MarketPage
        self.market_page=MarketPage(service,self.thumbnails);self.market_page.state_changed.connect(self._market_changed);self.pages.addWidget(self.market_page)
        from .awards_page import AwardsPage
        self.awards_page=AwardsPage(service,self.thumbnails);self.pages.addWidget(self.awards_page)
        from .annual_page import AnnualDraftPage
        self.annual_page=AnnualDraftPage(service);self.pages.addWidget(self.annual_page)
        self.annual_page.state_changed.connect(self.refresh_calendar)
        from .records_page import RecordsPage
        self.records_page=RecordsPage(service,self.thumbnails);self.pages.addWidget(self.records_page)
        from .season_hub import SeasonHub
        self.midseason_page=SeasonHub(service,self,wrapup=False);self.pages.addWidget(self.midseason_page)
        self.wrapup_page=SeasonHub(service,self,wrapup=True);self.pages.addWidget(self.wrapup_page)
        self.navigation_pages=[(self.midseason_menu,self.midseason_page),(self.wrapup_menu,self.wrapup_page),(self.explorer_menu,self.explorer_page),(self.market_menu,self.market_page),(self.draft_menu,self.draft_page),
            (self.squad_menu,self.squad_page),(self.schedule_menu,self.schedule_page),(self.development_menu,self.development_hub),(self.finance_menu,self.finance_page),
            (self.match_menu,self.match_page),(self.special_menu,self.special_page),(self.finals_menu,self.finals_page),
            (self.awards_menu,self.awards_page),(self.records_menu,self.records_page)]
        self.initial_draft_history=QPushButton('창단 드래프트 기록 보기');self.initial_draft_history.clicked.connect(self.show_draft)
        self.annual_page.layout().insertWidget(1,self.initial_draft_history)
        self.annual_draft_link=QPushButton('통합 드래프트 보기');self.annual_draft_link.clicked.connect(self.show_annual)
        self.draft_page.layout().insertWidget(1,self.annual_draft_link)
        self.annual_draft_link.hide()
        self.records_page.awards_requested.connect(self._records_awards)
        self.records_page.finals_requested.connect(self._records_finals)
        self._awards_announced=set()
        self.finals_page.battle_active_changed.connect(lambda *_:QTimer.singleShot(0,self._offer_awards))
        self.finals_page.busy_changed.connect(self._finals_busy)
        self.finals_page.state_changed.connect(self._matches_changed)
        self.finals_page.battle_active_changed.connect(self._sync_bgm)
        self.finals_page.tabs.currentChanged.connect(self._sync_bgm)
        self.schedule_page.special_button.clicked.connect(self.show_specials)
        self.special_page.busy_changed.connect(self._special_busy)
        self.special_page.state_changed.connect(self._matches_changed)
        self.special_page.battle_active_changed.connect(self._sync_bgm)
        self.match_page.battle_active_changed.connect(self._sync_bgm)
        self.match_page.tabs.currentChanged.connect(self._sync_bgm)
        self.pages.currentChanged.connect(self._sync_bgm)
        # The date belongs to the window, outside all switchable pages.
        game_content = QWidget()
        game_layout = QVBoxLayout(game_content)
        game_layout.setContentsMargins(0,0,0,0)
        game_layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("game_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26,14,26,8)
        header_layout.addWidget(self.game_date_label,1)
        self.chat_header=QPushButton('채팅');header_layout.addWidget(self.chat_header)
        self.bgm_controls=BgmControls(self.bgm)
        header_layout.addWidget(self.bgm_controls)
        self.theme_button=settings_button(header);self.theme_header=self.theme_button
        header_layout.addWidget(self.theme_button)
        header_layout.addWidget(self.recovery_button)
        header_layout.addWidget(self.day_button)
        game_layout.addWidget(header)
        game_layout.addWidget(self.pages,1)
        from .coach_panel import CoachPanel
        outer.addWidget(game_content, 1)
        self.setCentralWidget(central)
        from .trade_chat import TradeChat
        self.trade_chat=TradeChat(self)
        self.chat_header.clicked.connect(self.trade_chat.toggle)
        from .table_widgets import bind_window_tables
        bind_window_tables(self, service.settings_dir / "ui_layout.ini")
        from .dock_install import install_main_docks
        self.dock_layouts=install_main_docks(self,service.settings_dir/'ui_layout.ini')
        self.panel_layout_button=self.dock_layouts.button(header,lambda:self.pages.currentWidget())
        header_layout.insertWidget(1,self.panel_layout_button)
        self.setStyleSheet(STYLE)
        from .profile_controller import ProfileController
        self.profiles=ProfileController(self)
        self.coach_panel=CoachPanel(self,compact=True);self.utility_row.addWidget(self.coach_panel,1)
        from .notepad import Notepad
        self.notes=Notepad(service.settings_dir/'notes.txt',self)
        self.notes_button=QPushButton('메모');self.notes_button.setToolTip('자동 저장 메모장')
        self.notes_button.setStyleSheet('padding:8px 5px;border-radius:9px;')
        self.notes_button.clicked.connect(self.notes.open_window)
        header_layout.insertWidget(header_layout.indexOf(self.chat_header)+1,self.notes_button)
        self.market_page.profile_requested.connect(self.profiles.open)
        self.awards_page.profile_requested.connect(self.profiles.open)
        self.annual_page.profile_requested.connect(self.profiles.open)
        self.records_page.profile_requested.connect(self.profiles.open)
        self.pages.currentChanged.connect(self._highlight_navigation)
        self._highlight_navigation()
        self.music_toast=MusicToast(central)
        self.bgm.song_started.connect(self.music_toast.show_song)
        from .portrait_layout import PortraitLayout
        self.portrait_layout=PortraitLayout(self,sidebar,header_layout)
        self.reload()
        self.refresh_calendar()
        self.show_explorer()
        QTimer.singleShot(0,self.bgm.start)

    def _highlight_navigation(self, *_):
        current=self.pages.currentWidget()
        for button,page in self.navigation_pages:
            active=current is page or (button is self.draft_menu and current is self.annual_page)
            button.setProperty("navActive",active)
            button.style().unpolish(button);button.style().polish(button)

    def _sync_bgm(self,*_):
        if self._closing:return
        active=(self.pages.currentWidget() is self.match_page and self.match_page.replaying
                and self.match_page.tabs.currentIndex()==1)
        active=active or (self.pages.currentWidget() is self.special_page and self.special_page.replaying
                          and self.special_page.tabs.currentIndex()==1)
        active=active or (self.pages.currentWidget() is self.finals_page and self.finals_page.replaying and self.finals_page.tabs.currentIndex()==1)
        self.bgm.set_context('battle' if active else 'default')

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'music_toast'):self.music_toast.reposition()
        if hasattr(self,'trade_chat') and self.trade_chat.isVisible():self.trade_chat.reposition()

    def showEvent(self,event):
        super().showEvent(event)
        if not getattr(self,'_portrait_opened',False):
            self._portrait_opened=True
            if self.width()==900:
                # Include Windows title bar/borders in the 900x1600 envelope.
                available=self.screen().availableGeometry()
                frame=self.frameGeometry();extra_width=frame.width()-self.width();extra_height=frame.height()-self.height()
                self.resize(min(900,available.width())-max(0,extra_width),min(1600,available.height())-max(0,extra_height))

    def show_roster(self):
        self.show_explorer()

    def show_draft_menu(self):
        if self.service.draft.state().status=='completed':self.show_annual()
        else:self.show_draft()

    def show_draft(self):
        self.annual_draft_link.setVisible(self.service.draft.state().status=='completed')
        self.pages.setCurrentIndex(1)
        self.draft_page.reload()
        self.refresh_calendar()

    def show_squads(self):
        self.pages.setCurrentIndex(2)
        self.squad_page.reload()
        self.refresh_calendar()

    def show_schedule(self):
        self.pages.setCurrentIndex(3)
        self.schedule_page.reload()
        self.refresh_calendar()

    def refresh_calendar(self):
        self.calendar_state = self.service.calendar.state()
        self.game_date_label.setText(str(self.calendar_state.date) if self.calendar_state.date is not None else "게임 시작 전")
        if hasattr(self,'trade_chat'):self.trade_chat.refresh()
        if hasattr(self,'coach_panel'):self.coach_panel.refresh()
        from .season_hub import availability
        for button,wrapup in ((self.midseason_menu,False),(self.wrapup_menu,True)):
            allowed,reason=availability(self.calendar_state.date,wrapup)
            button.setEnabled(allowed and self.job is None);button.setToolTip(reason)
        self.day_button.setEnabled(self.calendar_state.date is not None and self.job is None and not self.squad_page.is_busy() and not self.match_page.is_busy() and not self.special_page.is_busy() and not self.finals_page.is_busy())
        if hasattr(self,'midseason_page') and self.pages.currentWidget() in (self.midseason_page,self.wrapup_page):
            self.pages.currentWidget().reload()
        from ..founding import stage_hint
        self.day_button.setToolTip(self.calendar_state.advance_block_reason or stage_hint(self.calendar_state.date) or "미처리 경기가 없으면 다음 날로 진행합니다.")
        self.recovery_status = self.service.calendar.initial_recovery_status()
        self.recovery_button.setVisible(self.recovery_status.allowed)
        self.recovery_button.setEnabled(self.job is None and not self.squad_page.is_busy() and not self.match_page.is_busy())
        if hasattr(self,'profiles') and not self._closing:self.profiles.refresh()

    def show_season_hub(self,wrapup):
        self.refresh_calendar()
        button=self.wrapup_menu if wrapup else self.midseason_menu
        if not button.isEnabled():return
        page=self.wrapup_page if wrapup else self.midseason_page
        self.pages.setCurrentWidget(page);page.reload()

    def show_matches(self):
        self.pages.setCurrentIndex(4)
        self.match_page.reload()
        self.refresh_calendar()

    def show_specials(self):
        self.pages.setCurrentIndex(5)
        self.special_page.go_current()
        self.refresh_calendar()

    def show_finals(self):
        self.pages.setCurrentWidget(self.finals_page);self.finals_page.go_current();self.refresh_calendar()

    def show_development(self):
        self.pages.setCurrentWidget(self.development_hub);self.development_tabs.setCurrentIndex(0);self.development_page.reload();self.refresh_calendar()

    def show_training(self):
        self.pages.setCurrentWidget(self.development_hub);self.development_tabs.setCurrentIndex(1);self.training_page.reload();self.refresh_calendar()

    def show_market(self):
        self.pages.setCurrentWidget(self.market_page);self.market_page.reload();self.refresh_calendar()

    def _market_changed(self):
        self.squad_page.reload();self.finance_page.reload();self.reload();self.refresh_calendar()

    def show_finance(self):
        self.pages.setCurrentWidget(self.finance_page);self.finance_page.reload();self.refresh_calendar()

    def show_explorer(self):
        self.pages.setCurrentWidget(self.explorer_page);self.explorer_page.reload();self.refresh_calendar()

    def _finals_busy(self,busy):
        self._match_busy(busy)
        self.match_page.set_external_busy(busy)
        self.finals_page.set_external_busy(False)

    def _special_busy(self,busy):
        if self._closing:return
        self.development_menu.setEnabled(not busy)
        self.training_menu.setEnabled(not busy)
        for button in (self.new_button,self.roster_menu,self.draft_menu,self.squad_menu,self.schedule_menu,self.match_menu,self.special_menu):
            button.setEnabled(not busy)
        self.match_page.set_external_busy(busy)
        self.finals_page.set_external_busy(busy);self.finals_menu.setEnabled(not busy)
        self.squad_page.set_busy(busy);self.draft_page.set_busy(busy)
        self.refresh_calendar()

    def _match_busy(self,busy):
        if self._closing:return
        self.development_menu.setEnabled(not busy)
        self.training_menu.setEnabled(not busy)
        for button in (self.new_button,self.roster_menu,self.draft_menu,self.squad_menu,self.schedule_menu,self.match_menu,self.special_menu):
            button.setEnabled(not busy)
        self.squad_page.set_busy(busy)
        self.draft_page.set_busy(busy)
        self.special_page.set_external_busy(busy)
        self.finals_page.set_external_busy(busy);self.finals_menu.setEnabled(not busy)
        self.refresh_calendar()

    def _matches_changed(self):
        if self._closing:return
        self.schedule_page.reload()
        self.match_page.refresh_standings()
        self.finals_page.reload()
        self.refresh_calendar()
        QTimer.singleShot(0,self._offer_awards)

    def show_awards(self):
        self.pages.setCurrentWidget(self.awards_page);self.awards_page.reload();self.refresh_calendar()

    def show_annual(self):
        self.pages.setCurrentWidget(self.annual_page);self.annual_page.reload();self.refresh_calendar()

    def show_records(self):
        self.pages.setCurrentWidget(self.records_page);self.records_page.reload();self.refresh_calendar()

    def _records_awards(self,season):
        self.show_awards()
        self.awards_page.season.setCurrentIndex(self.awards_page.season.findData(season))

    def _records_finals(self,season):
        self.records_page.postseason_detail(season)

    def _offer_awards(self):
        if self._closing or self.pages.currentWidget() is not self.finals_page or self.finals_page.is_busy():return
        from contextlib import closing
        with closing(self.service.database.connect()) as c:
            row=c.execute("SELECT season FROM season_finals WHERE status='completed' ORDER BY season DESC LIMIT 1").fetchone()
        if row and row[0] not in self._awards_announced:
            self._awards_announced.add(row[0]);self.show_awards()

    def advance_day(self):
        if self.job is not None or self.squad_page.is_busy() or self.match_page.is_busy() or self.special_page.is_busy() or self.finals_page.is_busy() or self.calendar_state.date is None:
            return
        from ..competition_actions import pending_ai
        if pending_ai(self.service):
            self.job=CompetitionAIJob(self.service);self.job.signals.finished.connect(self._competition_ai_finished)
            self._match_busy(True);self.match_page.set_external_busy(True)
            self.pool.start(self.job);return
        application_revision=None
        day=self.calendar_state.date
        agency=self.service.draft_session.player_agency()
        if agency and not self.calendar_state.advance_block_reason:
            applications=self.service.recruitment.state(agency)
            if applications['can_apply']:
                names=' / '.join(p['name'] for p in applications['targets']) or '없음'
                timing='다음 날 추첨 결과가 확정됩니다.' if day.is_founding and day.weekday() in (2,4) else '마감 즉시 추첨합니다.'
                answer=QMessageBox.question(self,'연습생 신청 마감',f"신청 {applications['count']}/2: {names}\nAI 신청과 동시에 접수를 마감합니다. {timing}\n마감 후 변경·재추첨할 수 없습니다. 계속할까요?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                if answer!=QMessageBox.StandardButton.Yes:return
                application_revision=applications['revision']
        self.draft_page.set_busy(True)
        self.squad_page.set_busy(True)
        try:
            self.service.calendar.advance_day(expected_absolute_day=self.calendar_state.date.absolute_day,expected_trainee_revision=application_revision)
        except (ValueError,sqlite3.Error,OSError) as error:
            message = str(error) if isinstance(error,CalendarError) else "날짜 저장 중 충돌이 발생했습니다. 다시 불러온 뒤 시도해 주세요."
            recovery = self.service.calendar.initial_recovery_status()
            if recovery.allowed:
                message += "\n\n상단의 '초기 날짜 복구'에서 백업 후 최초 월요일로 복구할 수 있습니다."
            elif self.calendar_state.advance_block_reason and self.calendar_state.date.absolute_day>0:
                message += "\n\n자동 날짜 복구 불가: " + recovery.reason + "\n현재 저장은 유지됩니다. 진행 전 백업을 별도 복사본으로 확인하거나 개별 상태 점검이 필요합니다."
            QMessageBox.warning(self,"날짜 진행 안내",message)
        finally:
            # Refresh even after a stale-date conflict from another window.
            self.squad_page.reload()
            self.schedule_page.reload()
            self.match_page.reload()
            self.special_page.reload()
            self.finals_page.reload()
            self.development_page.reload()
            self.training_page.reload()
            self.finance_page.reload()
            self.market_page.reload()
            self.draft_page.set_busy(False)
            self.squad_page.set_busy(False)
            self.refresh_calendar()

    def _competition_ai_finished(self,error):
        self.job=None
        if self._closing:return
        self._match_busy(False);self.match_page.set_external_busy(False)
        self.special_page.reload();self.finals_page.reload();self.refresh_calendar()
        if error:QMessageBox.warning(self,'AI 경기 진행 안내',error)
        else:self.advance_day()

    def recover_initial_date(self):
        if self.job is not None or self.squad_page.is_busy() or self.match_page.is_busy() or self.special_page.is_busy():
            return
        status = self.service.calendar.initial_recovery_status()
        if not status.allowed:
            QMessageBox.warning(self,"초기 날짜 복구 불가",status.reason+
                                "\n현재 저장은 유지합니다. 진행 전 백업을 별도 복사본으로 확인하거나 개별 상태 점검이 필요합니다.")
            self.refresh_calendar()
            return
        answer = QMessageBox.question(self,"초기 날짜 복구 확인",
            "초기 선수단 편성을 완료하지 않은 상태로 날짜가 진행되었습니다. "
            "기존 데이터를 백업한 뒤 시즌 1 정규 1주차 월요일로 복구하시겠습니까?\n\n"
            f"현재: {GameDate(status.absolute_day)}\n"
            "SQLite 백업을 먼저 생성하고 날짜와 날짜 수정 버전만 변경합니다. "
            "드래프트·선수·능력치·잠재력·자금·585경기 대진·특별전 6회는 유지됩니다.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.service.calendar.recover_initial_date(approved=True,expected_absolute_day=status.absolute_day,
                          expected_revision=status.revision,expected_token=status.token)
        except (ValueError,sqlite3.Error,OSError) as error:
            QMessageBox.warning(self,"초기 날짜 복구 실패",str(error))
        else:
            QMessageBox.information(self,"초기 날짜 복구 완료",f"{result.date}로 복구했습니다.\n백업: {result.backup_path}\n"
                                    "선수단 관리에서 1군 5명을 확정하고 1군·2군 리더를 지정해 주세요.")
        finally:
            self.squad_page.reload()
            self.schedule_page.reload()
            self.match_page.reload()
            self.refresh_calendar()

    def _squad_busy(self,busy):
        if self._closing:
            return
        for button in (self.new_button,self.roster_menu,self.draft_menu,self.squad_menu,self.schedule_menu,self.match_menu,self.special_menu,self.day_button):
            button.setEnabled(not busy)
        self.draft_page.set_busy(busy)
        self.match_page.set_external_busy(busy)
        self.special_page.set_external_busy(busy)
        self.refresh_calendar()

    def reload(self):
        selected = self.roster_selector.currentData()
        self.roster_selector.blockSignals(True)
        self.roster_selector.clear()
        self.roster_selector.addItem("최초 드래프트 후보", None)
        for agency in self.service.agencies():
            self.roster_selector.addItem(agency.name, agency.id)
        self.roster_selector.setCurrentIndex(max(0, self.roster_selector.findData(selected)))
        self.roster_selector.blockSignals(False)
        self._view_changed()

    def _view_changed(self, *_):
        agency_id = self.roster_selector.currentData()
        agency = next((item for item in self.service.agencies() if item.id == agency_id), None)
        self.model.replace(self.service.agency_roster(agency_id) if agency else self.service.initial_draft_candidates())
        total, candidates = self.service.database.counts()
        scan = self.service.scan
        self.subtitle.setText(f"{agency.name} · 기획사 선수 명단" if agency else "드래프트 후보 · 사진과 가상 나이 공개")
        self.summary.setText(
            f"인식 사진 {scan.image_count:,}개  ·  고유 인물 {len(scan.people):,}명  ·  "
            f"게임 인물 {total:,}명  ·  후보 {candidates:,}명  ·  미등장 {total-candidates:,}명"
            + (f"\n{agency.name} · 자금 {agency.funds_krw:,}원 · 소속 {self.model.rowCount():,}명" if agency else "")
            + (f"\n동일 이름의 중복 사진 {len(scan.duplicates)}개는 한 인물로 등록했습니다." if scan.duplicates else "")
        )
        self._update_empty()

    def _search(self, text):
        self.proxy.setFilterFixedString(text.strip())
        self._update_empty()

    def _update_empty(self):
        if self.roster_selector.currentData() is not None:
            if not self.model.rows:
                message = "이 기획사에 등록된 선수가 없습니다."
            elif self.proxy.rowCount() == 0:
                message = "검색 결과가 없습니다."
            else:
                message = f"소속 선수 중 {self.proxy.rowCount():,}명 표시 중"
        elif not self.service.database.has_game():
            message = "새 게임을 생성하면 최초 후보가 표시됩니다."
            if not self.service.scan.people:
                message += " assets/idols 폴더에 JPG·JPEG·PNG·WEBP 사진을 넣어 주세요."
        elif self.proxy.rowCount() == 0:
            message = "검색 결과가 없습니다."
        else:
            message = f"표시 중 {self.proxy.rowCount():,}명 · 미등장 인물은 공개되지 않습니다."
        self.empty.setText(message)

    def request_new_game(self):
        if self.slot_mode:
            self.menu_requested.emit()
            return
        if self.job is not None or self.squad_page.is_busy() or self.match_page.is_busy() or self.special_page.is_busy():
            return
        self.draft_page.set_busy(True)
        self.squad_page.set_busy(True)
        self.match_page.set_external_busy(True)
        if self.service.database.has_game():
            answer = QMessageBox.question(
                self, "새 게임 생성", "현재 게임을 대체하고 모든 가상 수치와 최초 후보를 새로 생성합니다. 계속할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.draft_page.set_busy(False)
                self.squad_page.set_busy(False)
                self.match_page.set_external_busy(False)
                return
        self.pages.setEnabled(False)
        self.roster_menu.setEnabled(False)
        self.draft_menu.setEnabled(False)
        self.squad_menu.setEnabled(False)
        self.schedule_menu.setEnabled(False)
        self.match_menu.setEnabled(False)
        self.special_menu.setEnabled(False)
        self.finals_menu.setEnabled(False)
        self.development_menu.setEnabled(False)
        self.training_menu.setEnabled(False)
        self.day_button.setEnabled(False)
        self.new_button.setEnabled(False)
        self.new_button.setText("생성 중…")
        self.job = NewGameJob(self.service)
        self.job.signals.finished.connect(self._game_finished)
        self.pool.start(self.job)

    def _game_finished(self, error):
        self.job = None
        if self._closing:
            return
        self.new_button.setEnabled(True)
        self.new_button.setText("새 게임 생성")
        self.pages.setEnabled(True)
        self.roster_menu.setEnabled(True)
        self.draft_menu.setEnabled(True)
        self.squad_menu.setEnabled(True)
        self.schedule_menu.setEnabled(True)
        self.match_menu.setEnabled(True)
        self.special_menu.setEnabled(True)
        self.finals_menu.setEnabled(True)
        self.development_menu.setEnabled(True)
        self.training_menu.setEnabled(True)
        self.draft_page.set_busy(False)
        self.squad_page.set_busy(False)
        self.match_page.set_external_busy(False)
        if error:
            QMessageBox.warning(self, "게임 생성 실패", error)
        else:
            self.reload()
            self.draft_page.reload()
            self.squad_page.reload()
            self.schedule_page.reload()
            self.match_page.reload()
            self.special_page.reload()
            self.finals_page.reload()
            self.development_page.reload()
            self.training_page.reload()
        self.refresh_calendar()

    def closeEvent(self, event):
        if not self.notes.flush():
            self.notes.open_window();event.ignore();return
        if self.before_close is not None and not self.before_close():
            event.ignore()
            return
        self._closing = True
        self.coach_panel.timer.stop()
        self.coach_panel.blink.stop()
        self.coach_panel.body.close()
        self.notes.close()
        self.portrait_layout.shutdown()
        self.profiles.shutdown()
        self.records_page.shutdown()
        self.dock_layouts.shutdown()
        if not self.slot_mode:self.bgm.shutdown()
        else:self.bgm.set_context('default')
        self.draft_page.shutdown()
        self.pool.waitForDone()
        self.squad_page.shutdown()
        self.match_page.shutdown()
        self.special_page.shutdown()
        self.finals_page.shutdown()
        self.awards_page.photos.close()
        self.annual_page.shutdown()
        self.thumbnails.close()
        super().closeEvent(event)
        self.closed.emit()


from .theme import STYLE
