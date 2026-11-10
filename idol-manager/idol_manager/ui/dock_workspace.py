"""Native dockable workspaces. Layout preferences never touch game SQLite."""
import json
from PySide6.QtCore import QByteArray,QEvent,QObject,QSettings,Qt,QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDockWidget,QMainWindow,QMenu,QToolButton,QSizePolicy

STATE_VERSION=1


class DockPanel(QDockWidget):
    def __init__(self,title,widget,workspace,key,*,wanted=True):
        super().__init__(title,workspace);self.workspace=workspace;self.key=key
        self.user_open=True;self.content_wanted=wanted
        self.setObjectName('dock-'+key);self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable|
                         QDockWidget.DockWidgetFeature.DockWidgetMovable|QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.setMinimumSize(90,80)
        self.setToolTip('제목줄 드래그: 도킹 이동 · 제목줄 더블클릭: 분리/복귀 · 패널 경계 드래그: 크기 조절')
        self.setWidget(widget);widget.setVisible(wanted);widget.installEventFilter(self)
        self.topLevelChanged.connect(lambda *_:workspace.schedule_save())
        self.dockLocationChanged.connect(lambda *_:workspace.schedule_save())
        self.toggleViewAction().triggered.connect(self.set_open)

    def set_open(self,opened=True):
        self.user_open=bool(opened);self.workspace.sync_panels()
        if opened and self.isVisible():self.raise_()
        self.workspace.schedule_save()

    def closeEvent(self,event):
        self.user_open=False;super().closeEvent(event);self.workspace.schedule_save()

    def moveEvent(self,event):
        super().moveEvent(event)
        if hasattr(self,'workspace'):self.workspace.schedule_save()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'workspace'):self.workspace.schedule_save()

    def eventFilter(self,obj,event):
        if obj is self.widget() and event.type() in (QEvent.Type.Show,QEvent.Type.Hide,QEvent.Type.ShowToParent,QEvent.Type.HideToParent):
            if not self.workspace._syncing:
                wanted=not obj.isHidden()
                if wanted!=self.content_wanted:
                    self.content_wanted=wanted
                    if self.workspace.single and not self.workspace.tab_page:self.workspace.setVisible(wanted)
                    self.workspace.sync_panels()
        return super().eventFilter(obj,event)

    def contextMenuEvent(self,event):
        menu=QMenu(self)
        floating=menu.addAction('원래 작업영역으로 도킹' if self.isFloating() else '별도 창으로 분리')
        floating.triggered.connect(lambda *_:self.setFloating(not self.isFloating()))
        menu.addAction('이 패널 표시',lambda:self.set_open(True))
        menu.addAction('이 작업영역 기본 배치',self.workspace.reset_layout)
        menu.exec(event.globalPos());menu.deleteLater()


class DockWorkspace(QMainWindow):
    def __init__(self,manager,key,parent=None,*,single=False,tab_page=False,scope=None):
        super().__init__(parent,Qt.WindowType.Widget)
        # QMainWindow's constructor adds the Window flag even with a parent.
        # These workspaces belong inside the existing page layout.
        self.setWindowFlags(Qt.WindowType.Widget)
        self.manager=manager;self.key=key;self.single=single;self.tab_page=tab_page
        self.scope=self if scope is None else scope
        self.panels=[];self._ready=False;self._restored=False;self._syncing=False;self._closed=False
        self._default_state=QByteArray();self._pending_state=None
        self.setObjectName('workspace-'+key);self.setMinimumSize(100,100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setDockNestingEnabled(True)
        self.setDockOptions(QMainWindow.DockOption.AllowNestedDocks|QMainWindow.DockOption.AllowTabbedDocks|
                            QMainWindow.DockOption.AnimatedDocks|QMainWindow.DockOption.GroupedDragging)
        self._save_timer=QTimer(self);self._save_timer.setSingleShot(True);self._save_timer.setInterval(180);self._save_timer.timeout.connect(self.save_layout)
        self._show_timer=QTimer(self);self._show_timer.setSingleShot(True);self._show_timer.timeout.connect(self._activate)
        self.setStyleSheet('''QMainWindow::separator {background:#d8bce8;width:9px;height:9px;}
            QMainWindow::separator:hover {background:#b789d4;}
            QDockWidget {font-weight:bold;}
            QDockWidget::title {background:#eee1f6;padding:7px;text-align:left;}
            QDockWidget::close-button,QDockWidget::float-button {padding:2px;}
        ''')
        manager.workspaces.append(self)
        if self.scope is not self:manager.watch_scope(self.scope)

    @property
    def settings_key(self):return 'dock_workspaces/v1/'+self.key

    def add_panel(self,title,widget,key,*,beside=None,orientation=Qt.Orientation.Vertical,wanted=True):
        panel=DockPanel(title,widget,self,key,wanted=wanted);self.panels.append(panel)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea,panel)
        if beside is not None:self.splitDockWidget(beside,panel,orientation)
        return panel

    def finish(self):
        self._default_state=self.saveState(STATE_VERSION);settings=self.manager.settings
        raw=settings.value(self.settings_key+'/state','')
        if raw:
            try:self._pending_state=QByteArray.fromBase64(str(raw).encode('ascii'))
            except (ValueError,UnicodeError):self._pending_state=None
        try:closed=set(json.loads(str(settings.value(self.settings_key+'/closed','[]'))))
        except (ValueError,TypeError):closed=set()
        for panel in self.panels:panel.user_open=panel.key not in closed
        self._ready=True
        if self.isVisible():self.queue_restore()

    def queue_restore(self):
        # Also replaces the old two-region splitter's deferred refresh hook.
        if not self._closed:self._show_timer.start(0)

    def _activate(self):
        if not self._ready or self._closed or not self.scope.isVisible():return
        if not self._restored:
            self._syncing=True
            try:
                if self._pending_state and not self.restoreState(self._pending_state,STATE_VERSION):self.restoreState(self._default_state,STATE_VERSION)
                self._restored=True
            finally:self._syncing=False
        self.sync_panels()
        for panel in self.panels:
            if panel.isFloating() and panel.isVisible():self.keep_on_screen(panel)

    @staticmethod
    def keep_on_screen(panel):
        screens=QGuiApplication.screens()
        if not screens:return
        rect=panel.frameGeometry()
        if any(s.availableGeometry().intersects(rect.adjusted(25,15,-25,-15)) for s in screens):return
        available=screens[0].availableGeometry()
        panel.resize(min(max(300,panel.width()),available.width()),min(max(180,panel.height()),available.height()))
        panel.move(available.center()-panel.rect().center())

    def sync_panels(self):
        if self._syncing or self._closed:return
        self._syncing=True
        try:
            for panel in self.panels:
                visible=panel.user_open and panel.content_wanted
                # A floating tool window must never survive its owning page/tab.
                if panel.isFloating():visible=visible and self.scope.isVisible() and self.isEnabled()
                panel.setVisible(visible)
        finally:self._syncing=False

    def schedule_save(self):
        if self._ready and self._restored and not self._syncing and not self._closed:self._save_timer.start()

    def save_layout(self):
        if not self._ready or not self._restored or self._closed:return
        settings=self.manager.settings
        settings.setValue(self.settings_key+'/state',bytes(self.saveState(STATE_VERSION).toBase64()).decode('ascii'))
        settings.setValue(self.settings_key+'/closed',json.dumps([p.key for p in self.panels if not p.user_open]))
        settings.sync()

    def reset_layout(self):
        self._save_timer.stop();self._pending_state=None
        self.manager.settings.remove(self.settings_key)
        self._syncing=True
        try:
            self.restoreState(self._default_state,STATE_VERSION)
            for panel in self.panels:panel.user_open=True
        finally:self._syncing=False
        self._restored=True;self.sync_panels();self.schedule_save()

    def show_all(self):
        for panel in self.panels:panel.user_open=True
        self.sync_panels();self.schedule_save()

    def showEvent(self,event):
        super().showEvent(event)
        if hasattr(self,'_show_timer'):self.queue_restore()

    def hideEvent(self,event):
        if self._ready and not self._closed:
            self.save_layout();self._syncing=True
            try:
                if not self.scope.isVisible():
                    for panel in self.panels:
                        if panel.isFloating():panel.hide()
            finally:self._syncing=False
        super().hideEvent(event)
        if self._ready and not self._closed and self.scope.isVisible():self.queue_restore()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'_save_timer'):self.schedule_save()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.EnabledChange and hasattr(self,'_show_timer'):self.queue_restore()

    def createPopupMenu(self):return self.manager.make_menu(self,workspaces=[self])

    def shutdown(self):
        self.save_layout();self._save_timer.stop();self._show_timer.stop();self._closed=True
        for panel in self.panels:
            if panel.isFloating():panel.hide()


class ScopeWatcher(QObject):
    def __init__(self,manager,scope):
        super().__init__(scope);self.manager=manager;self.scope=scope
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        scope.installEventFilter(self)

    def refresh(self):
        if not self.manager.closed:
            for workspace in self.manager.scoped(self.scope):workspace._activate()

    def eventFilter(self,obj,event):
        if not self.manager.closed:
            if event.type() in (QEvent.Type.Show,QEvent.Type.ShowToParent):self.timer.start(0)
            elif event.type() in (QEvent.Type.Hide,QEvent.Type.HideToParent) and not self.scope.isVisible():
                for workspace in self.manager.scoped(self.scope):
                    workspace.save_layout();workspace._syncing=True
                    try:
                        for panel in workspace.panels:
                            if panel.isFloating():panel.hide()
                    finally:workspace._syncing=False
        return super().eventFilter(obj,event)


class DockLayoutManager:
    def __init__(self,path):
        self.settings=QSettings(str(path),QSettings.Format.IniFormat);self.workspaces=[];self.watchers={};self.closed=False

    def watch_scope(self,scope):
        if scope not in self.watchers:self.watchers[scope]=ScopeWatcher(self,scope)

    def scoped(self,scope):
        return [w for w in self.workspaces if scope is None or scope is w or scope is w.scope or scope.isAncestorOf(w.scope)]

    def make_menu(self,parent,*,scope=None,workspaces=None):
        menu=QMenu(parent);targets=self.scoped(scope) if workspaces is None else workspaces
        menu.addAction('패널 모두 다시 표시',lambda:[w.show_all() for w in targets])
        menu.addAction('기본 패널 배치로 복원',lambda:[w.reset_layout() for w in targets]);menu.addSeparator()
        for workspace in targets:
            for panel in workspace.panels:
                action=menu.addAction(panel.windowTitle());action.setCheckable(True);action.setChecked(panel.user_open)
                action.setEnabled(workspace.isEnabled())
                action.triggered.connect(lambda checked,p=panel:p.set_open(checked))
        return menu

    def button(self,parent,scope_provider=None):
        button=QToolButton(parent);button.setText('패널 배치 ▾');button.setToolTip('도킹 패널 다시 표시·기본 배치 복원')
        def show_menu():
            menu=self.make_menu(button,scope=scope_provider() if scope_provider else None)
            menu.exec(button.mapToGlobal(button.rect().bottomLeft()));menu.deleteLater()
        button.clicked.connect(show_menu)
        return button

    def shutdown(self):
        if self.closed:return
        for workspace in self.workspaces:workspace.shutdown()
        self.closed=True
        for watcher in self.watchers.values():watcher.timer.stop()
        self.settings.sync()


class TabbedDockWorkspace(DockWorkspace):
    """Native dock tabs with a small selection adapter for existing view code."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self._active_index=0

    def setCurrentIndex(self,index):
        if not self._restored:self._activate()
        if 0<=index<len(self.panels):self._active_index=index;self.panels[index].set_open(True)

    def currentIndex(self):return self._active_index
    def count(self):return len(self.panels)
    def widget(self,index):return self.panels[index].widget()
