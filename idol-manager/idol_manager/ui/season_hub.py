"""Read-only seasonal hubs. Opening a page never settles or creates game data."""
from contextlib import closing
import json
import sqlite3
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget
from .match_page import make_table,fill_table
from ..game_clock import current_game_date
from ..league import standings

def hub_table():
    table=make_table();table.setProperty("fitAllColumns",True);return table


def availability(day,wrapup=False):
    allowed=bool(day and (day.is_offseason if wrapup else day.is_maintenance))
    return allowed,('포스트시즌 종료 후 비시즌에 이용할 수 있습니다.' if wrapup else '정규 전반기 종료 후 중간 정비 기간에 이용할 수 있습니다.') if not allowed else ''


def read_summary(database,wrapup=False):
    # SQLite itself enforces read-only access, including accidental writes.
    with closing(sqlite3.connect(database.path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        day=current_game_date(c)
        if not day:return None
        season=day.season
        names=dict(c.execute('SELECT id,name FROM agencies'))
        row=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
        agency=row[0] if row else None
        ranks=list(standings(c,season))
        final=c.execute('SELECT * FROM season_finals WHERE season=?',(season,)).fetchone()
        if wrapup and final:
            frozen=json.loads(final['standings_json'])
            if frozen:ranks=frozen
            order=json.loads(final['final_order_json'] or '[]')
            if order:ranks.sort(key=lambda r:order.index(r['agency_id']) if r['agency_id'] in order else len(order))
        counts=dict(c.execute('SELECT career_status,COUNT(*) FROM roster_memberships WHERE agency_id=? GROUP BY career_status',(agency,)))
        leaders=c.execute('SELECT COUNT(*) FROM squad_leaders WHERE agency_id=?',(agency,)).fetchone()[0]
        # Stats are unique per match/player; no event joins that multiply rows.
        players=[tuple(r) for r in c.execute('''SELECT p.name,COUNT(*),SUM(s.winning_idol),SUM(s.losing_idol),
            SUM(s.base_successes),ROUND(100.0*SUM(s.base_successes)/SUM(s.base_attempts),1)
            FROM match_player_stats s JOIN scheduled_matches m ON m.id=s.match_id JOIN people p ON p.id=s.person_id
            WHERE m.season=? AND m.status='completed' AND s.agency_id=? AND (? OR m.week<=12)
            GROUP BY s.person_id ORDER BY SUM(s.winning_idol) DESC,SUM(s.base_successes) DESC,p.name''',(season,agency,int(wrapup)))]
        contracts=[tuple(r) for r in c.execute('''SELECT p.name,t.end_season,f.annual_krw/10000,
            CASE WHEN t.end_season<=? THEN '만료 예정' ELSE '계약 유지' END
            FROM finance_contracts f JOIN market_terms t ON t.contract_id=f.id JOIN people p ON p.id=f.person_id
            WHERE f.agency_id=? AND (f.end_day IS NULL OR f.end_day>?)
            ORDER BY t.end_season IS NULL,t.end_season,p.name'''.replace('만료 예정','만료 예정').replace('계약 유지','계약 유지'),(season,agency,day.absolute_day))]
        negotiations=[tuple(r) for r in c.execute("SELECT p.name,n.status,COUNT(o.id) FROM market_negotiations n JOIN people p ON p.id=n.person_id LEFT JOIN market_offers o ON o.negotiation_id=n.id WHERE n.agency_id=? AND n.purpose='renew' AND n.started_day>=? GROUP BY n.id",(agency,(season-1)*224))] if wrapup else []
        annual=c.execute('SELECT status FROM annual_sessions WHERE season=?',(season,)).fetchone()
        series=[tuple(r) for r in c.execute('SELECT round_number,agency_a,agency_b,winner_id FROM final_series WHERE season=? ORDER BY round_number',(season,))]
        return dict(day=day,names=names,agency=agency,ranks=ranks,counts=counts,leaders=leaders,players=players,contracts=contracts,
            negotiations=negotiations,annual=annual[0] if annual else '미시작',final=dict(final) if final else None,series=series)


class SeasonHub(QWidget):
    def __init__(self,service,window,*,wrapup=False):
        super().__init__();self.service=service;self.main_window=window;self.wrapup=wrapup
        layout=QVBoxLayout(self);layout.setContentsMargins(20,16,20,16)
        title=QLabel('시즌 마무리' if wrapup else '중간점검');title.setObjectName('title');layout.addWidget(title)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('summary');layout.addWidget(self.summary)
        self.notice=QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.rank_table=hub_table();self.tabs.addTab(self.rank_table,'정규 최종 순위' if wrapup else '상반기 순위')
        self.players=hub_table();self.tabs.addTab(self.players,'우리 선수 기록')
        self.contracts=hub_table();self.tabs.addTab(self.contracts,'계약 현황')
        if wrapup:
            self.post=hub_table();self.tabs.addTab(self.post,'포스트시즌')
            self.renewals=hub_table();self.tabs.addTab(self.renewals,'재계약 현황')
        self.tasks=QLabel();self.tasks.setWordWrap(True);layout.addWidget(self.tasks)
        links=QHBoxLayout();layout.addLayout(links);self.actions={}
        for key,text,callback in (('squad','선수단 관리',window.show_squads),('training','성장 · 훈련',window.show_development),('market','선수 시장',window.show_market),('draft','연간 드래프트',window.show_annual)):
            b=QPushButton(text);b.clicked.connect(callback);links.addWidget(b);self.actions[key]=b
        refresh=QPushButton('새로고침');refresh.clicked.connect(self.reload);layout.addWidget(refresh)
    def showEvent(self,event):
        super().showEvent(event);self.reload()
    def reload(self):
        try:
            data=read_summary(self.service.database,self.wrapup)
            if not data:self.notice.setText('기록 없음');return
            d=data['day'];allowed,reason=availability(d,self.wrapup)
            if not allowed:
                self.notice.setText(reason);self.tabs.setEnabled(False)
                for b in self.actions.values():b.setEnabled(False)
                return
            self.tabs.setEnabled(True)
            for b in self.actions.values():b.setEnabled(True)
            names=data['names'];agency=data['agency'];ranks=data['ranks'];counts=data['counts']
            own=next((r for r in ranks if r['agency_id']==agency),None)
            rank=next((i+1 for i,r in enumerate(ranks) if r['agency_id']==agency),None)
            record=f"{rank}위 · {own['wins']}승 {own['losses']}패" if own else '기록 없음'
            self.summary.setText(f"{d}\n{names.get(agency,'플레이어 미선택')} · {record}\n1군 {counts.get('first_team',0)}명 · 2군 {counts.get('second_team',0)}명 · 연습생 {counts.get('trainee',0)}명 · 리더 {data['leaders']}/2명")
            rows=[];last=None;place=0
            for i,r in enumerate(ranks):
                if r['points']!=last:place=i+1
                rows.append((i+1 if self.wrapup and data['final'] and data['final']['final_order_json'] else place,names.get(r['agency_id'],r['agency_id']),r['wins'],r['losses'],r['points']))
                last=r['points']
            fill_table(self.rank_table,('순위','기획사','승','패','승점'),rows)
            fill_table(self.players,('이름','출전','승리 아이돌','패배 아이돌','일반 성공 합계','성공률(%)'),data['players'])
            fill_table(self.contracts,('이름','종료 시즌','연봉(만원)','상태'),[(n,e if e is not None else '미정',a,s) for n,e,a,s in data['contracts']])
            squad=self.service.squads.change_reason()
            purposes=('renew','draft','fa','debut','trainee')
            reasons={p:self.service.market.action_reason(agency,p) if agency else '플레이어 기획사를 선택해 주세요.' for p in purposes}
            labels={'renew':'재계약','draft':'연간 드래프트 계약','fa':'FA 영입','debut':'프로 데뷔','trainee':'연습생 신청'}
            self.tasks.setText('현재 업무\n선수단 변경: '+(squad or '가능')+'\n'+'\n'.join(f'{labels[p]}: {reasons[p] or "가능"}' for p in purposes))
            self.actions['draft'].setEnabled(not reasons['draft']);self.actions['draft'].setToolTip(reasons['draft'] or '기존 연간 드래프트 화면으로 이동')
            self.actions['market'].setToolTip('화면에서 업무별 기존 허용 조건을 적용합니다.')
            if self.wrapup:
                f=data['final'];champion=names.get(f['champion_id'],'기록 없음') if f else '기록 없음'
                self.notice.setText(f"우승: {champion} · 포스트시즌: {f['status'] if f else '기록 없음'} · 연간 드래프트: {data['annual']}\n다음 시즌 확인: 만료 계약·선수단 결원·양군 리더·드래프트·FA 업무를 확인하세요. 시상식은 기존 별도 메뉴에서 확인합니다.")
                fill_table(self.post,('라운드','기획사 A','기획사 B','승자'),[(r,names.get(a,a),names.get(b,b),names.get(w,'기록 없음')) for r,a,b,w in data['series']])
                states={'open':'협상 중','accepted':'완료','failed':'실패','abandoned':'포기'}
                fill_table(self.renewals,('이름','상태','제안 횟수'),[(n,states.get(s,s),k) for n,s,k in data['negotiations']])
            else:self.notice.setText('전반기 정규 경기 기록 기준 · 승점은 기존 리그 집계(특별전·재정 조정 포함)입니다.\n하반기 시작 전: 1군 5명·프로 최대 16명 및 양군 리더를 확인하세요. 성장·훈련 기록 확인은 정산을 재실행하지 않습니다.')
            if not data['players']:self.notice.setText(self.notice.text()+'\n선수 경기 기록 없음')
        except (ValueError,sqlite3.Error) as error:self.notice.setText('조회 실패: '+str(error))
