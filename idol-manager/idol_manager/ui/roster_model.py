from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from ..domain import PublicIdol
from .thumbnails import ThumbnailCache

STATUS_LABELS = {
    "candidate": "드래프트 후보", "unassigned": "미배정", "first_team": "1군",
    "second_team": "2군", "fa": "FA", "retired": "은퇴", "trainee": "연습생",
    "pro_pending": "프로(편성 대기)",
}


class RosterModel(QAbstractTableModel):
    HEADERS = ("사진", "이름", "가상 나이", "상태")

    def __init__(self, thumbnails: ThumbnailCache, parent=None):
        super().__init__(parent)
        self.rows: list[PublicIdol] = []
        self.thumbnails = thumbnails
        thumbnails.changed.connect(self._refresh_photos)

    def replace(self, rows: list[PublicIdol]):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        person = self.rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (None, person.name, person.age, STATUS_LABELS.get(person.status, person.status))[column]
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            return self.thumbnails.get(person.photo_path)
        if role == Qt.ItemDataRole.ForegroundRole and column == 3:
            return QColor("#5975a3")
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (0, 2):
            return Qt.AlignmentFlag.AlignCenter
        return None

    def _refresh_photos(self):
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0),
                                  [Qt.ItemDataRole.DecorationRole])
