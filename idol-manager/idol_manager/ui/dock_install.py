"""Reparent existing views into docks without replacing their models or signals."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QTabWidget,QStackedWidget,QSplitter,QScrollArea,QSizePolicy
from .table_widgets import QTableView,QTableWidget
from .dock_workspace import DockWorkspace,DockLayoutManager,TabbedDockWorkspace

TITLES={'season_history_table':'시즌별 · 통산 경기 기록','league_table':'시즌별 정규 순위','champion_table':'역대 챔피언','leader_table':'최고 기록','player_table':'선수 통산·시즌 기록','agency_table':'기획사 통산 기록','comparison_table':'선택 대상 비교','content_player_table':'선수별 콘텐츠 성적',
    'table':'아이돌 명단','candidate_table':'드래프트 후보','history_table':'지명 이력','detail_table':'후보 분석',
    'order_table':'기획사 지명 순서','fixture_table':'경기 목록','round_table':'특별전 단계 목록',
    'lineup_table':'출전자 선택','live_table':'실시간 판정 기록','records_table':'선수별 경기 기록',
    'abilities_table':'능력치별 판정','ability_table':'능력치별 판정','standings_table':'리그 순위',
    'rank_table':'특별전 순위','summary_table':'특별전 최종 정리','honors_table':'기획사 통산 기록',
    'injury_table':'부상 이력','moves_table':'선수단 이동 이력','calendar_table':'최근 출전 달력',
    'effective_table':'경기 유효 능력치','match_table':'최근 경기','content_table':'콘텐츠 성적',
    'skill_total_table':'능력치별 일반 합계','growth_table':'성장·노화 이력','forecast_table':'4주 예산 전망','ledger_table':'거래 장부','contract_table':'선수 계약','payroll_table':'급여 명세','debt_table':'채무 기록','sale_table':'강제 매각 검토','fa_table':'FA 선수 시장','negotiation_table':'계약 협상','trade_table':'트레이드 제안','renew_table':'재계약','release_table':'방출 대상','trainee_table':'연습생 영입·데뷔'}


def replace_widget(old,new):
    parent=old.parentWidget()
    if isinstance(parent,QSplitter):
        parent.replaceWidget(parent.indexOf(old),new);return False
    if isinstance(parent,QStackedWidget) and isinstance(parent.parentWidget(),QTabWidget):
        tabs=parent.parentWidget();index=tabs.indexOf(old);selected=tabs.currentIndex();blocked=tabs.blockSignals(True)
        text=tabs.tabText(index);icon=tabs.tabIcon(index);tip=tabs.tabToolTip(index);enabled=tabs.isTabEnabled(index)
        tabs.removeTab(index);tabs.insertTab(index,new,icon,text);tabs.setTabToolTip(index,tip);tabs.setTabEnabled(index,enabled)
        tabs.setCurrentIndex(selected);tabs.blockSignals(blocked);return True
    if parent is not None and parent.layout() is not None:
        item=parent.layout().replaceWidget(old,new,Qt.FindChildOption.FindChildrenRecursively)
        if item is not None:return False
    if parent is not None and isinstance(parent.parentWidget(),QScrollArea):
        scroll=parent.parentWidget()
        if scroll.widget() is old:scroll.takeWidget();scroll.setWidget(new);return False
    raise RuntimeError('표 작업영역의 원래 배치를 찾을 수 없습니다: '+old.__class__.__name__)


def relax_table(table):
    table.setMinimumSize(70,50);table.setMaximumSize(16777215,16777215)
    table.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)


def wrap_table(manager,table,key,title,scope):
    if hasattr(table,'dock_panel'):return table.dock_panel
    parent=table.parentWidget();tab_page=isinstance(parent,QStackedWidget) and isinstance(parent.parentWidget(),QTabWidget)
    wanted=True if tab_page else not table.isHidden()
    workspace=DockWorkspace(manager,key,parent,single=True,tab_page=tab_page,scope=scope)
    replace_widget(table,workspace);relax_table(table)
    panel=workspace.add_panel(title,table,key+'/panel',wanted=wanted);table.dock_panel=panel
    workspace.finish()
    if not wanted and not tab_page:workspace.hide()
    return panel


def paired_workspace(manager,page,upper,lower,key,upper_title,lower_title,*,list_height=230):
    old=upper.parentWidget()
    if not isinstance(old,QSplitter) or old.indexOf(lower)<0:return
    workspace=DockWorkspace(manager,key,old.parentWidget(),scope=page);replace_widget(old,workspace)
    relax_table(upper);lower.setMinimumHeight(180)
    first=workspace.add_panel(upper_title,upper,key+'/list')
    second=workspace.add_panel(lower_title,lower,key+'/details',beside=first)
    upper.dock_panel=first;workspace.resizeDocks([first,second],[list_height,500],Qt.Orientation.Vertical)
    old.hide();old.setParent(page);page.match_splitter=workspace
    workspace.finish()


def draft_workspace(manager,page):
    candidates=page.candidate_table.parentWidget();history=page.history_table.parentWidget()
    left=candidates.parentWidget();old=left.parentWidget()
    if not isinstance(left,QSplitter) or not isinstance(old,QSplitter):return
    workspace=DockWorkspace(manager,'draft/workspace',old.parentWidget(),scope=page);replace_widget(old,workspace)
    info=QWidget();info_layout=QVBoxLayout(info);info_layout.setContentsMargins(0,0,0,0)
    for widget in (page.portrait,page.selected_label,page.detail_label,page.detail_table):info_layout.addWidget(widget,1 if widget is page.portrait else 0)
    order=QWidget();order_layout=QVBoxLayout(order);order_layout.setContentsMargins(0,0,0,0)
    for widget in (page.order_label,page.order_table):order_layout.addWidget(widget)
    for table in (page.candidate_table,page.history_table,page.detail_table,page.order_table):relax_table(table)
    a=workspace.add_panel('드래프트 후보',candidates,'draft/candidates')
    b=workspace.add_panel('후보 사진·분석',info,'draft/info',beside=a,orientation=Qt.Orientation.Horizontal)
    c=workspace.add_panel('지명 이력',history,'draft/history',beside=a)
    d=workspace.add_panel('기획사 지명 순서',order,'draft/order',beside=b)
    for table,panel in ((page.candidate_table,a),(page.detail_table,b),(page.history_table,c),(page.order_table,d)):table.dock_panel=panel
    workspace.resizeDocks([a,b],[750,350],Qt.Orientation.Horizontal)
    workspace.resizeDocks([a,c],[380,210],Qt.Orientation.Vertical)
    workspace.resizeDocks([b,d],[350,240],Qt.Orientation.Vertical)
    old.hide();old.setParent(page);workspace.finish()


def paired_content(manager,page,first_widget,second_widget,key,first_title,second_title,*,wanted_second=True):
    parent=first_widget.parentWidget()
    if parent is not second_widget.parentWidget():return
    workspace=DockWorkspace(manager,key,parent,scope=page);replace_widget(first_widget,workspace)
    parent.layout().removeWidget(second_widget)
    for widget in (first_widget,second_widget):
        if isinstance(widget,(QTableView,QTableWidget)):relax_table(widget)
    first=workspace.add_panel(first_title,first_widget,key+'/first')
    second=workspace.add_panel(second_title,second_widget,key+'/second',beside=first,wanted=wanted_second)
    for widget,panel in ((first_widget,first),(second_widget,second)):
        if isinstance(widget,(QTableView,QTableWidget)):widget.dock_panel=panel
    workspace.resizeDocks([first,second],[430,180],Qt.Orientation.Vertical);workspace.finish()


def install_main_docks(window,path):
    manager=DockLayoutManager(path)
    draft_workspace(manager,window.draft_page)
    for page,key in ((window.match_page,'match/workspace'),(window.finals_page,'finals/progress-workspace')):
        paired_workspace(manager,page,page.fixture_table,page.tabs,key,'경기 목록','경기 상세·진행',list_height=130 if page is window.finals_page else 230)
        paired_content(manager,page,page.battle,page.live_table,key+'/replay','사진 대결 무대','상세 판정 기록',wanted_second=False)
        # The arena is a single scene, not a draggable photo window.
        stage=page.live_table.dock_panel.workspace.panels[0]
        stage.setTitleBarWidget(QWidget(stage))
        stage.setFeatures(stage.DockWidgetFeature.NoDockWidgetFeatures)
    # Tournament cards own stage navigation; keep the optional stage list
    # collapsed and give result tabs one uninterrupted area.
    pages=[('roster',window),('draft',window.draft_page),('squad',window.squad_page),('schedule',window.schedule_page),
        ('match',window.match_page),('special',window.special_page),('finals',window.finals_page),
        ('development',window.development_page),('training',window.training_page),('explorer',window.explorer_page),('finance',window.finance_page),('market',window.market_page),('awards',window.awards_page),('annual',window.annual_page),('records',window.records_page)]
    for key,page in pages:
        for name,value in list(vars(page).items()):
            if isinstance(value,(QTableView,QTableWidget)):
                if key=='special' and name=='round_table':continue
                title=TITLES.get(name,name)
                if name=='table':title={'squad':'소속 선수단','schedule':'경기 일정','development':'성장·노화 결과','training':'소속 선수 훈련','explorer':'아이돌 탐색','awards':'정규 시즌 개인 기록'}.get(key,title)
                if key=='awards' and name=='agency_table':title='기획사 개인상 수상 기록'
                wrap_table(manager,value,key+'/'+name,title,window.pages.widget(0) if page is window else page)
    return manager


def install_profile_docks(panel,path,namespace):
    manager=DockLayoutManager(path)
    # One shared workspace lets the four condition tables dock beside/under
    # each other, instead of keeping fixed-height tables in a long column.
    tables=(panel.injury_table,panel.moves_table,panel.calendar_table,panel.effective_table)
    container=tables[0].parentWidget();layout=container.layout()
    workspace=DockWorkspace(manager,namespace+'/condition',container,scope=panel)
    layout.addWidget(workspace,1);workspace.setMinimumHeight(430)
    first=None
    for table in tables:
        layout.removeWidget(table);relax_table(table)
        name=next(name for name,value in vars(panel).items() if value is table)
        dock=workspace.add_panel(TITLES[name],table,namespace+'/'+name)
        if first is None:first=dock
        else:workspace.tabifyDockWidget(first,dock)
        table.dock_panel=dock
    # The old static captions are replaced by the panels' title bars.
    from PySide6.QtWidgets import QLabel
    for i in range(layout.count()-1,-1,-1):
        item=layout.itemAt(i);widget=item.widget()
        if isinstance(widget,QLabel) and widget not in (panel.condition_label,getattr(panel,'condition_detail',None)):layout.removeWidget(widget);widget.hide()
    first.raise_();workspace.finish()
    old=panel.record_tabs;records=TabbedDockWorkspace(manager,namespace+'/records',old.parentWidget(),scope=panel)
    replace_widget(old,records)
    first_record=None
    while old.count():
        table=old.widget(0);title=old.tabText(0);old.removeTab(0);relax_table(table)
        name=next(name for name,value in vars(panel).items() if value is table)
        dock=records.add_panel(title,table,namespace+'/'+name)
        if first_record is None:first_record=dock
        else:records.tabifyDockWidget(first_record,dock)
        index=len(records.panels)-1
        dock.visibilityChanged.connect(lambda visible,i=index,w=records:setattr(w,'_active_index',i) if visible else None)
        table.dock_panel=dock
    first_record.raise_();records.finish();old.hide();old.setParent(panel);panel.record_tabs=records
    for name,value in list(vars(panel).items()):
        if isinstance(value,(QTableView,QTableWidget)):wrap_table(manager,value,namespace+'/'+name,TITLES.get(name,name),panel)
    return manager
