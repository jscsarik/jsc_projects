"""User-sized screen regions, stored separately from the game save."""
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSplitter, QSplitterHandle


class RegionHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.SplitVCursor)
        self.setToolTip('이 경계선을 위아래로 드래그하여 두 영역의 높이 비율을 조절하세요.')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#eee0f5'))
        painter.setPen(QColor('#8b659d'))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '···  위아래로 드래그하여 영역 크기 조절  ···')


class PanelSplitter(QSplitter):
    def __init__(self, settings_path, key, parent=None, default_ratio=.35):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.key = 'panels/' + key
        self.default_ratio = default_ratio
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self.restore_ratio)
        self.setHandleWidth(22)
        self.setChildrenCollapsible(False)
        self.setOpaqueResize(True)
        self.splitterMoved.connect(self._remember)

    def createHandle(self):
        return RegionHandle(self.orientation(), self)

    def _ratio(self):
        try:
            ratio = float(self.settings.value(self.key, self.default_ratio))
            return ratio if .05 <= ratio <= .95 else self.default_ratio
        except (TypeError, ValueError):
            return self.default_ratio

    def restore_ratio(self):
        if self.count() != 2 or any(self.widget(i).isHidden() for i in range(2)):
            return
        height = max(1, self.height() - self.handleWidth())
        first = round(height * self._ratio())
        self.setSizes([first, height - first])

    def _remember(self, *_):
        sizes = self.sizes()
        if len(sizes) == 2 and min(sizes) > 0:
            self.settings.setValue(self.key, str(sizes[0] / sum(sizes)))
            self.settings.sync()

    def showEvent(self, event):
        super().showEvent(event)
        self.queue_restore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.queue_restore()

    def queue_restore(self):
        # The parent-owned timer is cancelled if a closing window is destroyed.
        if hasattr(self,'_restore_timer'):self._restore_timer.start(0)
