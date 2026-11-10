"""Resizable tables with UI-only preferences; never writes game SQLite data."""
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication,QHeaderView, QInputDialog, QMenu, QTableView as QtTableView, QTableWidget as QtTableWidget
from .agency_table_layout import CompanyHeader,agency_columns,fit_company_table,fit_all_columns,user_widths


class AdjustableColumns:
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if QApplication.instance().property('themeLayoutChanging'):return
        pager=getattr(self,'_portrait_pager',None)
        if self.property('paginateWithoutScroll') and pager is not None and pager.enabled and not pager.busy:
            pager.signature=None;pager.refresh()
        self._queue_uniform_columns()

    def showEvent(self,event):
        super().showEvent(event)
        self._queue_uniform_columns()

    def _queue_uniform_columns(self,*_):
        if QApplication.instance().property('themeLayoutChanging'):return
        timer=getattr(self,'_uniform_timer',None)
        if timer is not None:timer.start(0)

    def _fit_uniform_columns(self):
        if QApplication.instance().property('themeLayoutChanging'):return
        if self.property('compactProfileTable') or not self.isVisible():return
        if self.property('fitAllColumns'):
            self._restoring_columns=True
            try:fit_all_columns(self)
            finally:self._restoring_columns=False
            return
        pager=getattr(self,'_portrait_pager',None)
        if pager is not None and pager.enabled:
            visible=[c for c in range(self.model().columnCount()) if not self.isColumnHidden(c)]
            if not pager.busy and sum(self.columnWidth(c) for c in visible)>self.viewport().width():
                pager.signature=None;pager.refresh()
            return
        columns=[c for c in range(self.model().columnCount()) if not self.isColumnHidden(c)]
        if columns and agency_columns(self):
            self._restoring_columns=True
            try:fit_company_table(self,columns,self.viewport().width())
            finally:self._restoring_columns=False
            return
        if not columns:return
        width=max(1,self.viewport().width()//len(columns))
        widths=user_widths(self,columns,self.viewport().width(),{c:width for c in columns})
        self._restoring_columns=True
        try:
            self.horizontalHeader().setStretchLastSection(False)
            for c in columns:self.horizontalHeader().resizeSection(c,widths[c])
        finally:self._restoring_columns=False

    def setColumnHidden(self,column,hidden):
        super().setColumnHidden(column,hidden)
        self._queue_uniform_columns()
        pager=getattr(self,'_portrait_pager',None)
        if pager is not None and pager.enabled and not pager.busy:
            if hidden:pager.original_columns.add(column)
            else:pager.original_columns.discard(column)
            pager.signature=None;pager.queue()

    def bind_layout(self, path, key):
        if not self.property('compactProfileTable'):
            old=self.horizontalHeader();section=old.sortIndicatorSection();order=old.sortIndicatorOrder()
            clickable=old.sectionsClickable();movable=old.sectionsMovable()
            self.setHorizontalHeader(CompanyHeader(Qt.Orientation.Horizontal,self));self.horizontalHeader().setSortIndicator(section,order)
            self.horizontalHeader().setSectionsClickable(clickable);self.horizontalHeader().setSectionsMovable(movable)
        if not self.property('compactProfileTable'):key='uniform1/'+key
        self._layout_settings = QSettings(str(path), QSettings.Format.IniFormat)
        self._layout_key = key
        self._restoring_columns = False
        self._default_widths = [self.columnWidth(i) for i in range(self.model().columnCount())]
        self._default_row_height = self.verticalHeader().defaultSectionSize()
        try:
            height = int(self._layout_settings.value(key + '_row_height', self._default_row_height))
            self.verticalHeader().setDefaultSectionSize(max(24, min(200, height)))
            self._user_row_height=max(24,min(200,height)) if self._layout_settings.contains(key+'_row_height') else None
        except (ValueError, TypeError):
            pass
        raw = self._layout_settings.value(key, '')
        try:
            self._saved_widths = {int(i): max(1, min(4000, int(w))) for i, w in
                                  (part.split(':') for part in str(raw).split(',') if part)}
        except (ValueError, TypeError):
            self._saved_widths = {}
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(40)
        self.setShowGrid(False)
        header.setToolTip('열 제목 사이의 경계를 드래그하여 너비 조절 · 우클릭으로 기본 너비 복원')
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._column_menu)
        header.sectionResized.connect(self._column_resized)
        self._restore_columns()
        self.model().columnsInserted.connect(self._restore_columns)
        self.model().modelReset.connect(self._restore_columns)
        self._uniform_timer=QTimer(self);self._uniform_timer.setSingleShot(True)
        self._uniform_timer.timeout.connect(self._fit_uniform_columns)
        self.model().headerDataChanged.connect(self._queue_uniform_columns)
        self.model().dataChanged.connect(self._queue_uniform_columns)
        self._queue_uniform_columns()

    def _restore_columns(self, *_):
        self._restoring_columns = True
        try:
            for column, width in self._saved_widths.items():
                if column < self.model().columnCount():
                    super().setColumnWidth(column, width)
        finally:
            self._restoring_columns = False
        self._queue_uniform_columns()

    def setColumnWidth(self, column, width):
        # Reloading a page must not replace a user's chosen width with its defaults.
        if hasattr(self, '_default_widths'):
            while len(self._default_widths) <= column:
                self._default_widths.append(100)
            self._default_widths[column] = width
        if hasattr(self, '_saved_widths') and column in self._saved_widths:
            width = self._saved_widths[column]
        if hasattr(self, '_restoring_columns'):
            self._restoring_columns = True
            try:
                super().setColumnWidth(column, width)
            finally:
                self._restoring_columns = False
        else:
            super().setColumnWidth(column, width)
        self._queue_uniform_columns()

    def _column_resized(self, column, old, width):
        if self._restoring_columns or width < 1:
            return
        columns=[c for c in range(self.model().columnCount()) if not self.isColumnHidden(c)]
        if column not in columns:return
        available=max(1,self.viewport().width());minimum=min(24,max(1,available//len(columns)))
        self.horizontalHeader().setMinimumSectionSize(minimum)
        width=max(minimum,min(width,available-minimum*(len(columns)-1)))
        others=[c for c in columns if c!=column]
        sizes={column:width}
        if others:
            remaining=available-width;total=sum(self.columnWidth(c) for c in others) or 1
            spare=max(0,remaining-minimum*len(others))
            sizes.update({c:minimum+int(spare*self.columnWidth(c)/total) for c in others})
            for c in others[:available-sum(sizes.values())]:sizes[c]+=1
        self._restoring_columns=True
        try:
            for c,value in sizes.items():self.horizontalHeader().resizeSection(c,value)
        finally:self._restoring_columns=False
        self._saved_widths.update(sizes)
        self._layout_settings.setValue(self._layout_key, ','.join(
            f'{i}:{w}' for i, w in sorted(self._saved_widths.items())))
        self._layout_settings.sync()
        self._queue_uniform_columns()

    def reset_columns(self):
        self._saved_widths.clear()
        self._layout_settings.remove(self._layout_key)
        self._layout_settings.sync()
        self._restoring_columns = True
        try:
            for column, width in enumerate(self._default_widths):
                super().setColumnWidth(column, width)
        finally:
            self._restoring_columns = False
        self._queue_uniform_columns()

    def _column_menu(self, position):
        menu = QMenu(self)
        action = menu.addAction('이 표의 기본 열 너비로 복원')
        height_action = menu.addAction('행 높이 조절…')
        selected = menu.exec(self.horizontalHeader().mapToGlobal(position))
        if selected is action:
            self.reset_columns()
        elif selected is height_action:
            height, ok = QInputDialog.getInt(self, '행 높이', '이 표의 행 높이 (픽셀)',
                                            self.verticalHeader().defaultSectionSize(), 24, 200)
            if ok:
                self.verticalHeader().setDefaultSectionSize(height)
                self._user_row_height=height
                for row in range(self.model().rowCount()):self.setRowHeight(row,height)
                self._queue_uniform_columns()
                self._layout_settings.setValue(self._layout_key + '_row_height', height)
                self._layout_settings.sync()


class QTableView(AdjustableColumns, QtTableView):
    pass


class QTableWidget(AdjustableColumns, QtTableWidget):
    pass


def bind_window_tables(window, path):
    """Use page and attribute names as stable keys, independent of translated text."""
    pages = [('roster', window), ('draft', window.draft_page), ('squad', window.squad_page),
             ('schedule', window.schedule_page), ('match', window.match_page),
             ('special', window.special_page), ('finals', window.finals_page),
             ('development', window.development_page),('training',window.training_page),('explorer',window.explorer_page),('finance',window.finance_page),('market',window.market_page),('awards',window.awards_page),('annual',window.annual_page),('records',window.records_page)]
    seen = set()
    for page_name, page in pages:
        for name, value in vars(page).items():
            if isinstance(value, (QTableView, QTableWidget)) and id(value) not in seen:
                key=f'tables/{page_name}/{name}'
                if page_name=='market' and name in ('fa_table','renew_table','release_table','trainee_table'):key=f'tables/market/readable2/{name}'
                if page_name in ('match','finals','special') and name in ('live_table','records_table'):key=f'tables/{page_name}/phase_split2/{name}'
                value.bind_layout(path, key)
                seen.add(id(value))
