"""Read-only finance dashboard; opening a screen never pays or settles."""
from PySide6.QtCore import Qt,QSize,QPointF,QTimer,QEvent
from PySide6.QtGui import QColor,QPainter,QPen,QIcon
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTabWidget,QSizePolicy,QMessageBox
from ..game_clock import GameDate
import sqlite3
from .match_page import make_table,fill_table,PROFILE_ROLE

LABELS={'focus_training':'2군 집중 훈련비','initial_funds':'신규 시작 자금','opening_balance':'도입 기초 잔액','weekly_sponsor':'주간 후원금',
 'season_bonus':'시즌 종료 보너스','debt_repayment':'채무 상환','salary_base':'기본 급여 의무','first_bonus':'1군 활동 보너스',
 'second_reduction':'2군 급여 감액','salary_payment':'급여 실제 지급','unpaid_salary':'미지급 급여','unpaid_operating':'운영비 미지급',
 'second_training':'2군 기본 훈련비','trainee_care':'연습생 관리비','payroll_not_backfilled':'도입 전 급여 소급 제외','partial_contract_review':'기간 중 계약 확인 필요','release_prepayment':'방출 위약금 전액 상환'}
ROLES={'first_team':'1군','second_team':'2군','pro_pending':'프로 편성 전','trainee':'연습생'}
def money(n):return f'{n:,}원'
def manwon(n):return f'{n/10000:,.4f}'.rstrip('0').rstrip('.') if n%10000 else f'{n//10000:,}'
class CashChart(QWidget):
    def __init__(self,parent=None):super().__init__(parent);self.values=[];self.setMinimumHeight(140)
    def set_values(self,values):self.values=values;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);area=self.rect().adjusted(18,18,-18,-25)
        p.fillRect(self.rect(),QColor('#fbf6ff'));p.setPen(QColor('#805a9d'))
        if len(self.values)<2:p.drawText(area,Qt.AlignmentFlag.AlignCenter,'현금 추이 · 거래가 쌓이면 그래프가 표시됩니다.');return
        low=min(self.values);high=max(self.values);span=max(1,high-low)
        p.drawText(18,self.height()-6,f'현금 추이: {money(self.values[0])} → {money(self.values[-1])}')
        p.setPen(QPen(QColor('#ab79cc'),3))
        points=[QPointF(area.left()+i*area.width()/(len(self.values)-1),area.bottom()-(v-low)*area.height()/span) for i,v in enumerate(self.values)]
        for first,second in zip(points,points[1:]):p.drawLine(first,second)

class FinancePage(QWidget):
    def __init__(self,service,thumbnails,parent=None):
        super().__init__(parent);self.service=service;self.thumbnails=thumbnails;self.rows=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(16,10,16,10);layout.setSpacing(7)
        title=QLabel('기획사 재정');title.setObjectName('title');title.setStyleSheet('font-size:24px;');layout.addWidget(title)
        controls=QHBoxLayout();self.agency=QComboBox();refresh=QPushButton('재정 새로고침')
        self.fit_button=QPushButton('화면에 맞추기');self.fit_button.clicked.connect(self.fit_screen)
        controls.addWidget(self.agency,1);controls.addWidget(refresh);controls.addWidget(self.fit_button);layout.addLayout(controls)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('summary');layout.addWidget(self.summary)
        self.notice=QLabel('주간 마감은 날짜 진행 시 자동 저장됩니다. 모든 표는 조회 전용입니다.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        payoff=QHBoxLayout();self.release_balance=QComboBox();self.prepay_button=QPushButton('방출 위약금 전액 상환')
        payoff.addWidget(self.release_balance,1);payoff.addWidget(self.prepay_button);layout.addLayout(payoff)
        self.prepay_button.clicked.connect(self.prepay_release);self.release_balance.currentIndexChanged.connect(self.update_prepay)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        overview=QWidget();box=QVBoxLayout(overview);self.chart=CashChart();box.addWidget(self.chart)
        self.forecast_table=make_table();box.addWidget(self.forecast_table,1);self.tabs.addTab(overview,'예산 전망')
        self.ledger_table=make_table();self.tabs.addTab(self.ledger_table,'거래 장부')
        self.contract_table=make_table();self.tabs.addTab(self.contract_table,'선수 계약')
        self.payroll_table=make_table();self.tabs.addTab(self.payroll_table,'급여 명세')
        self.debt_table=make_table();self.tabs.addTab(self.debt_table,'채무 기록')
        self.sale_table=make_table();self.tabs.addTab(self.sale_table,'강제 매각 검토')
        for table in (self.contract_table,self.payroll_table):table.setIconSize(QSize(24,28));table.verticalHeader().setDefaultSectionSize(30)
        self.agency.currentIndexChanged.connect(self.render);refresh.clicked.connect(self.reload)
        for table,widths in ((self.forecast_table,(330,170,170,170,190)),(self.ledger_table,(300,130,180,160,160,160,170,170,250,300,450)),
            (self.contract_table,(65,160,120,180,150,300,160,340)),(self.payroll_table,(65,160,110,70,100,150,150,110,110,130,130,150,150,150,160))):
            for col,width in enumerate(widths):
                if col>=table.columnCount():table.setColumnCount(len(widths))
                table.setColumnWidth(col,width)
        self._fitted_tables=set()
        self.tabs.currentChanged.connect(lambda *_:QTimer.singleShot(0,self.fit_visible_tables))
        self.photo_timer=QTimer(self);self.photo_timer.setSingleShot(True);self.photo_timer.timeout.connect(self.photos)
        self.thumbnails.changed.connect(self.queue_photos)
        for table in (self.contract_table,self.payroll_table):
            table.viewport().installEventFilter(self);table.verticalScrollBar().valueChanged.connect(self.queue_photos)
    def showEvent(self,event):
        super().showEvent(event);self.reload();QTimer.singleShot(0,self.fit_visible_tables)
    def reload(self,*_):
        selected=self.agency.currentData()
        if selected is None:selected=self.service.draft_session.player_agency()
        self.agency.blockSignals(True);self.agency.clear()
        for a in self.service.agencies():self.agency.addItem(a.name,a.id)
        self.agency.setCurrentIndex(max(0,self.agency.findData(selected)));self.agency.blockSignals(False);self.render()
    def render(self,*_):
        agency=self.agency.currentData()
        if not agency:return
        f=self.service.finance;d=f.dashboard(agency);self.data=d
        nextpay=f'시즌 {d["next_pay_season"]} · 정규 {d["next_pay_week"]}주차' if d['next_pay_week'] else '이번 시즌 정기 급여 종료'
        self.summary.setText(f'현금 {money(d["cash"])}  ·  채무 {money(d["debt"])}  ·  순자금 {money(d["net"])}\n'
            f'이번 주 실제 수입 {money(d["week_income"])} / 지출 {money(d["week_expense"])}  ·  시즌 실제 수입 {money(d["season_income"])} / 지출 {money(d["season_expense"])}\n'
            f'다음 급여 {nextpay} · 기본 예상 {money(d["next_payroll"])}  |  주간 운영비 {money(d["weekly_cost"])}  |  시즌 마감 예상 순자금 {money(d["end_projection"])}')
        self.notice.setText('정규 주 마감 자동 정산 · 예상 급여는 활동 보너스·감액 제외 · 표의 금액 단위: 만원')
        self.notice.setToolTip(d['forecast_notice']+'\n집중 훈련은 훈련 탭에서 화요일에 확정하며 추가 비용은 한 번만 지급합니다.')
        self.release_balance.blockSignals(True);self.release_balance.clear()
        for plan in self.service.market.release_balances(agency):
            if plan['remaining']>0:self.release_balance.addItem(f'{plan["name"]} · 남은 위약금 {money(plan["remaining"])}',(plan['id'],plan['remaining']))
        self.release_balance.blockSignals(False);self.update_prepay()
        self.chart.set_values([r['cash_after'] for r in d['ledger']])
        fill_table(self.forecast_table,('주 시작일','후원금 예상','운영비 예상','기본 급여 예상','예상 순자금'),
            [(r['date'],manwon(r['income']),manwon(r['operating']),manwon(r['payroll']),manwon(r['net'])) for r in d['forecast']])
        ledger=f.ledger(agency)
        fill_table(self.ledger_table,('게임 날짜','정산 주차','종류','금액/조정','현금 변동','채무 변동','거래 전 현금','거래 후 현금','선수 ID','정산 ID','설명'),
            [(str(GameDate(r['absolute_day'])),f'S{r["season"]} W{r["week"]}',LABELS.get(r['kind'],r['kind']),manwon(r['amount']),manwon(r['cash_delta']),manwon(r['debt_delta']),manwon(r['cash_before']),manwon(r['cash_after']),r['person_id'] or '—',r['settlement_id'],r['description']) for r in ledger])
        self.contracts=f.contracts(agency);self.payroll=f.payroll(agency)
        fill_table(self.contract_table,('사진','이름','소속 상태','계약 유형','계약 연봉','회계 적용 시작','만료 기록','급여 기준'),
            [('',r['name'],ROLES.get(r['career_status'],r['career_status']),{'pro':'프로','draft_trainee':'드래프트 연습생','free_trainee':'자유계약 연습생'}[r['kind']],manwon(r['annual_krw']),f'S{GameDate(r["start_day"]).season} · {GameDate(r["start_day"]).week}주',str(GameDate(r['end_day'])) if r['end_day'] is not None else '만료 미정','기획서 기본 연봉 · 도입 이후 적용') for r in self.contracts],people=[r['person_id'] for r in self.contracts],profile_columns=(1,))
        fill_table(self.payroll_table,('사진','이름','신분','시즌','회차','연봉\n(만원)','기본급\n(만원)','1군\n활동 주','2군\n소속 주','보너스\n(만원)','감액\n(만원)','지급 의무\n(만원)','지급 누계\n(만원)','미지급\n(만원)','상태'),
            [('',r['name'],ROLES.get(r['career_status'],r['career_status']),r['season'],r['cycle'],manwon(r['annual_krw']),manwon(r['base_krw']),r['first_weeks'],r['second_weeks'],manwon(r['bonus_krw']),manwon(r['reduction_krw']),manwon(r['due_krw']),manwon(r['paid_krw']),manwon(r['due_krw']-r['paid_krw']),'완료' if r['due_krw']==r['paid_krw'] else '미지급') for r in self.payroll],people=[r['person_id'] for r in self.payroll],profile_columns=(1,))
        with closing(f.database.connect()) as c:
            debts=[dict(r) for r in c.execute('SELECT * FROM finance_debts WHERE agency_id=? ORDER BY id DESC',(agency,))]
        fill_table(self.debt_table,('채무 ID','종류','선수 ID','최초 채무','남은 채무','상환 누계','급여 명세 ID'),
            [(r['id'],LABELS.get(r['kind'],r['kind']),r['person_id'] or '—',manwon(r['original_krw']),manwon(r['outstanding_krw']),manwon(r['original_krw']-r['outstanding_krw']),r['payroll_id'] or '—') for r in debts])
        names={a.id:a.name for a in self.service.agencies()};sales=f.sale_candidates(agency)
        fill_table(self.sale_table,('매각 우선순위','이름','계약 연봉','검토 가격','구매 능력·정원 충족 기획사','처리 상태'),
            [(i+1,r['name'],manwon(r['annual_krw']),manwon(r['price']),' / '.join(names[a] for a in r['buyers']) or '없음',r['reason']) for i,r in enumerate(sales)])
        self.photos(force_metadata=True)
        if self.isVisible():QTimer.singleShot(0,self.fit_visible_tables)
    def fit_screen(self):
        self.window().showMaximized();self._fitted_tables.clear()
        QTimer.singleShot(0,self.fit_visible_tables)
    def update_prepay(self,*_):
        selected=self.release_balance.currentData();own=self.agency.currentData()==self.service.draft_session.player_agency()
        enough=bool(selected and getattr(self,'data',{}).get('cash',0)>=selected[1])
        self.prepay_button.setEnabled(own and enough)
        self.prepay_button.setToolTip('플레이어 기획사만 상환할 수 있습니다.' if not own else '상환할 분할 위약금이 없습니다.' if not selected else '전액 상환할 현금이 부족합니다.' if not enough else '기존 납부 이력을 유지하고 남은 금액을 한 번 지급합니다.')
    def prepay_release(self):
        selected=self.release_balance.currentData()
        if not selected:return
        if QMessageBox.question(self,'위약금 전액 상환',f'남은 위약금 {money(selected[1])}을 현금으로 전액 상환하시겠습니까?\n기존 납부 기록은 유지되며 이후 분할 청구는 중단됩니다.')!=QMessageBox.StandardButton.Yes:return
        try:self.service.market.prepay_release(self.agency.currentData(),selected[0],expected_remaining=selected[1])
        except (ValueError,RuntimeError,sqlite3.Error) as error:QMessageBox.warning(self,'상환 안내',str(error))
        self.render()
    def fit_visible_tables(self):
        for table in (self.forecast_table,self.ledger_table,self.contract_table,self.payroll_table,self.debt_table,self.sale_table):
            if not table.isVisible() or table in self._fitted_tables or table.viewport().width()<100:continue
            if table in (self.contract_table,self.payroll_table):table.verticalHeader().setDefaultSectionSize(30)
            table.setWordWrap(False)
            table.setStyleSheet('QTableView::item {padding:3px;} QHeaderView::section {padding:6px;}')
            header=table.horizontalHeader();header.setStretchLastSection(False);metrics=table.fontMetrics()
            widths=[]
            for col in range(table.columnCount()):
                item=table.horizontalHeaderItem(col);label=item.text() if item else ''
                width=max((metrics.horizontalAdvance(line) for line in label.split('\n')),default=30)+16
                for row in range(min(table.rowCount(),50)):
                    cell=table.item(row,col)
                    if cell:width=max(width,min(300,metrics.horizontalAdvance(cell.text())+14))
                widths.append(max(140 if col==1 and table in (self.contract_table,self.payroll_table) else 40,width))
            available=table.viewport().width()-2
            total=sum(widths)
            if total>available:
                minimum=40*len(widths)
                extra=max(0,available-minimum)
                flexible=max(1,total-minimum)
                widths=[40+int((w-40)*extra/flexible) for w in widths]
            else:
                extra=(available-total)//max(1,len(widths))
                widths=[w+extra for w in widths]
            for col,width in enumerate(widths):header.resizeSection(col,width)
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    item=table.item(row,col)
                    if item:item.setToolTip(item.text())
            header.setToolTip('표의 금액 단위는 만원입니다. 열 경계는 직접 조절할 수 있습니다.')
            self._fitted_tables.add(table)
    def queue_photos(self,*_):
        if self.isVisible() and not self.photo_timer.isActive():self.photo_timer.start(25)
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Paint,QEvent.Type.Resize,QEvent.Type.Show):self.queue_photos()
        return super().eventFilter(obj,event)
    def photos(self,*,force_metadata=False):
        for table,rows in ((self.contract_table,getattr(self,'contracts',())),(self.payroll_table,getattr(self,'payroll',()))):
            if not force_metadata and not table.isVisible():continue
            table.setSortingEnabled(False)
            paths={r['person_id']:r['photo_path'] for r in rows}
            for i in range(table.rowCount()):
                person=table.item(i,1).data(PROFILE_ROLE)
                table.item(i,0).setData(Qt.ItemDataRole.UserRole,person)
                cell=table.item(i,0)
                if table.isVisible() and not table.isColumnHidden(0) and not table.isRowHidden(i) and table.visualItemRect(cell).intersects(table.viewport().rect()) and person in paths:
                    image=self.thumbnails.get(paths[person])
                    if cell.data(Qt.ItemDataRole.UserRole+3)!=image.cacheKey():
                        cell.setData(Qt.ItemDataRole.UserRole+3,image.cacheKey());cell.setIcon(QIcon(image))
            table.setSortingEnabled(True)

from contextlib import closing
