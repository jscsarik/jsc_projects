import sqlite3
from PySide6.QtCore import QObject,QSize,QSortFilterProxyModel,Qt
from PySide6.QtWidgets import QTableView,QTableWidget,QMessageBox
from .profile_dialog import ProfileDialog
from .match_page import PROFILE_ROLE
from .thumbnails import ThumbnailCache


class ProfileController(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.dialog=None
        self.photos=ThumbnailCache(window.service.image_root,window.service.cache_dir/'profile_thumbnails',self,image_size=QSize(360,480))
        for table in window.findChildren(QTableView):table.clicked.connect(lambda index,t=table:self.clicked(t,index))
        for page in (window.match_page,window.finals_page):page.battle.profile_requested.connect(self.open)
        window.explorer_page.compare_requested.connect(self.compare)

    def clicked(self,table,index):
        if not index.isValid():return
        person=index.data(PROFILE_ROLE)
        if person:self.open(person);return
        if isinstance(table,QTableWidget):
            # Lineups and growth tables already carry the authoritative ID.
            if table in (self.window.match_page.lineup_table,self.window.finals_page.lineup_table,self.window.special_page.lineup_table) and index.column()==1:
                person=table.item(index.row(),0).data(Qt.ItemDataRole.UserRole)
            elif table is self.window.development_page.table and index.column() in (0,1):person=table.item(index.row(),0).data(Qt.ItemDataRole.UserRole)
            else:return
        else:
            model=table.model();source=index
            while isinstance(model,QSortFilterProxyModel):source=model.mapToSource(source);model=model.sourceModel()
            if not hasattr(model,'rows') or source.row()>=len(model.rows):return
            allowed=(1,2) if table is self.window.squad_page.table else (3,) if table is self.window.draft_page.history_table else (0,1)
            if index.column() not in allowed:return
            row=model.rows[source.row()];person=getattr(row,'id',None) or getattr(row,'person_id',None)
        if person:self.open(person)

    def open(self,person):self.compare([person])

    def compare(self,people):
        try:
            # Use one window; the common panels also supply two-player comparison.
            if self.dialog is not None:self.dialog.close()
            self.dialog=ProfileDialog(self.window.service,self.photos,people,self.window)
            if hasattr(self.window,'portrait_layout'):self.window.portrait_layout.prepare_dialog(self.dialog)
            self.dialog.finished.connect(self._closed);self.dialog.show()
        except (ValueError,RuntimeError,sqlite3.Error) as error:
            QMessageBox.warning(self.window,'프로필 안내',str(error))

    def _closed(self,*_):self.dialog=None
    def refresh(self):
        if self.dialog is not None:
            for panel in self.dialog.panels:panel.reload()
    def shutdown(self):
        if self.dialog is not None:self.dialog.close()
        self.photos.close()
