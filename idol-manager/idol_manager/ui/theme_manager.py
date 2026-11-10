"""Application-wide, reversible UI themes; preferences never touch save databases."""
import re
from PySide6.QtCore import QObject,QEvent,QSettings,Signal,Qt,QTimer
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QApplication,QWidget,QPushButton,QMenu,QTableView,QMainWindow
from shiboken6 import isValid
from .theme import STYLE


def dark_color(value):
    color=QColor(value)
    hue,saturation,lightness,alpha=color.getHslF()
    if lightness>.86:return '#292c3b' if saturation<.35 else '#343043'
    if lightness>.65:return '#514563'
    if lightness<.65:
        color.setHslF(hue,max(.12,saturation*.65),max(.72,lightness),alpha)
    return color.name()


def dark_style(style):
    style=re.sub(r'#[0-9a-fA-F]{6}\b',lambda m:dark_color(m[0]),style)
    return re.sub(r'(?<=:)\s*white\b',' #292c3b',style,flags=re.I)


DARK_EXTRA='''
QWidget {background:#202330;color:#e9e6f0;}
QLabel {background:transparent;}
QFrame#sidebar {background:#292638;border-color:#454052;}
QLabel#brand,QLabel#title,QLabel#game_date {color:#cda8ef;}
QPushButton {background:#42364f;border-color:#625071;color:#eee8f4;}
QPushButton:hover {background:#614b73;border-color:#bc91d9;}
QPushButton:pressed {background:#76558b;}
QPushButton:disabled {background:#30313e;color:#a9a4b5;border-color:#484451;}
QPushButton[navActive="true"] {background:#554065;color:#f5e8ff;border-color:#bd90db;}
QPushButton#advanceDay {background:#28473f;color:#b9eadc;border-color:#4e7b6e;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit,QTextBrowser {
 background:#292c3b;color:#ece8f3;selection-background-color:#654e7c;selection-color:#fff;}
QTableView {background:#292c3b;alternate-background-color:#303242;color:#ece8f3;
 selection-background-color:#624877;selection-color:#fff;border-color:#474153;}
QTableView::item {background:#292c3b;color:#ece8f3;border-bottom-color:#393747;}
QTableView::item:alternate {background:#303242;}
QTableView::item:selected {background:#624877;color:#fff;}
QHeaderView::section {background:#3a3249;color:#dfc9f1;border-color:#50435e;}
QMenu,QComboBox QAbstractItemView {background:#2e2b3c;color:#eee8f4;border:1px solid #625071;}
QMenu::item:selected,QComboBox QAbstractItemView::item:selected {background:#624877;color:#fff;}
QMenu::item:disabled {color:#a9a4b5;}
QToolTip {background:#393046;color:#f3eafa;border-color:#8d6aa5;}
QScrollBar {background:#252735;}
QScrollBar::handle {background:#685474;}
QScrollBar::add-line,QScrollBar::sub-line,QScrollBar::add-page,QScrollBar::sub-page {background:#252735;}
QCheckBox,QRadioButton,QGroupBox {color:#e9e6f0;}
QCheckBox::indicator,QRadioButton::indicator {border:1px solid #a88ac1;background:#292c3b;}
QCheckBox::indicator:checked,QRadioButton::indicator:checked {background:#b995d9;}
'''


class ThemeManager(QObject):
    changed=Signal(str)

    def __init__(self,application,settings_path):
        super().__init__(application)
        self.app=application;self.settings=QSettings(str(settings_path),QSettings.Format.IniFormat)
        self.light_palette=QPalette(application.palette());self._busy=False
        self._layout_snapshot=None;self._layout_generation=0
        self.mode='light';application.theme_manager=self
        application.installEventFilter(self)
        self.set_mode(str(self.settings.value('appearance/theme','light')),persist=False)

    def _stage(self,widget):
        current=widget
        while current:
            if current.objectName()=='battleStage':return True
            current=current.parentWidget()
        return False

    def _style_widget(self,widget):
        if self._stage(widget):return
        current=widget.styleSheet()
        applied=getattr(widget,'_theme_applied_style',None)
        if current!=applied:widget._theme_light_style=current
        original=getattr(widget,'_theme_light_style',current)
        rendered=(dark_style(original)+(DARK_EXTRA if original.startswith(STYLE) else '')) if self.mode=='dark' else original
        widget._theme_applied_style=rendered
        if current!=rendered:widget.setStyleSheet(rendered)

    def eventFilter(self,obj,event):
        if not self._busy and isinstance(obj,QWidget) and event.type() in (QEvent.Type.Polish,QEvent.Type.Show,QEvent.Type.StyleChange):
            self._busy=True
            try:self._style_widget(obj)
            finally:self._busy=False
        return False

    def _hold_layout(self):
        self._layout_generation+=1
        if self._layout_snapshot is None:
            tables=[];docks=[];windows=[]
            for widget in self.app.allWidgets():
                if not widget.isVisible():continue
                if widget.isWindow():
                    windows.append((widget,widget.size(),widget.updatesEnabled()));widget.setUpdatesEnabled(False)
                if isinstance(widget,QMainWindow):docks.append((widget,widget.saveState()))
                if isinstance(widget,QTableView):
                    headers=[]
                    for header in (widget.horizontalHeader(),widget.verticalHeader()):
                        headers.append((header,header.saveState(),header.blockSignals(True)))
                    tables.append((widget,widget.window().size(),headers,widget.horizontalScrollBar().value(),widget.verticalScrollBar().value()))
            self._layout_snapshot=(tables,docks,windows)
        self.app.setProperty('themeLayoutChanging',bool(self._layout_snapshot[0]))
        return self._layout_generation

    def _restore_layout(self,generation,finish=False):
        if generation!=self._layout_generation or self._layout_snapshot is None:return
        tables,docks,windows=self._layout_snapshot
        sizes={w:size for w,size,_ in windows if isValid(w)}
        for widget,state in docks:
            if isValid(widget) and widget.window().size()==sizes.get(widget.window(),widget.window().size()):widget.restoreState(state)
        for table,window_size,headers,hscroll,vscroll in tables:
            if not isValid(table):continue
            if table.window().size()==window_size:
                previous=getattr(table,'_restoring_columns',False);table._restoring_columns=True
                try:
                    for header,state,_ in headers:
                        if isValid(header):header.restoreState(state)
                    table.horizontalScrollBar().setValue(hscroll);table.verticalScrollBar().setValue(vscroll)
                finally:table._restoring_columns=previous
        if not finish:return
        self._layout_snapshot=None;self.app.setProperty('themeLayoutChanging',False)
        for table,window_size,headers,_,_ in tables:
            for header,_,blocked in headers:
                if isValid(header):header.blockSignals(blocked)
            if isValid(table) and table.window().size()!=window_size:
                table._queue_uniform_columns() if hasattr(table,'_queue_uniform_columns') else None
                pager=getattr(table,'_portrait_pager',None)
                if pager:pager.signature=None;pager.queue()
        for window,_,enabled in windows:
            if isValid(window):window.setUpdatesEnabled(enabled)

    def set_mode(self,mode,persist=True):
        mode=mode if mode in ('light','dark') else 'light'
        generation=self._hold_layout()
        self.mode=mode;self._busy=True
        try:
            palette=QPalette(self.light_palette)
            if mode=='dark':
                for role,color in ((QPalette.ColorRole.Window,'#202330'),(QPalette.ColorRole.WindowText,'#e9e6f0'),
                    (QPalette.ColorRole.Base,'#292c3b'),(QPalette.ColorRole.AlternateBase,'#303242'),
                    (QPalette.ColorRole.Text,'#e9e6f0'),(QPalette.ColorRole.Button,'#42364f'),
                    (QPalette.ColorRole.ButtonText,'#eee8f4'),(QPalette.ColorRole.Highlight,'#624877'),
                    (QPalette.ColorRole.HighlightedText,'#ffffff'),(QPalette.ColorRole.PlaceholderText,'#aaa1b8')):
                    palette.setColor(role,QColor(color))
                palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.Text,QColor('#aaa4b5'))
                palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.ButtonText,QColor('#aaa4b5'))
            self.app.setPalette(palette)
            self.app.setStyleSheet(dark_style(STYLE)+DARK_EXTRA if mode=='dark' else STYLE)
            for widget in self.app.allWidgets():self._style_widget(widget)
        finally:
            self._busy=False
            QTimer.singleShot(0,lambda:self._restore_layout(generation))
            QTimer.singleShot(75,lambda:self._restore_layout(generation,True))
        if persist:self.settings.setValue('appearance/theme',mode);self.settings.sync()
        self.changed.emit(mode)


def settings_button(parent):
    button=QPushButton('⚙',parent);button.setAccessibleName('화면 테마 설정')
    button.setToolTip('화면 설정');button.setFixedSize(30,30)
    button.setStyleSheet('padding:0;border-radius:8px;font-size:18px;')
    menu=QMenu(button)
    manager=getattr(QApplication.instance(),'theme_manager',None)
    for mode,title in (('light','라이트 모드'),('dark','다크 모드')):
        action=menu.addAction(title);action.setCheckable(True)
        action.setData(mode)
        action.triggered.connect(lambda checked=False,m=mode:manager and manager.set_mode(m))
        if manager:
            action.setChecked(manager.mode==mode)
    menu.aboutToShow.connect(lambda:[action.setChecked(manager.mode==action.data()) for action in menu.actions()] if manager else None)
    button.setMenu(menu)
    return button
