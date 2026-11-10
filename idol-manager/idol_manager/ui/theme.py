"""A soft backstage palette for management; the arena has its own stage lighting."""
STYLE = """
QWidget { background: #fcf8fc; color: #493f5d; font-family: 'Malgun Gothic'; font-size: 13px; }
QFrame#sidebar { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f3e5ff,stop:1 #ffe9ef); border-right: 1px solid #e8d9ef; }
QFrame#sidebar QLabel { background: transparent; }
QLabel#brand { font-size: 26px; font-weight: 800; color: #8554a1; }
QLabel#game_date { font-size: 17px; font-weight: bold; color: #825791; }
QFrame#game_header { background: #fffafd; border-bottom: 1px solid #eadced; }
QLabel#title { font-size: 28px; font-weight: bold; color: #77508d; }
QLabel#summary { background: #f1ebff; border: 1px solid #e3d6f4; border-radius: 16px; padding: 15px; }
QPushButton { background: #eee5fb; border: 1px solid #e0d0ee; border-radius: 12px; padding: 11px; font-weight: bold; }
QPushButton:hover { background: #f9dcec; border-color: #d9adcf; }
QPushButton:pressed { background: #e4c5ed; }
QPushButton:disabled { background: #f1edf3; color: #aaa0b3; border-color: #e8e1ec; }
QPushButton[navActive="true"] { background: #fff9ff; color: #9558b2; border: 2px solid #cda6e3; }
QPushButton#advanceDay { background: #e1f3ed; color: #417b6b; border-color: #bedfd3; }
QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #e4d8ec; border-radius: 10px; padding: 9px; selection-background-color: #e9d4f5; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #bc8bd2; }
QTableView { background: white; alternate-background-color: #fcf8ff; border: 1px solid #e8ddec; border-radius: 12px; gridline-color: transparent; selection-background-color: #f1dff6; selection-color: #633b77; }
QTableView::item { padding: 6px; border-bottom: 1px solid #f4eef7; }
QHeaderView::section { background: #f3eaf9; color: #886495; padding: 10px; border: 0; border-right: 1px solid #e8d9ef; border-bottom: 1px solid #e4d3ee; font-weight: bold; }
QTabWidget::pane { background: #fffaff; border: 1px solid #e7d9ef; border-radius: 12px; }
QTabBar::tab { background: #f2eaf8; padding: 10px 18px; margin: 2px; border-radius: 9px; }
QTabBar::tab:selected { background: #e4d0f1; color: #704487; font-weight: bold; }
QScrollBar:vertical { width: 13px; background: #f6eef9; }
QScrollBar:horizontal { height: 13px; background: #f6eef9; }
QScrollBar::handle { background: #d7bfdf; border-radius: 6px; min-height: 26px; min-width: 26px; }
QToolTip { background: #fff5fc; color: #704487; border: 1px solid #d9bfe5; padding: 6px; }
QProgressBar { background: #f0e7f6; border: 0; border-radius: 6px; text-align: center; min-height: 12px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b695dd,stop:1 #ef99c5); border-radius: 6px; }
QGroupBox { border: 1px solid #e5d9ed; border-radius: 12px; margin-top: 10px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #9667a6; }
"""
