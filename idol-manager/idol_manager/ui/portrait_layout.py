"""900px portrait presentation. Pages existing models; never reads/writes game data."""
import math
import textwrap
from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel,
    QPushButton, QComboBox, QTableView, QListView, QHeaderView, QDockWidget,
    QTabWidget, QScrollArea, QSizePolicy, QDialog, QDialogButtonBox, QAbstractItemView,QLayout,
)


class RowDetails(QDialog):
    """Only values already exposed by the UI model, including estimated ranges."""
    def __init__(self, view, parent):
        super().__init__(parent)
        self.setWindowTitle('선택 항목 · 전체 정보')
        self.resize(760, 1080)
        box=QVBoxLayout(self);self.text=QLabel();self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.text,1)
        self.entries=[];model=view.model();row=view.currentIndex().row()
        for column in range(model.columnCount()):
            title=str(model.headerData(column,Qt.Orientation.Horizontal) or '항목')
            value=model.index(row,column).data()
            value='—' if value is None else str(value)
            for part in textwrap.wrap(value, 180, replace_whitespace=False) or ['—']:
                self.entries.append(title+'\n'+part)
        self.page=0;bar=QHBoxLayout();previous=QPushButton('이전');next_=QPushButton('다음')
        self.count=QLabel();bar.addWidget(previous);bar.addWidget(self.count,1);bar.addWidget(next_)
        previous.clicked.connect(lambda:self.turn(-1));next_.clicked.connect(lambda:self.turn(1))
        self.previous,self.next=previous,next_;box.addLayout(bar)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(self.close);box.addWidget(close)
        self.turn(0)

    def turn(self,delta):
        count=max(1,math.ceil(len(self.entries)/4));self.page=max(0,min(count-1,self.page+delta))
        self.text.setText('\n\n'.join(self.entries[self.page*4:self.page*4+4]))
        self.count.setText(f'전체 정보 {self.page+1}/{count}')
        self.previous.setEnabled(self.page>0);self.next.setEnabled(self.page+1<count)


class TablePages(QObject):
    def __init__(self,view,controller):
        super().__init__(view);self.view=view;self.controller=controller
        view._portrait_pager=self
        self.row_page=0;self.column_page=0;self.enabled=False;self.busy=False;self.revision=0;self.signature=None;self._visibility_sync=False
        self.original_columns=None;self.original_rows=None;self.original_widths=[]
        self.bar=QWidget();self.bar.setObjectName('tablePageControls')
        self.bar.setStyleSheet('QPushButton {padding:4px 6px;border-radius:8px;font-size:12px;} QComboBox {padding:4px;font-size:12px;} QLabel {font-size:12px;}')
        layout=QHBoxLayout(self.bar);layout.setContentsMargins(0,2,0,2);layout.setSpacing(4)
        self.previous=QPushButton('◀');self.next=QPushButton('▶');self.count=QLabel()
        self.fields=QComboBox();self.fields.setMinimumWidth(110);self.fields.setProperty('pageFieldSelector',True)
        self.details=QPushButton('선택 상세')
        for w in (self.previous,self.count,self.next,self.fields,self.details):layout.addWidget(w,1 if w is self.count else 0)
        self.previous.clicked.connect(lambda:self.turn(-1));self.next.clicked.connect(lambda:self.turn(1))
        self.fields.currentIndexChanged.connect(self.change_columns);self.details.clicked.connect(self.open_details)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        model=view.model()
        for signal in (model.modelReset,model.rowsInserted,model.rowsRemoved,model.columnsInserted,model.layoutChanged,model.dataChanged,model.headerDataChanged):
            signal.connect(self.model_changed)
        view.selectionModel().currentChanged.connect(self.current_changed)
        if isinstance(view,QTableView):
            view.horizontalHeader().sectionResized.connect(self.external_resize)
            view.verticalHeader().sectionResized.connect(self.external_resize)
        view.installEventFilter(self);view.viewport().installEventFilter(self)
        self.wrapper=QWidget();box=QVBoxLayout(self.wrapper);box.setContentsMargins(0,0,0,0);box.setSpacing(2)
        parent=view.parentWidget();wanted=not view.isHidden()
        workspace=getattr(getattr(view,'dock_panel',None),'workspace',None)
        syncing=workspace._syncing if workspace else False
        if workspace:workspace._syncing=True
        try:
            if isinstance(parent,QDockWidget):
                parent.setWidget(self.wrapper)
                if hasattr(parent,'workspace'):self.wrapper.installEventFilter(parent)
            else:
                from .dock_install import replace_widget
                replace_widget(view,self.wrapper)
            box.addWidget(view,1);box.addWidget(self.bar)
            view.setVisible(wanted);self.wrapper.setVisible(wanted)
        finally:
            if workspace:workspace._syncing=syncing
        self.bar.hide()

    def queue(self,*_):
        if QApplication.instance().property('themeLayoutChanging'):return
        if self.enabled and not self.busy and not self.timer.isActive():self.timer.start(15)

    def model_changed(self,*_):self.revision+=1;self.queue()

    def current_changed(self,current,previous):
        if not self.enabled or self.busy:return
        row=current.row()
        if row>=0 and self.view.isRowHidden(row) and row not in self.original_rows:
            rows=[r for r in range(self.view.model().rowCount()) if r not in self.original_rows]
            self.row_page=rows.index(row)//max(1,getattr(self,'page_size',1))
            self.signature=None;self.refresh()
        self.details.setEnabled(current.isValid());self.queue()

    def external_resize(self,*_):
        if self.enabled and not self.busy:self.revision+=1;self.queue()

    def eventFilter(self,obj,event):
        if obj is self.view and event.type() in (QEvent.Type.ShowToParent,QEvent.Type.HideToParent) and hasattr(self,'wrapper') and not self._visibility_sync:
            parent=self.wrapper.parentWidget();workspace=getattr(parent,'workspace',None)
            if isinstance(parent,QDockWidget) and not (workspace and workspace._syncing):
                self._visibility_sync=True
                try:self.wrapper.setVisible(not self.view.isHidden())
                finally:self._visibility_sync=False
        if event.type() in (QEvent.Type.Resize,QEvent.Type.Show):self.queue()
        return False

    def enable(self,value):
        if self.enabled==value:return
        self.enabled=value;v=self.view
        self.signature=None
        if value:
            self.policies=(v.horizontalScrollBarPolicy(),v.verticalScrollBarPolicy())
            self.scroll_modes=(v.horizontalScrollMode(),v.verticalScrollMode())
            v.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            v.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            self.original_columns={i for i in range(v.model().columnCount()) if v.isColumnHidden(i)} if isinstance(v,QTableView) else set()
            self.original_rows={i for i in range(v.model().rowCount()) if v.isRowHidden(i)}
            if isinstance(v,QTableView):
                self.original_minimum_height=v.minimumHeight();v.setMinimumHeight(max(90,v.minimumHeight()))
                self.original_widths=[v.columnWidth(i) for i in range(v.model().columnCount())]
                self.header_mode=v.horizontalHeader().sectionResizeMode(0) if v.model().columnCount() else QHeaderView.ResizeMode.Interactive
                v.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                v.horizontalHeader().setStretchLastSection(False)
                v.setWordWrap(True)
            v.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            v.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.bar.show();self.queue()
        else:
            self.timer.stop();self.bar.hide()
            restoring=getattr(v,'_restoring_columns',False);v._restoring_columns=True
            for r in range(v.model().rowCount()):v.setRowHidden(r,r in self.original_rows)
            if isinstance(v,QTableView):
                v.setMinimumHeight(self.original_minimum_height)
                for c in range(v.model().columnCount()):
                    v.setColumnHidden(c,c in self.original_columns and c not in (v.property('requiredVisibleColumns') or []))
                    if c<len(self.original_widths):
                        width=self.original_widths[c]
                        if c in (v.property('requiredVisibleColumns') or []):width=max(80,width)
                        v.horizontalHeader().resizeSection(c,width)
                v.horizontalHeader().setSectionResizeMode(self.header_mode)
            v._restoring_columns=restoring
            v.setHorizontalScrollBarPolicy(self.policies[0]);v.setVerticalScrollBarPolicy(self.policies[1])
            v.setHorizontalScrollMode(self.scroll_modes[0]);v.setVerticalScrollMode(self.scroll_modes[1])

    def refresh(self):
        if QApplication.instance().property('themeLayoutChanging'):return
        if not self.enabled or self.busy or not self.view.isVisible():return
        v=self.view
        signature=(v.viewport().width(),v.viewport().height(),self.revision,self.row_page,self.column_page,v.currentIndex().isValid())
        if self.signature==signature:return
        self.signature=signature
        self.busy=True
        restoring=getattr(v,'_restoring_columns',False)
        v._restoring_columns=True
        try:
            v=self.view;model=v.model();n=model.rowCount();w=max(120,v.viewport().width()-4)
            if isinstance(v,QTableView):
                v.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                v.horizontalHeader().setStretchLastSection(False)
                required=list(v.property('requiredVisibleColumns') or [])
                columns=[c for c in range(model.columnCount()) if c not in self.original_columns or c in required]
                names={c:str(model.headerData(c,Qt.Orientation.Horizontal) or '') for c in columns}
                # Keep a readable identity even on checkbox/photo/name lists.
                pinned=list(dict.fromkeys(required+[c for label in ('이름','선택','사진') for c in columns if names[c]==label][:2]))
                if not pinned and columns:pinned=[columns[0]]
                others=[c for c in columns if c not in pinned]
                # 120+ pixels per field keeps Korean headings/values legible.
                slots=max(1,int(w//145)-len(pinned));groups=[others[i:i+slots] for i in range(0,len(others),slots)] or [[]]
                compact=bool(v.property('compactProfileTable'))
                if compact:
                    natural={c:max(26,min(340,max(v.sizeHintForColumn(c),v.horizontalHeader().sectionSizeHint(c)))) for c in columns}
                    room=max(40,w-sum(natural[c] for c in pinned));groups=[[]];used=0
                    for c in others:
                        if groups[-1] and used+natural[c]>room:groups.append([]);used=0
                        groups[-1].append(c);used+=natural[c]
                self.column_page=min(self.column_page,len(groups)-1)
                selected=pinned+groups[self.column_page]
                self.fields.blockSignals(True);self.fields.clear()
                for i,group in enumerate(groups):
                    self.fields.addItem(f'정보 {i+1}/{len(groups)}')
                    self.fields.setItemData(i,' / '.join(names[c] for c in pinned+group),Qt.ItemDataRole.ToolTipRole)
                self.fields.setCurrentIndex(self.column_page);self.fields.blockSignals(False)
                self.fields.setMaximumWidth(max(140,min(290,w//3)))
                for c in range(model.columnCount()):v.setColumnHidden(c,c not in selected)
                # Prevent interactive user widths from overflowing the portrait page.
                weights=[.6 if names[c] in ('선택','사진') else 1.45 if names[c]=='이름' else 1 for c in selected]
                total=sum(weights) or 1;left=w
                for i,(c,weight) in enumerate(zip(selected,weights)):
                    width=left if i==len(selected)-1 else int(w*weight/total)
                    v.horizontalHeader().resizeSection(c,width);left-=width
                if compact:
                    for c in selected:v.horizontalHeader().resizeSection(c,min(w,natural[c]))
                from .agency_table_layout import user_widths
                widths=user_widths(v,selected,w,{c:v.columnWidth(c) for c in selected})
                for c in selected:v.horizontalHeader().resizeSection(c,widths[c])
                height=getattr(v,'_user_row_height',None) or max(32,min(64,v.viewport().height()-3))
                if compact:height=28
                v.verticalHeader().setDefaultSectionSize(height)
                for r in range(n):v.setRowHeight(r,height)
                if not compact:
                    from .agency_table_layout import fit_company_table
                    height=fit_company_table(v,selected,w) or height
                available=max(1,v.viewport().height()-3)
            else:
                height=max(42,v.sizeHintForRow(0));available=max(1,v.viewport().height()-3)
                self.fields.hide()
            size=max(1,int(available//height));rows=[r for r in range(n) if r not in self.original_rows]
            pages=max(1,math.ceil(len(rows)/size));self.row_page=min(self.row_page,pages-1)
            visible=set(rows[self.row_page*size:(self.row_page+1)*size])
            for r in range(n):v.setRowHidden(r,r not in visible)
            v.doItemsLayout()
            v.scrollToTop();v.horizontalScrollBar().setValue(0)
            self.count.setText(f'{self.row_page+1}/{pages}쪽 · 총 {len(rows)}')
            self.previous.setEnabled(self.row_page>0);self.next.setEnabled(self.row_page+1<pages)
            self.details.setEnabled(v.currentIndex().isValid());self.page_size=size
        finally:
            v._restoring_columns=restoring;self.busy=False
            # Hiding rows can change a visible row-number header from one to
            # two digits. Fit again to the new viewport rather than leaving
            # a few pixels outside the page.
            if (v.viewport().width(),v.viewport().height())!=signature[:2]:self.queue()

    def turn(self,delta):self.row_page=max(0,self.row_page+delta);self.refresh()
    def change_columns(self,index):
        if index>=0:self.column_page=index;self.refresh()
    def open_details(self):
        if self.view.currentIndex().isValid():
            self.dialog=RowDetails(self.view,self.controller.window);self.dialog.show()


class TextPages(QObject):
    """Long profile explanations/history use pages, rather than clipped scroll areas."""
    def __init__(self,label):
        super().__init__(label);self.label=label;self.full=label.text();self.rendered=self.full;self.page=0
        wanted=not label.isHidden()
        self.wrapper=QWidget();box=QVBoxLayout(self.wrapper);box.setContentsMargins(0,0,0,0)
        parent=label.parentWidget();parent.layout().replaceWidget(label,self.wrapper)
        label.setMinimumSize(0,0);label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        label.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(label,1)
        row=QHBoxLayout();self.previous=QPushButton('설명 이전');self.count=QLabel();self.next=QPushButton('설명 다음')
        row.addWidget(self.previous);row.addWidget(self.count,1);row.addWidget(self.next);box.addLayout(row)
        self.previous.clicked.connect(lambda:self.turn(-1));self.next.clicked.connect(lambda:self.turn(1))
        self.wrapper.setMinimumHeight(160)
        if any(parent.layout().itemAt(i).widget() not in (None,self.wrapper) for i in range(parent.layout().count())):
            self.wrapper.setMaximumHeight(280)
        label._text_pages_wrapper=self.wrapper;self.wrapper.setVisible(wanted);label.setVisible(wanted)

    def turn(self,delta):self.page=max(0,self.page+delta);self.refresh()

    def refresh(self):
        if not self.label.isVisible():return
        if self.label.text()!=self.rendered:self.full=self.label.text();self.page=0
        fm=QFontMetrics(self.label.font());width=max(100,self.label.width()-6);height=max(40,self.label.height()-8)
        remaining=self.full;pages=[]
        flags=Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere
        while remaining:
            lo,hi=1,len(remaining)
            while lo<hi:
                mid=(lo+hi+1)//2
                if fm.boundingRect(0,0,width,100000,int(flags),remaining[:mid]).height()<=height:lo=mid
                else:hi=mid-1
            end=lo
            if end<len(remaining):
                boundary=max(remaining.rfind('\n',0,end),remaining.rfind(' ',0,end))
                if boundary>end//2:end=boundary+1
            pages.append(remaining[:end]);remaining=remaining[end:]
        pages=pages or [''];self.page=min(self.page,len(pages)-1)
        self.rendered=pages[self.page];self.label.setText(self.rendered)
        self.count.setText(f'{self.page+1}/{len(pages)}쪽');self.previous.setEnabled(self.page>0);self.next.setEnabled(self.page+1<len(pages))


class PortraitLayout(QObject):
    def __init__(self,window,sidebar,header_layout):
        super().__init__(window);self.window=window;self.sidebar=sidebar;self.enabled=False
        self.tables={};self.boxes={};self.scans=False;self.tab_pickers={};self.dialogs=[];self.text_pages={};self.dock_features={}
        self.dialog_objects={}
        self.nav=QComboBox();self.nav.setAccessibleName('화면 이동');self.nav.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        buttons=tuple(button for button,page in window.navigation_pages)+(window.coach_panel.toggle,window.new_button,)
        self.buttons=buttons
        for b in buttons:self.nav.addItem((b.property('navGroup')+' · ' if b.property('navGroup') else '')+b.text())
        self.nav.activated.connect(self.navigate)
        window.pages.currentChanged.connect(self.sync_navigation)
        parent=header_layout.parentWidget().parentWidget().layout()
        parent.insertWidget(1,self.nav);self.nav.hide()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        QApplication.instance().installEventFilter(self)
        for page in (window.match_page,window.finals_page):
            page.tabs.currentChanged.connect(self.update_battle_panels)
            page.details_button.toggled.connect(self.update_battle_panels)
        self.timer.start(0)

    def navigate(self,index):
        self.buttons[index].click();self.sync_navigation()

    def sync_navigation(self,*_):
        current=self.window.pages.currentWidget()
        if current is self.window.annual_page:current=self.window.draft_page
        index=next((i for i,(_,page) in enumerate(self.window.navigation_pages) if page is current),0)
        self.nav.setCurrentIndex(index)

    def shutdown(self):
        self.timer.stop();QApplication.instance().removeEventFilter(self)
        for pager in self.tables.values():
            try:pager.timer.stop()
            except RuntimeError:pass  # A closed profile owns/destroys its pagers.

    def eventFilter(self,obj,event):
        if self.window._closing:return False
        if QApplication.instance().property('themeLayoutChanging'):return False
        if event.type() in (QEvent.Type.Show,QEvent.Type.Resize,QEvent.Type.LayoutRequest):
            if isinstance(obj,QWidget) and (obj is self.window or self.window.isAncestorOf(obj)):
                if not self.scans and not self.timer.isActive():self.timer.start(35)
        return False

    def update_battle_panels(self,*_):
        if self.window._closing:return
        active=self.window.width()<=1000
        for page in (self.window.match_page,self.window.finals_page):
            fixture=page.fixture_table.dock_panel
            watching=page.tabs.currentIndex()==1 and bool(page.battle.cards)
            if watching and not getattr(fixture,'_portrait_battle_hidden',False):
                fixture._portrait_previous_wanted=fixture.content_wanted;fixture._portrait_battle_hidden=True
                fixture.content_wanted=False;fixture.workspace.sync_panels()
            elif not watching and getattr(fixture,'_portrait_battle_hidden',False):
                fixture._portrait_battle_hidden=False;fixture.content_wanted=fixture._portrait_previous_wanted;fixture.workspace.sync_panels()
            stage=page.live_table.dock_panel.workspace.panels[0]
            detail_only=watching and page.details_button.isChecked()
            if detail_only and not getattr(stage,'_portrait_detail_hidden',False):
                stage._portrait_detail_hidden=True;stage._portrait_previous_wanted=stage.content_wanted
                stage.content_wanted=False;stage.workspace.sync_panels()
            elif not detail_only and getattr(stage,'_portrait_detail_hidden',False):
                stage._portrait_detail_hidden=False;stage.content_wanted=stage._portrait_previous_wanted;stage.workspace.sync_panels()
            fixture.workspace.layout().activate()
            page.fixture_table.doItemsLayout()

    def refresh(self):
        if self.window._closing:return
        if QApplication.instance().property('themeLayoutChanging'):return
        self.prune_deleted()
        active=self.window.width()<=1000;self.enabled=active;self.scans=True
        try:
            self.sidebar.setVisible(not active);self.nav.setVisible(active)
            self.update_battle_panels()
            for table in self.window.findChildren(QTableView)+self.window.findChildren(QListView):
                # QComboBox popups are implementation details, not information tables.
                if table.model() is None or isinstance(table.parentWidget(),QComboBox) or table.window() not in [self.window,*self.dialogs]:continue
                if table.property('fitAllColumns'):
                    if table in self.tables:self.tables[table].enable(False)
                    continue
                if not isinstance(table,QTableView) and table.__class__.__name__!='QListWidget':continue
                paged=active or bool(table.property('paginateWithoutScroll'))
                if not paged and table not in self.tables:continue
                if table not in self.tables:
                    self.tables[table]=TablePages(table,self)
                self.tables[table].enable(paged);self.tables[table].queue()
            for widget in self.window.findChildren(QWidget):
                if isinstance(widget,QDockWidget):
                    if active:
                        if widget not in self.dock_features:self.dock_features[widget]=widget.features()
                        if widget.isFloating():widget.setFloating(False)
                        widget.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
                    elif widget in self.dock_features:widget.setFeatures(self.dock_features[widget])
                if widget.window() not in [self.window,*self.dialogs]:continue
                if widget.__class__.__name__=='TeamPanel':
                    # The stage owns its multi-player 3+2 card sizing.
                    widget.reflow()
                if active and isinstance(widget,QLabel) and widget.pixmap().isNull():
                    widget.setWordWrap(True);widget.setMinimumWidth(0)
                    if widget.isVisible() and widget.window() in self.dialogs and len(widget.text())>600 and widget not in self.text_pages and widget.parentWidget().layout():
                        self.text_pages[widget]=TextPages(widget)
                    if widget in self.text_pages:self.text_pages[widget].refresh()
                if isinstance(widget,QComboBox) and active and not widget.property('pageFieldSelector'):
                    widget.setMinimumContentsLength(0);widget.setMinimumWidth(0)
                    widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                if isinstance(widget,QTabWidget):
                    widget.setUsesScrollButtons(not active)
                    if active:widget.setTabPosition(QTabWidget.TabPosition.North)
                    if active and widget.count()>5 and widget not in self.tab_pickers:
                        picker=QComboBox();picker.setAccessibleName('정보 화면 선택')
                        for i in range(widget.count()):picker.addItem(widget.tabText(i))
                        picker.setCurrentIndex(widget.currentIndex());picker.activated.connect(widget.setCurrentIndex)
                        widget.currentChanged.connect(picker.setCurrentIndex)
                        wrapper=QWidget();box=QVBoxLayout(wrapper);box.setContentsMargins(0,0,0,0)
                        parent=widget.parentWidget()
                        if isinstance(parent,QDockWidget):parent.setWidget(wrapper)
                        else:
                            from .dock_install import replace_widget
                            replace_widget(widget,wrapper)
                        box.addWidget(picker);box.addWidget(widget,1);wrapper.show();widget.show()
                        self.tab_pickers[widget]=picker
                    if widget in self.tab_pickers:
                        self.tab_pickers[widget].setVisible(active);widget.tabBar().setVisible(not active)
                if isinstance(widget,QScrollArea) and active and not widget.property('responsivePageScroll'):
                    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    if widget.widget():widget.widget().setMinimumSize(0,0)
                if active and widget.__class__.__name__=='DockWorkspace':widget.setMinimumHeight(100)
                layout=widget.layout()
                if layout:self.reflow(layout,active)
            self.sync_navigation()
        finally:
            # Capture ownership while the dialog's QObject tree is alive.
            # Finished/close callbacks must never walk parents of old layouts.
            from shiboken6 import isValid
            for dialog in self.dialogs:
                if isValid(dialog):self.dialog_objects.setdefault(dialog,set()).update(dialog.findChildren(QObject))
            self.scans=False

    def prepare_dialog(self,dialog):
        forced=bool(dialog.property('paginateWithoutScroll'))
        if not self.enabled and not forced:return
        self.dialogs.append(dialog)
        self.dialog_objects[dialog]=set(dialog.findChildren(QObject))|{dialog}
        dialog.finished.connect(lambda *_:self.release_dialog(dialog))
        if forced:
            dialog.setMinimumSize(640,440)
            dialog.resize(max(640,min(1050,self.window.width()-40)),max(440,min(650,self.window.height()-60)))
            self.timer.start(0);return
        dialog.setMinimumSize(600,600)
        dialog.resize(1400,800) if len(getattr(dialog,'panels',[]))==1 else dialog.resize(860,1480)
        # Comparison is one profile at a time, instead of two 510px panels side by side.
        outer=dialog.findChild(QScrollArea)
        if outer is not None and hasattr(dialog,'panels'):
            host=outer.takeWidget();tabs=QTabWidget()
            for panel in dialog.panels:
                if host.layout():host.layout().removeWidget(panel)
                tabs.addTab(panel,panel.name.text())
            dialog.layout().replaceWidget(outer,tabs);outer.hide();host.deleteLater()
        self.timer.start(0)

    def prune_deleted(self,scope=None):
        from shiboken6 import isValid
        owned=self.dialog_objects.get(scope,set())
        for store in (self.tables,self.boxes,self.tab_pickers,self.text_pages,self.dock_features):
            for obj in list(store):
                if not isValid(obj) or obj in owned:del store[obj]

    def release_dialog(self,dialog):
        self.prune_deleted(dialog)
        self.dialog_objects.pop(dialog,None)
        if dialog in self.dialogs:self.dialogs.remove(dialog)

    def reflow(self,layout,active):
        if not isinstance(layout,QLayout):return
        if isinstance(layout,QHBoxLayout) and layout not in self.boxes:
            self.boxes[layout]=layout.direction()
        if layout in self.boxes:
            # Header and navigation stay compact; crowded action/filter rows stack.
            width=layout.geometry().width()
            need=sum(layout.itemAt(i).minimumSize().width() for i in range(layout.count()))+layout.spacing()*max(0,layout.count()-1)
            direction=QBoxLayout.Direction.TopToBottom if active and width>0 and need>width else self.boxes[layout]
            if layout.direction()!=direction:layout.setDirection(direction)
        if active:
            margins=layout.contentsMargins()
            if max(margins.left(),margins.right())>14:layout.setContentsMargins(10,8,10,8)
            if layout.spacing()>8:layout.setSpacing(6)
        for i in range(layout.count()):
            if layout.itemAt(i).layout():self.reflow(layout.itemAt(i).layout(),active)
