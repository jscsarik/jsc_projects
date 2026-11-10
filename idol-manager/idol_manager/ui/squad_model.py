from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QFont,QColor

from ..config import SKILLS

SQUAD_LABELS = {"pro_pending":"편성 대기","first_team":"1군","second_team":"2군","trainee":"연습생"}


class SquadModel(QAbstractTableModel):
    selection_changed = Signal()
    SORT_ROLE = int(Qt.ItemDataRole.UserRole)+1
    HEADERS = ("1군 선택","사진","이름","나이","선수단","평균","보컬","댄스","랩","예능","외모","신체","지성","리더십","건강","1군 연속 등록(주)","필요 휴식(주)")

    def __init__(self, thumbnails, parent=None):
        super().__init__(parent)
        self.rows = []
        self.selected_ids = set()
        self.editable = False
        self.conditions={}
        self.thumbnails = thumbnails
        thumbnails.changed.connect(self._photos_changed)

    def replace(self, rows, editable, conditions=None):
        self.beginResetModel()
        self.rows = list(rows)
        self.editable = editable
        self.conditions=conditions or {}
        self.selected_ids.intersection_update(member.id for member in self.rows if member.squad in ("pro_pending","first_team","second_team"))
        self.endResetModel()
        self.selection_changed.emit()

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if orientation==Qt.Orientation.Horizontal and role==Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.rows):
            return None
        member = self.rows[index.row()]
        column = index.column()
        if role==Qt.ItemDataRole.CheckStateRole and column==0 and member.squad in ("pro_pending","first_team","second_team") and self.editable:
            return Qt.CheckState.Checked if member.id in self.selected_ids else Qt.CheckState.Unchecked
        if role==Qt.ItemDataRole.DecorationRole and column==1:
            return self.thumbnails.get(member.photo_path)
        values = (None,None,member.name,member.age,SQUAD_LABELS.get(member.squad,member.squad),
                  member.average,*member.skill_values,member.health,*self.conditions.get(member.id,(None,None)))
        if role==Qt.ItemDataRole.ToolTipRole and column>=15:
            return '필요 휴식은 앞으로 더 쉬어야 하는 주 수입니다. 완료한 완전한 2군 휴식 주를 차감하며 건강 회복을 뜻하지 않습니다.'
        if role==Qt.ItemDataRole.FontRole and column>=5:
            font=QFont();font.setPixelSize(15);font.setBold(True);return font
        if role==Qt.ItemDataRole.ForegroundRole and 6<=column<=14:
            return QColor('#24745a' if values[column]>=80 else '#345b85' if values[column]>=60 else '#685673')
        if role==self.SORT_ROLE:
            return values[column]
        if role==Qt.ItemDataRole.DisplayRole:
            return f"{member.average:.1f}" if column==5 else '기록 없음' if column>=15 and values[column] is None else values[column]
        if role==Qt.ItemDataRole.TextAlignmentRole and column>=3:
            return Qt.AlignmentFlag.AlignCenter
        return None

    def flags(self,index):
        flags = super().flags(index)
        if index.isValid() and index.column()==0 and self.editable and self.rows[index.row()].squad in ("pro_pending","first_team","second_team"):
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self,index,value,role=Qt.ItemDataRole.EditRole):
        if role!=Qt.ItemDataRole.CheckStateRole or not index.isValid() or index.column()!=0 or not self.editable:
            return False
        member = self.rows[index.row()]
        if member.squad not in ("pro_pending","first_team","second_team"):
            return False
        if value in (Qt.CheckState.Checked,Qt.CheckState.Checked.value):
            self.selected_ids.add(member.id)
        else:
            self.selected_ids.discard(member.id)
        self.dataChanged.emit(index,index,[Qt.ItemDataRole.CheckStateRole])
        self.selection_changed.emit()
        return True

    def _photos_changed(self):
        if self.rows:
            self.dataChanged.emit(self.index(0,1),self.index(len(self.rows)-1,1),[Qt.ItemDataRole.DecorationRole])


class SquadFilter(QSortFilterProxyModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.name_query = ""
        self.squad = "pro"
        self.setSortRole(SquadModel.SORT_ROLE)

    def set_query(self,text):
        self.name_query = text.strip().casefold()
        self.invalidate()

    def set_squad(self,squad):
        self.squad = squad
        self.invalidate()

    def filterAcceptsRow(self,row,parent):
        member = self.sourceModel().rows[row]
        squad_match = member.squad!="trainee" if self.squad=="pro" else member.squad==self.squad
        return squad_match and self.name_query in member.name.casefold()
