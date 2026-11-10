from PySide6.QtCore import QEasingCurve,QPropertyAnimation,QTimer,Qt
from PySide6.QtWidgets import (QCheckBox,QGraphicsOpacityEffect,QHBoxLayout,QLabel,QMenu,
    QPushButton,QSlider,QToolButton,QVBoxLayout,QWidget,QWidgetAction)


class MusicToast(QLabel):
    def __init__(self,parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setStyleSheet('background: #e1f0ea; color: #355b50; border: 1px solid #c5ded1; border-radius: 9px; padding: 8px 14px; font-weight: bold;')
        self.effect=QGraphicsOpacityEffect(self);self.setGraphicsEffect(self.effect)
        self.hold=QTimer(self);self.hold.setSingleShot(True);self.hold.setInterval(1500)
        self.hold.timeout.connect(self._fade)
        self.animation=QPropertyAnimation(self.effect,b'opacity',self);self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad);self.animation.finished.connect(self.hide)
        self.full_text='';self.hide()

    def show_song(self,title):
        self.hold.stop();self.animation.stop();self.effect.setOpacity(1.0)
        self.full_text='♪ '+title;self.setToolTip(self.full_text);self.reposition()
        self.show();self.raise_();self.hold.start()

    def reposition(self):
        maximum=max(120,min(540,self.parentWidget().width()-40))
        self.setText(self.fontMetrics().elidedText(self.full_text,Qt.TextElideMode.ElideRight,maximum-30))
        self.adjustSize();self.move(max(10,(self.parentWidget().width()-self.width())//2),12)

    def _fade(self):
        self.animation.setStartValue(1.0);self.animation.setEndValue(0.0);self.animation.start()


class BgmControls(QToolButton):
    def __init__(self,manager,parent=None):
        super().__init__(parent)
        self.manager=manager;self.setAccessibleName('BGM 설정');self.setText('♪ BGM')
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu=QMenu(self);panel=QWidget();panel.setMinimumWidth(330)
        layout=QVBoxLayout(panel);layout.setContentsMargins(15,12,15,12)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.counts=QLabel();layout.addWidget(self.status);layout.addWidget(self.counts)
        self.enabled_box=QCheckBox('BGM 켜기');self.muted_box=QCheckBox('음소거')
        flags=QHBoxLayout();flags.addWidget(self.enabled_box);flags.addWidget(self.muted_box);layout.addLayout(flags)
        self.volume_label=QLabel();self.volume_slider=QSlider(Qt.Orientation.Horizontal);self.volume_slider.setRange(0,100)
        self.volume_slider.setAccessibleName('BGM 볼륨');layout.addWidget(self.volume_label);layout.addWidget(self.volume_slider)
        row=QHBoxLayout();self.pause_button=QPushButton('일시정지');self.next_button=QPushButton('다음 곡')
        row.addWidget(self.pause_button);row.addWidget(self.next_button);layout.addLayout(row)
        self.refresh_button=QPushButton('음악 목록 새로고침');layout.addWidget(self.refresh_button)
        action=QWidgetAction(self.menu);action.setDefaultWidget(panel);self.menu.addAction(action);self.setMenu(self.menu)
        self.enabled_box.toggled.connect(manager.set_enabled);self.muted_box.toggled.connect(manager.set_muted)
        self.volume_slider.valueChanged.connect(manager.set_volume);self.pause_button.clicked.connect(manager.toggle_pause)
        self.next_button.clicked.connect(manager.next_track);self.refresh_button.clicked.connect(manager.refresh)
        manager.state_changed.connect(self.refresh);manager.playlists_changed.connect(self.refresh);self.refresh()

    def refresh(self):
        manager=self.manager
        for widget,value in ((self.enabled_box,manager.enabled),(self.muted_box,manager.muted)):
            widget.blockSignals(True);widget.setChecked(value);widget.blockSignals(False)
        self.volume_slider.blockSignals(True);self.volume_slider.setValue(manager.volume);self.volume_slider.blockSignals(False)
        self.volume_label.setText(f'볼륨 {manager.volume}%')
        self.pause_button.setText('재생' if manager.paused else '일시정지')
        self.pause_button.setEnabled(manager.enabled);self.next_button.setEnabled(manager.enabled)
        self.refresh_button.setEnabled(not manager.scanning)
        self.counts.setText(f"일반 {len(manager.bags['default'].tracks)}곡 · 배틀 {len(manager.bags['battle'].tracks)}곡")
        self.status.setText((manager.current_track.title+'\n' if manager.current_track else '')+
                            manager.status)
        self.setText('♪ 꺼짐' if not manager.enabled else ('♪ 음소거' if manager.muted else '♪ BGM'))
