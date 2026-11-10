from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt,QSortFilterProxyModel

SKILL_NAMES=('보컬','댄스','랩','예능','외모','신체','지성','리더십')
SORT_ROLE=Qt.ItemDataRole.UserRole+1


class DraftCandidateProxy(QSortFilterProxyModel):
    def __init__(self,parent=None):
        super().__init__(parent);self.min_age=0;self.max_age=100;self.status='available'
        self.setSortRole(SORT_ROLE)

    def filterAcceptsRow(self,row,parent):
        p=self.sourceModel().rows[row]
        status_ok=(self.status=='all' or (self.status=='available' and p.pick_number is None) or (self.status=='picked' and p.pick_number is not None))
        return status_ok and self.min_age<=p.age<=self.max_age and super().filterAcceptsRow(row,parent)


class BlindCandidateModel(QAbstractTableModel):
    HEADERS = ("사진", "이름", "나이",*SKILL_NAMES,"추정 종합","상태")

    def __init__(self, thumbnails, parent=None):
        super().__init__(parent)
        self.rows = []
        self.thumbnails = thumbnails
        thumbnails.changed.connect(self._photos_changed)

    def replace(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        person = self.rows[index.row()]
        column = index.column()
        if role==SORT_ROLE:
            return ((None,person.name,person.age)[column] if column<3 else
                    person.estimates[column-3].midpoint if column<11 else
                    person.estimated_overall if column==11 else person.status)
        if role == Qt.ItemDataRole.DisplayRole:
            return ((None,person.name,person.age)[column] if column<3 else
                    str(person.estimates[column-3]) if column<11 else
                    person.estimated_overall if column==11 else person.status)
        if role==Qt.ItemDataRole.ToolTipRole and column>=3:
            return '현재 능력치의 추정 범위이며 잠재력 상한이 아닙니다. 추정 종합은 범위 중간값 8개의 평균입니다.'
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            return self.thumbnails.get(person.photo_path)
        if role == Qt.ItemDataRole.TextAlignmentRole and column == 2:
            return Qt.AlignmentFlag.AlignCenter
        return None

    def _photos_changed(self):
        if self.rows:
            self.dataChanged.emit(self.index(0,0),self.index(len(self.rows)-1,0),[Qt.ItemDataRole.DecorationRole])


class DraftHistoryModel(QAbstractTableModel):
    HEADERS = ("전체 지명", "라운드", "기획사", "이름")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.names = {}

    def replace(self, rows, names):
        self.beginResetModel()
        self.rows, self.names = list(rows), names
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (row.pick_number,row.round_number,self.names.get(row.agency_id,row.agency_id),row.name)[index.column()]
        return None
