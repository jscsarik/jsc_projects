"""Tuesday focus selection and a read-only view of saved Monday trials."""
from PySide6.QtCore import Qt,QSize,QRectF
from PySide6.QtGui import QIcon,QColor,QLinearGradient,QPen
from PySide6.QtWidgets import QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QMessageBox,QStyledItemDelegate,QStyle,QApplication
from .match_page import make_table,fill_table
from .draft_models import SKILL_NAMES
from ..config import SKILLS
from ..game_clock import GameDate
from ..training_service import FOCUS_COST

NAMES=dict(zip(SKILLS,SKILL_NAMES))

class SkillButtonDelegate(QStyledItemDelegate):
    """Raised ability buttons without adding widgets or changing table geometry."""
    def __init__(self,page):super().__init__(page.table);self.page=page
    def paint(self,painter,option,index):
        page=self.page;identity=index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        chosen=page.choices().get(identity)==SKILLS[index.column()-4]
        enabled=page.editable();dark=getattr(getattr(QApplication.instance(),'theme_manager',None),'mode','light')=='dark'
        r=QRectF(option.rect).adjusted(4,7,-4,-7)
        if r.height()>34:r.setTop(r.center().y()-17);r.setHeight(34)
        painter.save();painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.fillRect(option.rect,option.palette.highlight() if option.state & QStyle.StateFlag.State_Selected else option.palette.base())
        shadow=QColor('#16121e' if dark else '#cbb6dc')
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(shadow);painter.drawRoundedRect(r.translated(0,3),5,5)
        top,bottom=('#8561a5','#624281') if chosen else (('#51465e','#393140') if dark else ('#ffffff','#eee3f8'))
        if enabled and option.state & QStyle.StateFlag.State_MouseOver:top,bottom=('#a47ac7','#8057a1') if chosen else (('#6b557e','#4c3c5c') if dark else ('#fffaff','#dfc9ef'))
        gradient=QLinearGradient(r.topLeft(),r.bottomLeft());gradient.setColorAt(0,QColor(top));gradient.setColorAt(1,QColor(bottom))
        painter.setBrush(gradient);painter.setPen(QPen(QColor('#b789d5' if chosen else '#9b7ab2'),2 if chosen else 1));painter.drawRoundedRect(r,5,5)
        painter.setPen(QColor('#faf5ff' if chosen or dark else '#503268') if enabled else QColor('#aaa0b5' if dark else '#82758b'))
        font=option.font;font.setBold(chosen);painter.setFont(font)
        painter.drawText(r,Qt.AlignmentFlag.AlignCenter,str(index.data()));painter.restore()

class TrainingDetails(QDialog):
    def __init__(self,rows,settings,parent=None,*,name=''):
        super().__init__(parent);self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f'{name} · 성장 판정 상세' if name else '성장 판정 상세')
        area=self.screen().availableGeometry();self.resize(min(1400,area.width()-40),min(760,area.height()-80))
        layout=QVBoxLayout(self);notice=QLabel(f'{GameDate(rows[0]["day"])} · 저장된 월요일 정산 결과' if rows else '이번 주 성장 결과 없음')
        if name:notice.setText(name+' · '+notice.text())
        notice.setWordWrap(True);layout.addWidget(notice)
        self.table=make_table();self.table.setProperty('fitAllColumns',True);self.table.setWordWrap(True);layout.addWidget(self.table,1)
        self.table.setProperty('columnPreferences',[80,155,70,90,90,165,90,70,80])
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        def probability(value):return '—' if value is None else f'{value*100:g}%'
        data=[]
        for r in rows:
            result=r['success'] if isinstance(r['success'],str) else ('성공' if r['success'] else '실패')
            data.append((NAMES.get(r['skill'],'—'),r['kind'],r['before'] if r['before'] is not None else '—',
                '비공개' if r['kind']=='PA 격차 추가 성장' else probability(r['up']),probability(r['down']),result,
                f'{r["delta"]:+d}' if r['delta'] else '변화 없음',r['final'] if r['final'] is not None else '—','O' if r['prevented'] else ''))
        fill_table(self.table,('능력치','판정 종류','판정 전','상승 확률','하락 확률','판정 결과','실제 변화','최종','하락 방지'),data)
        self.table.bind_layout(settings/'ui_layout.ini','training/details')
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hint=QLabel('확률·성공 여부·변화량은 저장 기록입니다. PA 수치·상한·PA 기반 내부 확률은 공개하지 않습니다.')
        hint.setWordWrap(True);layout.addWidget(hint)
        close=QPushButton('닫기');close.clicked.connect(self.close);layout.addWidget(close)

class TrainingPage(QWidget):
    def __init__(self,service,parent=None,*,thumbnails=None):
        super().__init__(parent);self.service=service;self.snapshot=None;self.detail_dialog=None;self.thumbnails=thumbnails;self.pending={}
        layout=QVBoxLayout(self);layout.setContentsMargins(20,16,20,16)
        title=QLabel('훈련');title.setObjectName('title');layout.addWidget(title);self.heading=title
        self.notice=QLabel();self.notice.setWordWrap(True);self.notice.setMinimumWidth(0);layout.addWidget(self.notice)
        hint=QLabel('화요일: 2군 집중 훈련 선택·확정 / 월요일: 지난주 월~일 성장 정산\n2군 기본 훈련 주 10만원(기존 정규 시즌 정산) · 집중 훈련 주 15만원 추가(확정 시 지급) · 1군 집중 훈련 미지원')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.table=make_table();self.table.setProperty('fitAllColumns',True);self.table.setWordWrap(True);layout.addWidget(self.table,1)
        self.table.setProperty('columnPreferences',[52,100,48,55,*([48]*8),85,80,80,170])
        self.table.setIconSize(QSize(44,52));self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.setProperty('requiredVisibleColumns',[0,1,3])
        self.skill_buttons=SkillButtonDelegate(self)
        for column in range(4,12):self.table.setItemDelegateForColumn(column,self.skill_buttons)
        self.table.setMouseTracking(True)
        self.table.entered.connect(lambda index:self.table.viewport().setCursor(Qt.CursorShape.PointingHandCursor if self.editable() and 4<=index.column()<12 else Qt.CursorShape.ArrowCursor))
        controls=QHBoxLayout();self.focus=QComboBox();self.focus.addItem('집중 훈련 없음',None)
        for skill,name in NAMES.items():self.focus.addItem(name,skill)
        self.apply=QPushButton('선택 적용');self.apply.clicked.connect(self.apply_choice)
        self.confirm=QPushButton('이번 주 훈련 확정');self.confirm.clicked.connect(self.confirm_choices)
        refresh=QPushButton('새로 불러오기');refresh.clicked.connect(self.reload)
        for w in (self.focus,self.apply,self.confirm,refresh):controls.addWidget(w)
        layout.addLayout(controls)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table.itemSelectionChanged.connect(self.selected);self.table.cellDoubleClicked.connect(self.open_details)
        self.table.cellClicked.connect(self.choose_cell);self.focus.currentIndexChanged.connect(self.choose_combo)
        if self.thumbnails:self.thumbnails.changed.connect(self.photos)
        self.reload()

    def agency(self):return self.service.draft_session.player_agency()
    def current_person(self):
        row=self.table.currentRow()
        return self.table.item(row,0).data(Qt.ItemDataRole.UserRole) if row>=0 and self.table.item(row,0) else None

    def reload(self,*_):
        agency=self.agency();self.snapshot=self.service.training.state(agency);self.pending.clear()
        names={a.id:a.name for a in self.service.agencies()};day=self.snapshot['day']
        self.notice.setText(f'{names.get(agency,"플레이어 기획사를 선택해 주세요.")} · {day or "새 게임을 시작해 주세요."}')
        self.table.blockSignals(True);self.table.setSortingEnabled(False)
        data=[]
        visible=[p for p in self.snapshot['players'] if p['career_status']=='second_team']
        for p in visible:
            cost=FOCUS_COST if p['focus'] else 0
            last='이번 주 성장 결과 없음' if p['last_day'] is None else f'{GameDate(p["last_day"])} · 합계 {p["last_delta"]:+d}'
            status=('확정' if p['focus'] else '훈련 없음') if self.snapshot['confirmed'] else ('선택 중' if p['focus'] else '미선택')
            if p['career_status']=='first_team':status='화요일 2군 확정' if p['focus'] and self.snapshot['confirmed'] else '1군 미지원'
            data.append(('',p['name'],'2군',round(sum(p['skills'])/8,1),*p['skills'],NAMES.get(p['focus'],'없음'),
                status,f'{cost:,}원',last))
        fill_table(self.table,('사진','이름','선수단','평균',*SKILL_NAMES,'집중 능력치','적용 상태','추가 비용','마지막 월요일 결과'),data)
        for row,p in enumerate(visible):
            self.table.item(row,0).setData(Qt.ItemDataRole.UserRole,p['id'])
            for column in range(4,12):self.table.item(row,column).setToolTip('클릭하여 집중 훈련 선택 · 다시 클릭하면 해제')
        self.table.setSortingEnabled(True);self.table.blockSignals(False)
        if self.table.rowCount():self.table.selectRow(0)
        self.selected()
        self.photos()

    def photos(self):
        if not self.thumbnails or not self.snapshot:return
        paths={p['id']:p['photo_path'] for p in self.snapshot['players']}
        for row in range(self.table.rowCount()):
            item=self.table.item(row,0)
            if item and item.data(Qt.ItemDataRole.UserRole) in paths:
                item.setIcon(QIcon(self.thumbnails.get(paths[item.data(Qt.ItemDataRole.UserRole)])))

    def editable(self):
        d=self.snapshot['day']
        return bool(self.agency() and d and not d.is_founding and d.weekday()==1 and (d.is_regular or d.is_postseason) and not self.snapshot['confirmed'])

    def selected(self):
        p=next((p for p in self.snapshot['players'] if p['id']==self.current_person()),None)
        self.focus.blockSignals(True)
        self.focus.setCurrentIndex(max(0,self.focus.findData(self.pending.get(p['id'],p['focus']) if p else None)))
        self.focus.blockSignals(False)
        enabled=self.editable();second=p and p['career_status']=='second_team'
        self.focus.setEnabled(bool(enabled and second));self.apply.setEnabled(bool(enabled and second));self.confirm.setEnabled(enabled)
        amount=sum(skill is not None for skill in self.choices().values())*FOCUS_COST
        reason='2군 선수를 선택해 주세요.' if enabled else ('이번 주 훈련 확정 완료' if self.snapshot['confirmed'] else '집중 훈련 설정은 정규·포스트시즌 화요일에만 가능합니다.')
        if not self.agency():reason='플레이어 기획사가 선택되지 않았습니다.'
        elif enabled and p and not second:reason='1군 집중 훈련의 효과·비용은 아직 적용하지 않습니다.'
        self.status.setText(f'선택한 집중 훈련 비용: {amount:,}원 · 일괄 적용 대기 {len(self.pending)}명 · {reason}\n능력치 숫자 클릭 → 선수별 선택 → 선택 적용으로 일괄 저장 · 같은 숫자를 다시 누르면 해제 · 이름 더블클릭: 성장 기록')

    def choose_cell(self,row,column):
        if not self.editable() or not 4<=column<12:return
        identity=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
        skill=SKILLS[column-4]
        current=self.choices().get(identity)
        self.stage_choice(identity,None if current==skill else skill)

    def choose_combo(self,*_):
        if self.editable() and self.current_person():self.stage_choice(self.current_person(),self.focus.currentData())

    def stage_choice(self,identity,skill):
        self.pending[identity]=skill
        sorting=self.table.isSortingEnabled();self.table.blockSignals(True);self.table.setSortingEnabled(False)
        for row in range(self.table.rowCount()):
            person=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
            if person not in self.pending:continue
            chosen=self.pending[person]
            self.table.item(row,12).setText(NAMES.get(chosen,'없음'))
            self.table.item(row,13).setText('적용 대기')
            self.table.item(row,14).setText(f'{FOCUS_COST if chosen else 0:,}원')
            for column,key in enumerate(SKILLS,4):
                item=self.table.item(row,column);font=item.font();font.setBold(key==chosen);item.setFont(font)
                item.setToolTip('집중 훈련 선택 · 선택 적용 시 일괄 저장' if key==chosen else '클릭하여 집중 훈련 선택')
        self.table.setSortingEnabled(sorting);self.table.blockSignals(False);self.selected()

    def choices(self):
        choices={p['id']:p['focus'] for p in self.snapshot['players'] if p['career_status']=='second_team'}
        choices.update(self.pending)
        return choices

    def save(self,confirm):
        try:self.service.training.save(self.agency(),self.choices(),confirm=confirm,expected_revision=self.snapshot['revision'])
        except ValueError as error:
            QMessageBox.warning(self,'훈련 설정',str(error));return
        self.reload()

    def apply_choice(self):self.save(False)
    def confirm_choices(self):
        amount=sum(skill is not None for skill in self.choices().values())*FOCUS_COST
        if QMessageBox.question(self,'훈련 확정',f'이번 주 집중 훈련을 확정할까요?\n추가 비용 {amount:,}원을 지급하며, 확정 후에는 변경할 수 없습니다.')==QMessageBox.StandardButton.Yes:self.save(True)

    def open_details(self,*_):
        if not self.current_person():return
        try:rows=self.service.training.details(self.agency(),self.current_person())
        except ValueError as error:QMessageBox.warning(self,'성장 기록',str(error));return
        name=next(p['name'] for p in self.snapshot['players'] if p['id']==self.current_person())
        self.detail_dialog=TrainingDetails(rows,self.service.settings_dir,self,name=name)
        self.detail_dialog.show()
