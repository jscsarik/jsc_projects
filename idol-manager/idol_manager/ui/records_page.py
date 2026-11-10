"""Historical queries only. Shared paginated tables and common player profiles."""
import sqlite3
from collections import defaultdict
from PySide6.QtCore import Qt,Signal,QSize,QTimer,QEvent,QThreadPool
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,QSpinBox,QPushButton,
    QTabWidget,QDialog,QDialogButtonBox,QMessageBox)
from .match_page import make_table,fill_table,PROFILE_ROLE
from .profile_dialog import bounds_text,date_text
from .roster_model import STATUS_LABELS
from ..config import SKILLS
from ..awards import LABELS,AWARDS

KINDS={'regular':'정규 시즌','special':'특별전','postseason':'포스트시즌','tiebreak':'정규 순위 결정전'}
METRICS={'champions':'챔피언','regular_first':'정규 1위','wins':'정규 승리','qualifications':'PS 진출','awards':'개인상','appearances':'정규 출전','winning_idol':'승리 아이돌','successes':'주요+일반 성공 합계','mvp':'MVP'}
def pct(v):return round(v*100,3) if v is not None else None
def show(v):return '기록 없음' if v is None else v


class RecordsPage(QWidget):
    profile_requested=Signal(str);awards_requested=Signal(int);finals_requested=Signal(int)
    def __init__(self,service,photos):
        super().__init__();self.service=service;self.api=service.records;self.photos=photos;self._loading=False;self.dialogs=[]
        from .records_queries import QueryCache,QuerySignals
        self.api=QueryCache(self.api);self.query_pool=QThreadPool(self);self.query_pool.setMaxThreadCount(1)
        self.query_jobs={}
        self.query_signals=QuerySignals(self);self.query_signals.finished.connect(self.query_finished)
        self.query_signals.preview.connect(self.query_preview)
        self.query_generation=0;self.rendered_generation=-1;self.query_timer=QTimer(self);self.query_timer.setSingleShot(True);self.query_timer.timeout.connect(self.start_query)
        self.setStyleSheet('QWidget {font-family:"Malgun Gothic";} QLabel#title {color:#497d9f;} QHeaderView::section {background:#edf6ff;color:#416b89;} QTableView {background:white;alternate-background-color:#f5faff;selection-background-color:#dceeff;}')
        photos.changed.connect(self.refresh_photos)
        self.names={a.id:a.name for a in service.agencies()}
        box=QVBoxLayout(self);title=QLabel('기록실 · STAR ARCHIVE');title.setObjectName('title');box.addWidget(title)
        self.notice=QLabel('저장된 완료 경기만 조회합니다. 정규·특별전·PS·결정전은 별도 집계합니다.');self.notice.setWordWrap(True);box.addWidget(self.notice)
        bar=QHBoxLayout();self.season=QComboBox();self.kind=QComboBox()
        for k,v in KINDS.items():self.kind.addItem(v,k)
        self.kind.addItem('전체 (구간별 표시)',None);self.agency=QComboBox();self.agency.addItem('모든 기획사',None)
        for k,v in self.names.items():self.agency.addItem(v,k)
        for w in (self.season,self.kind,self.agency):bar.addWidget(w)
        box.addLayout(bar);bar=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('아이돌 이름 검색')
        self.minimum=QSpinBox();self.minimum.setRange(0,10000000);self.minimum.setPrefix('기본 시도 최소 ')
        self.role=QComboBox();self.role.addItem('모든 신분',None)
        for k in ('first_team','second_team','trainee','fa','retired','unassigned'):self.role.addItem(STATUS_LABELS.get(k,k),k)
        bar.addWidget(self.search,1);bar.addWidget(self.minimum);bar.addWidget(self.role);box.addLayout(bar)
        bar=QHBoxLayout()
        for text,callback in [('새로고침',self.reload),('시즌 시상식',lambda:self.awards_requested.emit(self.selected_season())),('포스트시즌 결과',lambda:self.finals_requested.emit(self.selected_season()))]:
            b=QPushButton(text);b.clicked.connect(callback);bar.addWidget(b)
        box.addLayout(bar);self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        self.league_tabs=QTabWidget();self.tabs.addTab(self.league_tabs,'역대 리그')
        self.league_table=make_table();self.champion_table=make_table();self.leader_table=make_table()
        for name,t in [('정규 최종 순위',self.league_table),('역대 챔피언',self.champion_table),('최고 기록 · 동률 전원',self.leader_table)]:self.league_tabs.addTab(t,name)
        players=QWidget();v=QVBoxLayout(players);self.player_table=make_table();self.player_table.setIconSize(QSize(32,40));v.addWidget(self.player_table,1)
        b=QPushButton('선택 선수 · 시즌 경력 / 성장 / 수상 / 이적');self.player_detail_button=b;b.clicked.connect(self.player_detail);v.addWidget(b);self.tabs.addTab(players,'선수 기록')
        self.agency_table=make_table();self.tabs.addTab(self.agency_table,'기획사 기록')
        content=QWidget();v=QVBoxLayout(content);row=QHBoxLayout();self.content=QComboBox();self.content.addItem('모든 콘텐츠',None)
        self.catalog={r['id']:r for r in self.api.content_catalog()}
        for k,c in self.catalog.items():self.content.addItem(c['name'],k)
        row.addWidget(self.content);v.addLayout(row);self.content_info=QLabel();self.content_info.setWordWrap(True);v.addWidget(self.content_info)
        self.content_tabs=QTabWidget();self.content_table=make_table();self.content_player_table=make_table()
        self.content_tabs.addTab(self.content_table,'콘텐츠 개최·기획사 성적');self.content_tabs.addTab(self.content_player_table,'선수별 콘텐츠');v.addWidget(self.content_tabs,1);self.tabs.addTab(content,'콘텐츠별 성적')
        comparison=QWidget();v=QVBoxLayout(comparison);row=QHBoxLayout();self.compare_kind=QComboBox();self.compare_kind.addItems(['아이돌 2명','기획사 2곳']);self.left=QComboBox();self.right=QComboBox()
        for w in (self.compare_kind,self.left,self.right):row.addWidget(w)
        v.addLayout(row);self.comparison_note=QLabel();self.comparison_note.setWordWrap(True);v.addWidget(self.comparison_note)
        self.compare_photos=QLabel();self.compare_photos.setAlignment(Qt.AlignmentFlag.AlignCenter);v.addWidget(self.compare_photos)
        pictures=QHBoxLayout();self.left_photo=QLabel();self.right_photo=QLabel()
        for photo in (self.left_photo,self.right_photo):photo.setAlignment(Qt.AlignmentFlag.AlignCenter);photo.setFixedHeight(100);pictures.addWidget(photo)
        v.addLayout(pictures)
        self.comparison_table=make_table();v.addWidget(self.comparison_table,1);self.tabs.addTab(comparison,'기록 비교')
        self.league_table.cellDoubleClicked.connect(lambda *_:self.agency_detail(self._id(self.league_table),self._season_id(self.league_table)))
        self.champion_table.cellDoubleClicked.connect(self.champion_detail)
        self.agency_table.cellDoubleClicked.connect(lambda *_:self.agency_detail(self._id(self.agency_table),self.selected_season()))
        self.player_table.cellDoubleClicked.connect(lambda *_:self.profile_requested.emit(self._id(self.player_table)) if self._id(self.player_table) else None)
        self.compare_kind.currentIndexChanged.connect(self.comparison_choices)
        self.photo_timer=QTimer(self);self.photo_timer.setSingleShot(True);self.photo_timer.timeout.connect(self.refresh_photos)
        for t in (self.league_table,self.player_table,self.agency_table):t.viewport().installEventFilter(self)
        for w in (self.left,self.right):w.currentIndexChanged.connect(self.render)
        self.league_tabs.currentChanged.connect(self.render)
        for w in (self.season,self.kind,self.agency,self.role,self.content):w.currentIndexChanged.connect(self.render)
        self.search.textChanged.connect(self.render);self.minimum.valueChanged.connect(self.render);self.tabs.currentChanged.connect(self.render)

    def selected_season(self):
        if self.season.currentData():return self.season.currentData()
        if self.tabs.currentIndex()==0:
            t=self.champion_table if self.league_tabs.currentIndex()==1 else self.league_table
            selected=self._season_id(t)
            if selected:return selected
        return max(self.api.seasons())

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.Paint,QEvent.Type.Resize,QEvent.Type.Show) and hasattr(self,'photo_timer'):
            self.photo_timer.start(0)
        return super().eventFilter(watched,event)
    def showEvent(self,event):super().showEvent(event);self.reload()
    def reload(self,*_):
        self._loading=True
        selected=self.season.currentData();self.season.clear();self.season.addItem('통산 · 전체 시즌',None)
        for n in self.api.seasons():self.season.addItem(f'시즌 {n}',n)
        self.season.setCurrentIndex(max(0,self.season.findData(selected)));self._loading=False
        self.comparison_choices();self.render()

    @staticmethod
    def _id(t):
        item=t.item(t.currentRow(),0);value=item.data(Qt.ItemDataRole.UserRole) if item else None
        return value[0] if isinstance(value,list) else value
    @staticmethod
    def _season_id(t):
        item=t.item(t.currentRow(),0);value=item.data(Qt.ItemDataRole.UserRole) if item else None
        return value[1] if isinstance(value,list) else None

    def fill(self,table,headers,rows,ids=None,photos=None):
        sorting=table.isSortingEnabled();table.setSortingEnabled(False)
        fill_table(table,headers,[(show(x) for x in row) for row in rows])
        for i,key in enumerate(ids or []):
            table.item(i,0).setData(Qt.ItemDataRole.UserRole,key)
            if table in (self.player_table,self.content_player_table):table.item(i,0).setData(PROFILE_ROLE,key)
            if photos:table.item(i,0).setData(Qt.ItemDataRole.UserRole+2,photos[i] or '')
        table.setSortingEnabled(sorting)
        if photos:QTimer.singleShot(0,self.refresh_photos)

    def refresh_photos(self):
        for table in (self.league_table,self.player_table,self.agency_table):
            if not table.isVisible():continue
            for i in range(table.rowCount()):
                if table.isRowHidden(i):continue
                item=table.item(i,0)
                if item is not None and item.data(Qt.ItemDataRole.UserRole+2) is not None and table.visualItemRect(item).intersects(table.viewport().rect()):
                    pixmap=self.photos.get(item.data(Qt.ItemDataRole.UserRole+2))
                    if item.data(Qt.ItemDataRole.UserRole+3)!=pixmap.cacheKey():
                        item.setData(Qt.ItemDataRole.UserRole+3,pixmap.cacheKey());item.setIcon(QIcon(pixmap))
        for photo,path in getattr(self,'_comparison_pictures',[]):
            if photo.isVisible():photo.setPixmap(self.photos.get(path).scaled(110,100,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def render(self,*_):
        if self._loading:return
        try:revision=self.api.revision()
        except OSError as e:self.notice.setText('기록 조회 오류: '+str(e));return
        if getattr(self,'_display_revision',None)!=revision:
            self._display_revision=revision
            for table in (self.league_table,self.champion_table,self.leader_table,self.player_table,self.agency_table,self.content_table,self.content_player_table,self.comparison_table):table.setRowCount(0)
        self.query_generation+=1;self.cancel_queries();self.query_timer.start(0)
    def cancel_queries(self):
        for job in self.query_jobs.values():job.cancelled.set()
        self.query_jobs.clear();self.query_pool.clear()
    def start_query(self):
        if not self.isVisible():return
        from .records_queries import QueryJob
        s=self.season.currentData();kind=self.kind.currentData();agency=self.agency.currentData();tab=self.tabs.currentIndex();requests=[]
        if tab==0:
            requests=[('league',(n,),{}) for n in ([s] if s else self.api.seasons())]+[('champions',(s,),{})]
            if self.league_tabs.currentIndex()==2:requests.append(('leaders',(s,),{}))
        elif tab==1:requests=[('players',(),dict(season=s,kind=kind,agency=agency))]
        elif tab==2:requests=[('agencies',(s,),{})]
        elif tab==3:requests=[('contents',(),dict(season=s,kind=kind,agency=agency)),('players',(),{}),('content_players',(),dict(season=s,kind=kind,agency=agency))]
        elif self.left.currentData() and self.right.currentData():requests=[('compare_players' if self.compare_kind.currentIndex()==0 else 'compare_agencies',(self.left.currentData(),self.right.currentData()),dict(season=s,**({'kind':kind} if self.compare_kind.currentIndex()==0 else {})))]
        self.notice.setText('기록을 불러오는 중… 다른 화면을 이용할 수 있습니다.')
        job=QueryJob(self.api,self.query_generation,requests,self.query_signals)
        self.query_jobs[self.query_generation]=job;self.query_pool.start(job)
    def query_finished(self,generation,revision,error):
        self.query_jobs.pop(generation,None)
        if generation!=self.query_generation or not self.isVisible():return
        if error:self.notice.setText('기록 조회 오류: '+error);return
        try:current=self.api.revision()
        except OSError as e:self.notice.setText('기록 조회 오류: '+str(e));return
        if revision!=current:self.render();return
        try:self._render();self.rendered_generation=generation
        except (ValueError,sqlite3.Error,OSError) as e:self.notice.setText('기록 조회 오류: '+str(e))
    def hideEvent(self,event):
        self.query_generation+=1;self.query_timer.stop();self.cancel_queries();super().hideEvent(event)
    def query_preview(self,generation,revision,rows):
        try:current=self.api.revision()
        except OSError as e:self.notice.setText('기록 조회 오류: '+str(e));return
        if generation!=self.query_generation or revision!=current or not self.isVisible() or self.tabs.currentIndex()!=1:return
        rows=[r for r in rows if self.search.text().casefold() in r['name'].casefold() and r['attempts']>=self.minimum.value() and (not self.role.currentData() or r['career_status']==self.role.currentData())]
        self._fill_players(rows)
        self.notice.setText('첫 20명의 실제 기록을 먼저 표시합니다. 전체 선수 집계 중… 완료되면 전체 명단·정렬을 갱신합니다.')
    def shutdown(self):
        self.query_generation+=1;self.query_timer.stop();self.cancel_queries();self.query_pool.waitForDone()

    def _render(self):
        s=self.season.currentData();kind=self.kind.currentData();agency=self.agency.currentData();tab=self.tabs.currentIndex()
        self.notice.setText('읽기 전용 · 없는 과거 CA·시즌 말 재정은 기록 없음 · 성공률 열은 % · 같은 기록은 한 번만 합산\n기획사 필터는 당시 경기 소속 기준입니다. 선수 신분·사진·나이는 현재 값입니다. 리그·기획사 정규 성적은 경기 구간 필터와 독립입니다.')
        if tab==0:
            leagues=[r for n in ([s] if s else self.api.seasons()) for r in self.api.league(n) if not agency or r['agency_id']==agency]
            self.fill(self.league_table,('기획사','시즌','최종 정규 순위','정규 경기','승','패','정규 승점','특별전 변동','재정 페널티','공식 승점','PS 진출'),
                [(r['name'],r['season'],r['rank'],r['played'],r['wins'],r['losses'],r['regular_points'],r['special_points'],r['penalty'],r['points'],'확정' if r['qualified'] else '미진출' if r['qualified'] is False else '미확정') for r in leagues],[[r['agency_id'],r['season']] for r in leagues],[r['logo_path'] for r in leagues])
            champs=[r for r in self.api.champions(s) if not agency or r['agency_id']==agency]
            self.champs={r['season']:r for r in champs}
            self.fill(self.champion_table,('챔피언','시즌','당시 정규 순위','당시 누적 우승','1라운드','2라운드','결승'),
                [(r['name'],r['season'],r['rank'],r['cumulative'],*[next((f'{self.names.get(v["agency_a"])} {show(v["wins_a"])} : {show(v["wins_b"])} {self.names.get(v["agency_b"])}' for v in r['series'] if v['round_number']==n),'기록 없음') for n in (1,2,3)]) for r in champs],[[r['agency_id'],r['season']] for r in champs])
            if self.league_tabs.currentIndex()==2:
                leaders=self.api.leaders(s);self.fill(self.leader_table,('기록자','기록','수치'),[(r['name'],METRICS[r['metric']],r['value']) for r in leaders])
        elif tab==1:
            rows=self.api.players(season=s,kind=kind,agency=agency,name=self.search.text(),minimum=self.minimum.value(),role=self.role.currentData())
            self._fill_players(rows)
        elif tab==2:
            rows=[r for r in self.api.agencies(s) if not agency or r['id']==agency]
            self.fill(self.agency_table,('기획사','현재 자금','현재 채무','정규 경기','승','패','승률 %','최고 정규 순위','정규 1위','PS 진출','챔피언','개인상','정규 승점','공식 승점','특별전 변동','페널티'),[(r['name'],r['funds_krw'],r['debt'],r['played'],r['wins'],r['losses'],pct(r['rate']),r['best_rank'],r['regular_first'],r['qualifications'],r['champions'],r['awards'],r['regular_points'],r['points'],r['special_points'],r['penalty']) for r in rows],[r['id'] for r in rows],[r['logo_path'] for r in rows])
        elif tab==3:
            content=self.content.currentData();catalog=self.catalog.get(content)
            self.content_info.setText((catalog['name']+' · 주요 '+ ' / '.join(LABELS[k] for k in catalog['main'])+f' · 출전 {catalog["minimum"]}~{catalog["maximum"]}명') if catalog else '완료된 경기만 집계 · 특별전 개최는 단계별 대결 수 · 미래 일정 콘텐츠 배정은 표시하지 않습니다.')
            rows=[r for r in self.api.contents(season=s,kind=kind,agency=agency) if not content or r['content_id']==content]
            self.fill(self.content_table,('콘텐츠','구간','조회 개최','통산 개최','승','패','승률 %','선수 출전','기본 시도','주요 능력치 성공','일반 능력치 성공','기본 실패','기본 성공률 %'),[(r['content_name'],KINDS[r['kind']],r['played'],r['lifetime_played'],r['wins'],r['losses'],pct(r['win_rate']),r['appearances'],r['attempts'],r['main_successes'],r['support_successes'],r['attempts']-r['successes'],pct(r['rate'])) for r in rows])
            people={r['id']:r['name'] for r in self.api.players(name=self.search.text())}
            pr=[r for r in self.api.content_players(season=s,kind=kind,agency=agency) if r['person_id'] in people and (not content or r['content_id']==content)]
            self.fill(self.content_player_table,('아이돌','콘텐츠','구간','실제 출전','기본 시도','주요 능력치 성공','일반 능력치 성공','기본 실패','기본 성공률 %'),[(people[r['person_id']],r['content_name'],KINDS[r['kind']],r['appearances'],r['attempts'],r['main_successes'],r['support_successes'],r['attempts']-r['successes'],pct(r['rate'])) for r in pr],[r['person_id'] for r in pr])
        else:self.render_compare()

    def _fill_players(self,rows):
        headers=('이름','나이','현재 기획사','현재 신분','데뷔 시즌','조회 출전','정규 출전','특별전 출전','PS 출전','결정전 출전','팀 승','팀 패','승리 아이돌','패배 아이돌','기본 시도','주요 능력치 성공','일반 능력치 성공','기본 성공률 %','리더 성공','리더 시도','DM 성공','DM 시도','개인상','누락 판정 경기',*[LABELS[k]+suffix for k in SKILLS for suffix in (' 시도',' 성공',' 실패',' 성공률 %')])
        self.fill(self.player_table,headers,[(r['name'],r['age'],r['agency_name'] or '미소속',STATUS_LABELS.get(r['career_status'],r['career_status']),r['debut'],r['appearances'],r['regular_appearances'],r['special_appearances'],r['postseason_appearances'],r['tiebreak_appearances'],r['wins'] or 0,r['losses'] or 0,r['winning_idol'],r['losing_idol'],r['attempts'],r['main_successes'],r['support_successes'],pct(r['rate']),r['leader_successes'],r['leader_attempts'],r['deathmatch_successes'],r['deathmatch_attempts'],r['awards'],r['partial'],*[v for k in SKILLS for v in (r['skills'][k]['attempts'],r['skills'][k]['successes'],r['skills'][k]['failures'],pct(r['skills'][k]['rate']))]) for r in rows],[r['id'] for r in rows],[r['photo_path'] for r in rows])

    def comparison_choices(self,*_):
        if self._loading:return
        self._loading=True
        choices=self.api.player_choices() if self.compare_kind.currentIndex()==0 else self.service.agencies()
        for box in (self.left,self.right):
            previous=box.currentData();box.clear()
            for r in choices:box.addItem(r['name'] if isinstance(r,dict) else r.name,r['id'] if isinstance(r,dict) else r.id)
            box.setCurrentIndex(max(0,box.findData(previous)))
        if self.left.currentData()==self.right.currentData() and self.right.count()>1:self.right.setCurrentIndex(1)
        self._loading=False;self.render()

    def render_compare(self,*_):
        if self._loading or not self.left.currentData() or not self.right.currentData():return
        s=self.season.currentData();args=(self.left.currentData(),self.right.currentData());rows=[]
        try:
            if self.compare_kind.currentIndex()==0:
                a,b=self.api.compare_players(*args,season=s,kind=self.kind.currentData())
                self.comparison_note.setText('현재 능력치・건강・연봉과 과거 경기 기록을 구분합니다. 미지명 후보는 저장된 추정 범위만 공개합니다.')
                for label,key in [('나이 (현재)','age'),('현재 기획사','agency_name'),('건강 (현재)','health'),('연봉 (현재)','salary'),('조회 구간 출전','appearances'),('승리 아이돌','winning_idol'),('패배 아이돌','losing_idol'),('기본 시도','attempts'),('주요 능력치 성공','main_successes'),('일반 능력치 성공','support_successes'),('개인상','awards')]:rows.append((label,a[key],b[key]))
                rows.append(('CA (현재 / 추정)',bounds_text(a['average_bounds']),bounds_text(b['average_bounds'])))
                rows.append(('기본 성공률 %',pct(a['rate']),pct(b['rate'])))
                for i,k in enumerate(SKILLS):
                    rows.extend([(LABELS[k]+' 현재 / 추정',bounds_text(a['bounds'][i]),bounds_text(b['bounds'][i])),(LABELS[k]+' 기본 시도',a['skills'][k]['attempts'],b['skills'][k]['attempts']),(LABELS[k]+' 기본 성공률 %',pct(a['skills'][k]['rate']),pct(b['skills'][k]['rate']))])
                self.compare_photos.setText(a['name']+'    VS    '+b['name'])
                for box,p in ((self.left,a),(self.right,b)):box.setItemIcon(box.currentIndex(),QIcon(self.photos.get(p['photo_path'] or '')))
            else:
                a,b=self.api.compare_agencies(*args,season=s)
                self.comparison_note.setText('현재 자금·채무·평균은 현재 값. 선수단 평균은 프로 1군·2군·임시 프로만 포함하며 연습생 제외. 건강은 CA에 포함하지 않습니다.')
                for label,key in [('정규 승리','wins'),('정규 경기','played'),('PS 진출','qualifications'),('정규 1위','regular_first'),('챔피언','champions'),('개인상','awards'),('현재 자금','funds_krw'),('현재 채무','debt'),('현재 프로 인원','current_pro_count'),('현재 프로 평균 CA','current_pro_ca'),('현재 프로 평균 건강','current_pro_health')]:rows.append((label,a[key],b[key]))
                rows.append(('정규 승률 %',pct(a['rate']),pct(b['rate'])))
                ah={r['season']:r for r in a['history']};bh={r['season']:r for r in b['history']}
                for n in sorted(set(ah)|set(bh)):
                    rows.extend([(f'시즌 {n} 정규 순위',ah.get(n,{}).get('rank'),bh.get(n,{}).get('rank')),(f'시즌 {n} 승률 %',pct(ah.get(n,{}).get('win_rate')),pct(bh.get(n,{}).get('win_rate')))])
                self.compare_photos.setText(a['name']+'    VS    '+b['name'])
            self._comparison_pictures=[(photo,p.get('photo_path',p.get('logo_path')) or '') for photo,p in ((self.left_photo,a),(self.right_photo,b))]
            for photo,p in ((self.left_photo,a),(self.right_photo,b)):
                pixmap=self.photos.get(p.get('photo_path',p.get('logo_path')) or '')
                photo.setPixmap(pixmap.scaled(110,100,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.fill(self.comparison_table,('항목',a['name'],b['name']),rows)
        except (ValueError,sqlite3.Error) as e:self.comparison_note.setText(str(e))

    def detail(self,title,sections):
        d=QDialog(self);d.setWindowTitle(title);d.resize(820,1100);layout=QVBoxLayout(d);tabs=QTabWidget();layout.addWidget(tabs,1)
        for label,headers,rows,ids in sections:
            table=make_table();self.fill(table,headers,rows,ids);tabs.addTab(table,label)
            if ids:table.cellDoubleClicked.connect(lambda *_,t=table:self.profile_requested.emit(self._id(t)) if self._id(t) else None)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(d.close);layout.addWidget(close)
        self.dialogs.append(d);d.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);d.finished.connect(lambda *_:self.dialogs.remove(d) if d in self.dialogs else None)
        controller=getattr(self.window(),'portrait_layout',None)
        if controller:controller.prepare_dialog(d)
        d.show();return d

    def player_detail(self):
        person=self._id(self.player_table)
        if not person:return
        h=self.api.player_history(person)
        totals=defaultdict(lambda:[0,0,0])
        for r in h['seasons']:
            v=totals[(r['season'],r['kind'])];v[0]+=r['appearances'];v[1]+=r['attempts'];v[2]+=r['successes']
        sections=[('시즌별 소속',('시즌','당시 기획사','구간','출전','팀 승','팀 패','승리 아이돌','패배 아이돌','기본 시도','성공률 %','리더 성공'),[(r['season'],self.names.get(r['agency_id']),KINDS[r['kind']],r['appearances'],r['wins'],r['losses'],r['winning_idol'],r['losing_idol'],r['attempts'],pct(r['rate']),r['leader_successes']) for r in h['seasons']],None),
            ('시즌 합계',('시즌','구간','출전','기본 시도','성공률 %'),[(s,KINDS[k],v[0],v[1],pct(v[2]/v[1] if v[1] else None)) for (s,k),v in sorted(totals.items())],None),
            ('일별 소속 근거',('시즌','당시 기획사','신분','기록 일수'),[(r['season'],self.names.get(r['agency_id'],'미소속'),STATUS_LABELS.get(r['role'],r['role']),r['days']) for r in h['roles']],None),
            ('수상',('시즌','개인상','수상 당시 기획사'),[(r['season'],AWARDS[r['award_type']],self.names.get(r['awarded_agency_id'],'기록 없음')) for r in h['awards']],None),
            ('이적·계약',('게임 날짜','이전 기획사','새 기획사','사유'),[(date_text(r['absolute_day']),self.names.get(r['from_agency'],'미소속'),self.names.get(r['to_agency'],'미소속'),r['kind']) for r in h['moves']],None)]
        growth=[]
        for r in h['growth']:
            for event in r['changes']:
                for change in event['changes']:growth.append((r['season'],date_text(event['day']),change['kind'],LABELS.get(change['skill'],change['skill']),change['applied'],'기록 없음','기록 없음'))
        sections.append(('실제 성장',('시즌','정산 날짜','사유','능력치','적용 변화','시즌 시작 CA','시즌 종료 CA'),growth,None))
        self.detail('선수 시즌 경력 · 과거 CA 스냅샷은 저장되어 있지 않습니다',sections)

    def agency_detail(self,agency,season):
        if not agency:return
        season=season or self.selected_season();h=self.api.agency_history(agency,season)
        history=next(r['history'] for r in self.api.agencies() if r['id']==agency)
        finances=h['finances'];sections=[('시즌 추이',('시즌','최종 순위 (1위 최고)','정규 경기','승률 %','정규 승점','공식 승점','챔피언'),[(r['season'],r['rank'],r['played'],pct(r['win_rate']),r['regular_points'],r['points'],'우승' if r['champion'] else '—') for r in history],None),
            ('재정 기록',('항목','저장된 값'),[(name,finances[key]) for name,key in [('시즌 시작 현금','start'),('기록된 현금 수입','income'),('기록된 현금 지출','expense'),('장부 최종 기록 현금 (시즌 말과 구분)','last_recorded_cash'),('시즌 종료 현금 스냅샷','end'),('시즌 종료 채무 스냅샷','end_debt')]],None),
            ('당시 계약 근거',('이름','계약 유형','시작','종료','당시 연봉'),[(r['name'],r['kind'],date_text(r['start_day']),date_text(r['end_day']),r['annual_krw']) for r in h['contracts']],[r['id'] for r in h['contracts']]),
            ('당시 일별 소속',('이름','신분'),[(r['name'],STATUS_LABELS.get(r['role'],r['role'])) for r in h['roles']],[r['id'] for r in h['roles']]),
            ('포스트시즌 결과',('라운드','기획사 A','기획사 B','시리즈 승자'),[(r['round_number'],self.names.get(r['agency_a']),self.names.get(r['agency_b']),self.names.get(r['winner_id'],'미확정')) for r in h['postseason']],None),
            ('특별전 결과',('주차','단계','콘텐츠','순위'),[(r['week'],r['stage'],r['content_name'],r['rank']) for r in h['special']],None),
            ('계약·트레이드',('선수 ID','날짜','구분','이전','새 기획사'),[(r['person_id'],date_text(r['absolute_day']),r['kind'],self.names.get(r['from_agency'],'미소속'),self.names.get(r['to_agency'],'미소속')) for r in h['moves']],[r['person_id'] for r in h['moves']]),
            ('시즌 개인상',('선수 ID','수상'),[(r['person_id'],AWARDS[r['award_type']]) for r in h['awards']],[r['person_id'] for r in h['awards']])]
        self.detail(f'{self.names[agency]} · 시즌 {season} · 저장 근거가 있는 기록만 표시',sections)

    def champion_detail(self,*_):
        season=self._season_id(self.champion_table);record=self.champs.get(season)
        if not record:return
        self.detail(f'시즌 {season} 포스트시즌 대진', [('시리즈',('라운드','기획사 A','승','기획사 B','승','시리즈 승자'),[(r['round_number'],self.names.get(r['agency_a']),r['wins_a'],self.names.get(r['agency_b']),r['wins_b'],self.names.get(r['winner_id'],'미확정')) for r in record['series']],None)])

    def postseason_detail(self,season):
        data=self.api.postseason(season)
        self.detail(f'시즌 {season} 저장된 포스트시즌 결과',[
            ('대진',('라운드','기획사 A','기획사 B','시리즈 승자'),[(r['round_number'],self.names.get(r['agency_a']),self.names.get(r['agency_b']),self.names.get(r['winner_id'],'미확정')) for r in data['series']],None),
            ('완료 경기',('라운드','차전','날짜','콘텐츠','승자','저장된 팀 점수'),[(r['round_number'],r['game_number'],date_text(r['absolute_day']),r['content'],self.names.get(r['winner'],'기록 없음'),' / '.join(self.names.get(t['agency_id'],t['agency_id'])+': '+str(t.get('total_score',t.get('base_score','기록 없음'))) for t in r['teams'])) for r in data['games']],None)])
