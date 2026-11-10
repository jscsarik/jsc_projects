from .game_clock import regular_day
"""Atomic contracts, auctions and transfers. All player valuation uses public DTOs."""
from contextlib import closing,contextmanager
from collections import Counter
import json,uuid,secrets,random,sqlite3
from fractions import Fraction
from .game_clock import GameDate,current_game_date
from .config import SKILLS
from .finance_service import FinanceService,cash,debt,journal,income,obligation,round_10000,salary_parts
from .market_rules import market_salary,acceptance,raised_offer,player_value,trade_response
from .conditions import sync_rosters,promotion_allowed

PRO=('pro_pending','first_team','second_team')
class MarketError(ValueError):pass
def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)
def key():return uuid.uuid4().hex
def date(c):
    day=current_game_date(c)
    if day is None:raise MarketError('새 게임을 먼저 생성해 주세요.')
    return day

def initialize_market(c):
    previous=c.row_factory;c.row_factory=sqlite3.Row
    try:
        d=current_game_date(c)
        if d is None or c.execute('SELECT 1 FROM market_runtime').fetchone():return
        c.execute('INSERT INTO market_runtime VALUES (1,?)',(d.absolute_day,))
        sync_terms(c)
        for r in c.execute('''SELECT r.person_id,r.agency_id,r.career_status FROM roster_memberships r'''):
            professional=c.execute("SELECT 1 FROM professional_history WHERE person_id=?",(r['person_id'],)).fetchone() is not None
            c.execute('INSERT INTO market_careers VALUES (?,?,?,?,NULL)',(r['person_id'],1 if professional or r['career_status'] in PRO else None,r['agency_id'],d.season if r['agency_id'] is None else None))
    finally:c.row_factory=previous

def sync_terms(c):
    for r in c.execute('SELECT * FROM finance_contracts WHERE id NOT IN (SELECT contract_id FROM market_terms)').fetchall():
        c.execute('INSERT INTO market_terms VALUES (?,?,?,?,?)',(r['id'],r['id'],GameDate(r['start_day']).season,None,'legacy_expiry_unknown_preserved'))

def active_contract(c,person,day=None):
    day=date(c).absolute_day if day is None else day
    return c.execute('''SELECT x.*,t.root_id,t.start_season,t.end_season FROM finance_contracts x
        LEFT JOIN market_terms t ON t.contract_id=x.id WHERE x.person_id=? AND x.start_day<=? AND (x.end_day IS NULL OR x.end_day>?) ORDER BY x.start_day DESC LIMIT 1''',(person,day,day)).fetchone()

def _settlement(c,agency,event):
    d=date(c);identity=f'market:{event}:{agency}'
    c.execute("INSERT INTO finance_settlements VALUES (?,1,?,?,?,?, 'market')",(identity,agency,d.season,d.week,d.absolute_day))
    return dict(id=identity,agency=agency,season=d.season,week=d.week,day=d.absolute_day)

def _history(c,person,old,new,kind,contract=None,*,cash_amount=0,penalty=0,related=None,details=None):
    identity=key();d=date(c)
    c.execute('INSERT INTO market_history VALUES (?,1,?,?,?,?,?,?,?,?,?,?,?)',
        (identity,person,old,new,d.absolute_day,kind,contract['id'] if contract else None,contract['annual_krw'] if contract else None,cash_amount,penalty,related,dump(details or {})))
    return identity

def roster(c,agency):return [dict(r) for r in c.execute('SELECT * FROM roster_memberships WHERE agency_id=?',(agency,))]
def _owned(c,person,agency=None):
    r=c.execute('SELECT r.*,i.age FROM roster_memberships r JOIN idols i ON i.person_id=r.person_id WHERE r.person_id=?',(person,)).fetchone()
    if r is None or (agency is not None and r['agency_id']!=agency):raise MarketError('선수의 현재 소속이 변경되었습니다. 다시 확인해 주세요.')
    return r

def trainee_eligible(c,person):
    """Never-professional, publicly introduced candidates may sign from age 14."""
    p=_owned(c,person)
    return (p['agency_id'] is None and p['career_status'] in ('fa','unassigned') and p['age']>=14
        and c.execute("SELECT 1 FROM idols WHERE person_id=? AND status='candidate'",(person,)).fetchone() is not None
        and not c.execute('SELECT 1 FROM professional_history WHERE person_id=?',(person,)).fetchone()
        and not c.execute('SELECT 1 FROM market_careers WHERE person_id=? AND debut_season IS NOT NULL',(person,)).fetchone()
        and not c.execute("SELECT 1 FROM market_auctions WHERE person_id=? AND status='open'",(person,)).fetchone()
        and not c.execute("SELECT 1 FROM market_negotiations WHERE person_id=? AND status='open'",(person,)).fetchone())

def _safe_day(c,*,monday=True):
    d=date(c)
    if d.is_founding:raise MarketError('창단 준비에는 지명 계약·FA 직접 협상·월요일 연습생 신청만 가능합니다.')
    if monday and d.weekday()!=0:raise MarketError('계약·방출·트레이드 최종 처리는 월요일에 가능합니다. 포스트시즌 금요일은 선수단 교체만 허용합니다.')
    if c.execute("SELECT 1 FROM match_runs WHERE status!='completed' UNION ALL SELECT 1 FROM final_contests WHERE status='prepared' UNION ALL SELECT 1 FROM special_rounds WHERE status='prepared'").fetchone():raise MarketError('준비·진행 중인 경기가 있어 계약 선수 구성을 변경할 수 없습니다.')
    return d

def _vacancies(c,agency):
    released=c.execute("SELECT COUNT(*) FROM market_history WHERE from_agency=? AND kind='release' AND absolute_day>=?",(agency,(date(c).season-1)*224)).fetchone()[0]
    replacements=c.execute("SELECT COUNT(*) FROM market_history WHERE to_agency=? AND kind IN ('fa','debut') AND absolute_day>=?",(agency,(date(c).season-1)*224)).fetchone()[0]
    return max(0,released-replacements)

def _entry_day(c,agency,purpose):
    d=date(c)
    if d.is_founding:
        from .founding import staged
        if staged(c):
            if purpose=='founding' and d.weekday()==1:return d
            if purpose=='fa' and d.weekday() in (3,5):return d
            if purpose=='trainee' and d.weekday() in (2,4):return d
            raise MarketError('창단 계약은 화요일, 연습생 신청은 수·금요일, FA 영입은 목·토요일에 가능합니다. 최초 편성은 다음 월요일입니다.')
        if d.weekday()!=0:raise MarketError('창단 준비의 계약·선수단 준비는 첫 월요일에 완료해 주세요.')
        if purpose=='founding':return d
        if purpose=='fa' and sum(r['career_status'] in PRO for r in roster(c,agency))<16:return d
        if purpose=='trainee':return d
        raise MarketError('창단 준비의 프로 결원은 FA 직접 협상으로 보충해 주세요.')
    if purpose=='founding':raise MarketError('창단 상위 지명 계약은 창단 화요일에만 진행합니다.')
    if d.is_offseason and d.week==3 and purpose=='fa':
        event=c.execute('SELECT 1 FROM annual_intakes WHERE season=?',(d.season,)).fetchone()
        if event:
            from .annual_draft import draft_issue
            issue=draft_issue(c,d.season)
            if issue:raise MarketError(issue)
    if purpose=='renew':
        if not d.is_offseason or d.week!=1:raise MarketError('재계약은 비시즌 1주차에 진행합니다.')
    elif purpose=='debut':
        if d.is_maintenance or (d.is_preparation and not d.is_founding):return d
        raise MarketError('프로 데뷔는 17세 이상 연습생이 중간 정비 또는 시즌 준비 주의 데뷔 절차에서만 진행할 수 있습니다.')
    elif purpose=='trainee':
        if d.weekday()!=0:raise MarketError('연습생 자유계약은 매주 월요일 신청 후 동시 추첨합니다.')
    elif purpose=='draft':
        if not d.is_offseason or d.week!=2:raise MarketError('통합 드래프트 계약 연결은 비시즌 2주차에 가능합니다.')
    else:
        if d.is_offseason and d.week==3:return d
        _safe_day(c)
        if not d.is_regular:raise MarketError('FA 영입은 정규 월요일 또는 비시즌 3주차에 가능합니다.')
    return d

def _slot(c,agency,*,trainee=False,excluding_auction=None):
    if trainee:return
    count=sum(r['career_status'] in PRO for r in roster(c,agency))
    held=c.execute("SELECT COUNT(DISTINCT a.id) FROM market_auctions a JOIN market_bids b ON b.auction_id=a.id WHERE a.status='open' AND b.agency_id=? AND a.id!=?",(agency,excluding_auction or '')).fetchone()[0]
    if count+held>=16:raise MarketError('프로 정원 16명 또는 진행 중인 FA 입찰의 예약 자리를 초과합니다.')
    if sum(r['career_status']=='second_team' for r in roster(c,agency))>=11:raise MarketError('신규 프로 선수는 2군에 등록됩니다. 2군 자리를 먼저 확보해 주세요.')

def _budget(c,agency,annual,*,exclude_person=None,exclude_auction=None):
    FinanceService(None).validate_spend(agency,(annual+5)//6,connection=c)
    now=date(c).absolute_day
    current=c.execute("SELECT COALESCE(SUM(annual_krw),0) FROM finance_contracts WHERE agency_id=? AND (kind='pro' OR id IN (SELECT contract_id FROM paid_draft_contracts)) AND person_id!=? AND start_day<=? AND (end_day IS NULL OR end_day>?)",(agency,exclude_person or '',now,now)).fetchone()[0]
    promises=c.execute("SELECT COALESCE(SUM(value),0) FROM (SELECT MAX(b.annual) AS value FROM market_bids b JOIN market_auctions a ON a.id=b.auction_id WHERE b.agency_id=? AND a.status='open' AND a.id!=? GROUP BY a.id)",(agency,exclude_auction or '')).fetchone()[0]
    operating=sum(r['career_status'] in ('second_team','trainee') for r in roster(c,agency))*100000*2
    if cash(c,agency)<(current+promises+annual+5)//6+operating:raise MarketError('기존 급여·운영비와 다른 입찰 약정을 포함하면 계약 예산이 부족합니다.')

def _close(c,contract,day):
    if contract and (contract['end_day'] is None or contract['end_day']>day):c.execute('UPDATE finance_contracts SET end_day=? WHERE id=?',(day,contract['id']))

def _new_contract(c,person,agency,annual,duration,kind,*,inherit=None,renew=False,finite_trainee=False):
    d=date(c);old=active_contract(c,person);_close(c,old,d.absolute_day)
    identity=key()
    start_season=(d.season+1 if d.is_offseason else d.season)
    end_season=start_season+duration-1
    if inherit:
        end=inherit['end_day'];start_season=inherit['start_season'];end_season=inherit['end_season']
        root=inherit['root_id'] or inherit['id'];kind=inherit['kind'];annual=inherit['annual_krw']
    else:
        end=(end_season-1)*224+210;root=identity
        if kind!='pro' and not finite_trainee:end=None;end_season=None
    c.execute('INSERT INTO finance_contracts VALUES (?,1,?,?,?,?,?,?,?)',(identity,person,agency,kind,annual,d.absolute_day,end,'market19'))
    c.execute('INSERT INTO market_terms VALUES (?,?,?,?,?)',(identity,root,start_season,end_season,'transfer' if inherit else 'renewal' if renew else 'signed'))
    if inherit:
        paid=c.execute('SELECT negotiated FROM paid_draft_contracts WHERE contract_id=?',(inherit['id'],)).fetchone()
        if paid:c.execute('INSERT INTO paid_draft_contracts VALUES (?,1,?)',(identity,paid[0]))
    return active_contract(c,person)

def _move(c,person,new,role,reason,contract=None,related=None,*,cash_amount=0,penalty=0):
    d=date(c);old=_owned(c,person)['agency_id']
    c.execute('DELETE FROM squad_leaders WHERE person_id=? AND (agency_id IS NOT ? OR squad IS NOT ?)',(person,new,role))
    c.execute('UPDATE roster_memberships SET agency_id=?,career_status=? WHERE person_id=?',(new,role,person))
    c.execute('UPDATE squad_formations SET revision=revision+1 WHERE agency_id IN (?,?)',(old,new))
    c.execute('UPDATE market_careers SET last_agency=COALESCE(?,last_agency),unemployed_since=?,retired_day=? WHERE person_id=?',
        (old,None if new else d.season,d.absolute_day if role=='retired' else None,person))
    if role in PRO:
        founder=c.execute('SELECT 1 FROM draft_picks WHERE person_id=?',(person,)).fetchone()
        first=c.execute("SELECT MIN(t.start_season) FROM finance_contracts x JOIN market_terms t ON t.contract_id=x.id WHERE x.person_id=? AND x.kind='pro'",(person,)).fetchone()[0]
        debut=1 if founder else first or d.season+int(d.is_offseason)
        c.execute('UPDATE market_careers SET debut_season=COALESCE(debut_season,?) WHERE person_id=?',(debut,person))
    if new is None and role in ('fa','unassigned') and not d.is_regular and not d.is_postseason and d.week==2:
        c.execute("INSERT OR IGNORE INTO annual_pool SELECT season,? FROM annual_sessions WHERE season=? AND status='in_progress'",(person,d.season))
    sync_rosters(c,d.absolute_day,'market_'+reason)
    _history(c,person,old,new,reason,contract,related=related,cash_amount=cash_amount,penalty=penalty)

class MarketService:
    def __init__(self,database,*,seed_factory=None):self.database=database;self.seed_factory=seed_factory or (lambda:secrets.randbits(128))
    def action_reason(self,agency,purpose):
        if not agency:return '플레이어 기획사를 선택해 주세요.'
        with closing(self.database.connect()) as c:
            try:
                if purpose in ('trade','release'):
                    d=date(c);_safe_day(c,monday=purpose=='trade' or d.is_regular or d.is_postseason or d.is_founding)
                else:_entry_day(c,agency,purpose)
            except ValueError as error:return str(error)
        return ''
    def propose_trade(self,a,b,terms,*,request_id):return propose_trade(self,a,b,terms,request_id=request_id)
    def trade_reply(self,identity,agency,action,*,terms=None,expected_version):return trade_reply(self,identity,agency,action,terms=terms,expected_version=expected_version)
    def trades(self):return trades(self)
    def evaluate_trade(self,identity,agency):return evaluate_trade(self,identity,agency)
    def ai_trade_reply(self,identity,agency):return ai_trade_reply(self,identity,agency)
    def force_sale(self,agency,*,request_id):return force_sale(self,agency,request_id=request_id)
    def abandon(self,negotiation,agency):return abandon(self,negotiation,agency)
    def connect_draft_pick(self,agency,person,season,*,pick_id):return connect_draft_pick(self,agency,person,season,pick_id=pick_id)
    def record_draft_outcome(self,season,person,*,picked):return record_draft_outcome(self,season,person,picked=picked)
    def release_quote(self,agency,person):return release_quote(self,agency,person)
    def release_balances(self,agency):
        with closing(self.database.connect()) as c:
            return tuple(dict(p,remaining=_release_remaining(c,p)) for p in c.execute('''SELECT r.*,p.name FROM market_release_plans r
                JOIN people p ON p.id=r.person_id WHERE agency_id=? AND method='installments' ORDER BY absolute_day,id''',(agency,)))
    def prepay_release(self,agency,plan_id,*,expected_remaining=None):
        """User-authorized full cash payoff; past installments stay immutable."""
        with self.write() as c:
            p=c.execute("SELECT * FROM market_release_plans WHERE id=? AND agency_id=? AND method='installments'",(plan_id,agency)).fetchone()
            if p is None:raise MarketError('해당 기획사의 분할 방출 위약금이 아닙니다.')
            event='release-prepay:'+plan_id;identity=f'market:{event}:{agency}'
            prior=c.execute("SELECT * FROM finance_ledger WHERE settlement_id=? AND kind='release_prepayment'",(identity,)).fetchone()
            if prior:return dict(prior)
            remaining=_release_remaining(c,p)
            if expected_remaining is not None and expected_remaining!=remaining:raise MarketError('상환 잔액이 변경되었습니다. 새로고침한 뒤 다시 확인해 주세요.')
            if remaining<=0:raise MarketError('이미 납부를 마친 위약금입니다.')
            if cash(c,agency)<remaining:raise MarketError('남은 방출 위약금을 전액 상환할 현금이 부족합니다.')
            s=_settlement(c,agency,event)
            c.execute('''UPDATE finance_debts SET outstanding_krw=0 WHERE id=? OR
                (kind='release_due' AND settlement_id IN (SELECT settlement_id FROM market_installments WHERE plan_id=?))''',(p['debt_id'],plan_id))
            journal(c,s,'release_prepayment',remaining,cash_delta=-remaining,debt_delta=-remaining,person=p['person_id'],description='남은 방출 위약금 전액 조기 상환 · 계획 '+plan_id)
            _history(c,p['person_id'],agency,agency,'release_prepayment',related=plan_id,cash_amount=remaining)
            return dict(c.execute("SELECT * FROM finance_ledger WHERE settlement_id=? AND kind='release_prepayment'",(identity,)).fetchone())
    @contextmanager
    def write(self):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');sync_terms(c)
            state=c.execute('SELECT status FROM draft_state WHERE id=1').fetchone()
            if not state or state[0]!='completed':raise MarketError('최초 드래프트 완료 후 선수 시장을 이용할 수 있습니다.')
            yield c
    def public_people(self,*,agency=None,available=False):
        with closing(self.database.connect()) as c:return public_people(c,agency=agency,available=available)
    def history(self,person=None):
        with closing(self.database.connect()) as c:return tuple(dict(r) for r in c.execute('SELECT * FROM market_history'+(' WHERE person_id=?' if person else '')+' ORDER BY absolute_day,rowid',(person,) if person else ()))
    def negotiations(self,agency=None):
        with closing(self.database.connect()) as c:
            rows=c.execute('SELECT * FROM market_negotiations'+(' WHERE agency_id=?' if agency else '')+' ORDER BY started_day DESC,id',(agency,) if agency else ()).fetchall()
            return tuple(dict(r,offers=[dict(o) for o in c.execute('SELECT * FROM market_offers WHERE negotiation_id=? ORDER BY ordinal',(r['id'],))]) for r in rows)
    def start_negotiation(self,agency,person,purpose,*,context=None):
        if purpose not in ('renew','debut','fa','draft','founding'):raise MarketError('협상 종류가 올바르지 않습니다.')
        with self.write() as c:
            d=_entry_day(c,agency,purpose);p=_owned(c,person)
            if purpose=='founding':
                right=c.execute("SELECT negotiation_id FROM founding_contracts WHERE person_id=? AND agency_id=? AND status='pending'",(person,agency)).fetchone()
                if not right:raise MarketError('진행할 창단 상위 지명 계약이 없습니다.')
                return right[0]
            if purpose in ('renew','debut') and p['agency_id']!=agency:raise MarketError('소속 선수만 재계약·데뷔 협상을 할 수 있습니다.')
            if purpose=='draft' and not c.execute('SELECT 1 FROM market_draft_rights WHERE season=? AND agency_id=? AND person_id=? AND consumed=0',(d.season,agency,person)).fetchone():raise MarketError('확정된 통합 드래프트 지명권 연결이 없습니다. 드래프트를 우회해 계약할 수 없습니다.')
            if purpose=='debut' and (p['career_status']!='trainee' or p['age']<17):raise MarketError('17세 이상 소속 연습생만 프로 데뷔가 가능합니다.')
            if purpose=='renew' and p['career_status'] not in PRO and not c.execute('SELECT 1 FROM paid_draft_contracts z JOIN finance_contracts x ON x.id=z.contract_id WHERE x.person_id=? AND z.negotiated=1 AND (x.end_day IS NULL OR x.end_day>?)',(person,d.absolute_day)).fetchone():raise MarketError('프로 또는 협상 계약을 가진 드래프트 연습생만 재계약할 수 있습니다.')
            if purpose in ('fa','draft') and (p['agency_id'] is not None or p['career_status'] not in ('fa','unassigned') or p['age']<17):raise MarketError('계약 가능한 17세 이상 미소속 선수만 협상할 수 있습니다.')
            if c.execute("SELECT 1 FROM market_auctions WHERE person_id=? AND status='open'",(person,)).fetchone():raise MarketError('공개 입찰 중인 선수는 FA 시장에서 입찰해 주세요.')
            _budget(c,agency,30000000,exclude_person=person)
            context=context or f'{d.season}:{d.day_in_season//7}'
            row=c.execute('SELECT id FROM market_negotiations WHERE agency_id=? AND person_id=? AND purpose=? AND context=?',(agency,person,purpose,context)).fetchone()
            if row:return row[0]
            identity=key();c.execute("INSERT INTO market_negotiations VALUES (?,1,?,?,?,'open',?,?)",(identity,agency,person,purpose,d.absolute_day,str(context)));return identity
    def offer(self,negotiation,annual,duration,*,request_id):
        if type(annual) is not int or annual<=0 or annual%10000 or duration not in (1,2):raise MarketError('연봉은 만 원 단위 양수, 계약기간은 1~2시즌이어야 합니다.')
        with self.write() as c:
            cached=c.execute('SELECT * FROM market_offers WHERE id=?',(request_id,)).fetchone()
            if cached:
                if cached['negotiation_id']!=negotiation or cached['annual']!=annual or cached['duration']!=duration:raise MarketError('동일 요청 ID로 다른 제안을 실행할 수 없습니다.')
                return dict(cached)
            n=c.execute('SELECT * FROM market_negotiations WHERE id=?',(negotiation,)).fetchone()
            if not n or n['status']!='open':raise MarketError('종료되었거나 없는 협상입니다.')
            d=_entry_day(c,n['agency_id'],n['purpose']);p=_owned(c,n['person_id'])
            if n['purpose'] in ('renew','debut','founding') and p['agency_id']!=n['agency_id']:raise MarketError('선수 소속이 변경되었습니다.')
            if n['purpose'] in ('fa','draft') and p['agency_id'] is not None:raise MarketError('이미 계약된 선수입니다.')
            if n['purpose'] in ('fa','draft') and c.execute("SELECT 1 FROM market_auctions WHERE person_id=? AND status='open'",(n['person_id'],)).fetchone():
                raise MarketError('협상 개시 후 공개 입찰이 시작되었습니다. FA 시장의 입찰로 참여해 주세요.')
            prior=c.execute('SELECT * FROM market_offers WHERE negotiation_id=? ORDER BY ordinal DESC LIMIT 1',(negotiation,)).fetchone()
            ordinal=prior['ordinal']+1 if prior else 1
            if ordinal>3:raise MarketError('협상은 최대 3회입니다.')
            if n['purpose']=='debut' and annual!=30000000:raise MarketError('프로 데뷔 첫 계약 연봉은 3,000만 원 고정입니다.')
            if prior and n['purpose']!='debut' and annual<raised_offer(prior['annual']):raise MarketError('거절 후에는 직전 제안보다 5% 인상한 금액 이상을 제안해 주세요.')
            as_trainee=n['purpose']=='draft' and c.execute("SELECT 1 FROM annual_turns WHERE pick_id=? AND registration='trainee'",(n['context'],)).fetchone()
            if n['purpose']=='draft' and annual<30000000:raise MarketError('17세 이상 드래프트 계약 연봉은 최소 3,000만 원입니다.')
            if n['purpose'] not in ('renew','founding') and not as_trainee:_slot(c,n['agency_id'])
            _budget(c,n['agency_id'],annual,exclude_person=n['person_id'])
            renew_trainee=n['purpose']=='renew' and p['career_status']=='trainee'
            if n['purpose']=='debut':probability=acceptance(annual,30000000)
            else:probability=acceptance(annual,internal_market_salary(c,n['person_id']))
            seed=self.seed_factory();roll=random.Random(seed).random();accepted=roll<probability
            c.execute('INSERT INTO market_offers VALUES (?,?,?,?,?,?,?,?,?,?)',(request_id,negotiation,ordinal,annual,duration,probability,str(seed),roll,int(accepted),d.absolute_day))
            if accepted:
                contract=_new_contract(c,n['person_id'],n['agency_id'],annual,duration,'draft_trainee' if as_trainee or renew_trainee else 'pro',renew=n['purpose']=='renew',finite_trainee=bool(as_trainee or renew_trainee))
                if as_trainee or renew_trainee:
                    c.execute('INSERT INTO paid_draft_contracts VALUES (?,1,1)',(contract['id'],))
                if n['purpose']=='renew':_history(c,n['person_id'],n['agency_id'],n['agency_id'],'renew',contract,related=negotiation)
                else:
                    pending=d.is_founding and not c.execute('SELECT 1 FROM squad_formations WHERE agency_id=?',(n['agency_id'],)).fetchone()
                    _move(c,n['person_id'],n['agency_id'],'trainee' if as_trainee else 'pro_pending' if pending else 'second_team','founding_contract' if n['purpose']=='founding' else 'debut' if n['purpose']=='debut' else 'fa',contract,negotiation)
                c.execute("UPDATE market_negotiations SET status='accepted' WHERE id=?",(negotiation,))
            elif ordinal==3:
                c.execute("UPDATE market_negotiations SET status='failed' WHERE id=?",(negotiation,))
                _history(c,n['person_id'],n['agency_id'],n['agency_id'],'negotiation_failed',related=negotiation)
                if n['purpose']=='draft':_move(c,n['person_id'],None,'fa','draft_contract_failed',related=negotiation)
                if n['purpose']=='founding':_move(c,n['person_id'],None,'fa','founding_contract_failed',related=negotiation)
            if n['purpose']=='founding' and (accepted or ordinal==3):
                c.execute('UPDATE founding_contracts SET status=? WHERE person_id=?',('signed' if accepted else 'failed',n['person_id']))
            if n['purpose']=='draft' and (accepted or ordinal==3):c.execute('UPDATE market_draft_rights SET consumed=1 WHERE season=? AND agency_id=? AND person_id=?',(d.season,n['agency_id'],n['person_id']))
            if n['purpose']=='draft':
                from .annual_draft import sync_session
                sync_session(c,d.season)
            return dict(c.execute('SELECT * FROM market_offers WHERE id=?',(request_id,)).fetchone())
    def sign_trainee(self,agency,person,*,drafted=False,request_id):
        with self.write() as c:
            if not drafted:
                from .trainee_recruitment import request_one
                return request_one(c,agency,person,request_id)
            if c.execute('SELECT 1 FROM market_history WHERE related_id=?',(request_id,)).fetchone():return
            _entry_day(c,agency,'draft' if drafted else 'trainee');p=_owned(c,person)
            if not trainee_eligible(c,person):raise MarketError('프로 경력이 없는 미소속 14세 이상 공개 후보만 연습생 자유계약이 가능합니다.')
            if drafted and (p['age']>16 or not c.execute('SELECT 1 FROM market_draft_rights WHERE season=? AND agency_id=? AND person_id=? AND consumed=0',(date(c).season,agency,person)).fetchone()):raise MarketError('확정된 미성년 드래프트 지명권이 필요합니다.')
            _budget(c,agency,0)
            contract=_new_contract(c,person,agency,20000000 if drafted else 0,1,'draft_trainee' if drafted else 'free_trainee')
            if drafted:c.execute('INSERT INTO paid_draft_contracts VALUES (?,1,0)',(contract['id'],))
            _move(c,person,agency,'trainee','trainee',contract,request_id)
    def bid(self,agency,person,annual,duration,*,request_id):
        if type(annual) is not int or annual<=0 or annual%10000 or duration not in (1,2):raise MarketError('만 원 단위 연봉과 1~2시즌을 선택해 주세요.')
        with self.write() as c:
            from .founding import staged
            if date(c).is_founding and not staged(c):raise MarketError('기존 창단 준비의 결원은 FA 직접 협상으로 보충합니다.')
            prior=c.execute('SELECT * FROM market_bids WHERE id=?',(request_id,)).fetchone()
            if prior:
                if prior['agency_id']!=agency or prior['annual']!=annual or prior['duration']!=duration:raise MarketError('다른 입찰과 동일한 요청 ID입니다.')
                return prior['auction_id']
            d=_entry_day(c,agency,'fa');p=_owned(c,person)
            if p['agency_id'] is not None or p['career_status'] not in ('fa','unassigned') or p['age']<17:raise MarketError('계약 가능한 FA 선수가 아닙니다.')
            close=(d.season-1)*224+224
            a=c.execute('SELECT * FROM market_auctions WHERE person_id=? AND season=?',(person,d.season)).fetchone()
            if a and (a['status']!='open' or d.absolute_day>=a['deadline']):raise MarketError('입찰 기간이 종료되었습니다.')
            auction=a['id'] if a else key()
            _slot(c,agency,excluding_auction=auction);_budget(c,agency,annual,exclude_auction=auction)
            high=c.execute('SELECT COALESCE(MAX(annual),0) FROM market_bids WHERE auction_id=?',(auction,)).fetchone()[0]
            own=c.execute('SELECT COALESCE(MAX(annual),0) FROM market_bids WHERE auction_id=? AND agency_id=?',(auction,agency)).fetchone()[0]
            if annual<high or annual<=own:raise MarketError('현재 최고액 이상이며 자신의 직전 입찰보다 높은 연봉이 필요합니다.')
            if not a:
                original=c.execute('SELECT last_agency FROM market_careers WHERE person_id=?',(person,)).fetchone()
                c.execute("INSERT INTO market_auctions VALUES (?,1,?,?,?,?,?,'open',NULL,NULL,'{}')",(auction,person,d.season,original[0] if original else None,min(d.absolute_day+2,close),close))
            elif annual>high:c.execute('UPDATE market_auctions SET deadline=? WHERE id=?',(min(d.absolute_day+2,close),auction))
            c.execute('INSERT INTO market_bids VALUES (?,?,?,?,?,?)',(request_id,auction,agency,annual,duration,d.absolute_day));return auction
    def auctions(self):
        with closing(self.database.connect()) as c:return tuple(dict(r,bids=[dict(b) for b in c.execute('SELECT * FROM market_bids WHERE auction_id=? ORDER BY annual DESC,id',(r['id'],))]) for r in c.execute('SELECT * FROM market_auctions ORDER BY season DESC,id'))
    def release(self,agency,person,method,*,request_id):
        if method not in ('immediate','installments'):raise MarketError('즉시 지급 또는 10주 분할을 선택해 주세요.')
        with self.write() as c:
            done=c.execute('SELECT * FROM market_release_plans WHERE id=?',(request_id,)).fetchone()
            if done:return dict(done)
            day=date(c);d=_safe_day(c,monday=day.is_regular or day.is_postseason or day.is_founding);p=_owned(c,person,agency);contract=active_contract(c,person)
            if p['career_status'] not in PRO or not contract:raise MarketError('유효한 프로 계약이 없습니다.')
            total=release_penalty(c,contract,d.absolute_day)
            if method=='immediate':FinanceService(None).validate_spend(agency,total,connection=c)
            s=_settlement(c,agency,request_id);debt_id=None
            if method=='immediate':journal(c,s,'release_penalty',total,cash_delta=-total,person=person,description='중도 방출 위약금 즉시 지급')
            elif total:
                cur=c.execute("INSERT INTO finance_debts(game_id,settlement_id,agency_id,person_id,kind,original_krw,outstanding_krw) VALUES (1,?,?,?,'release_scheduled',?,?)",(s['id'],agency,person,total,total));debt_id=cur.lastrowid
                journal(c,s,'release_penalty_debt',total,debt_delta=total,person=person,description='위약금 10주 확정 의무 · 미래 회차 선결제 아님')
            _close(c,contract,d.absolute_day)
            _move(c,person,None,'retired' if p['age']>=33 else 'fa','release',contract,request_id,penalty=total)
            c.execute('INSERT INTO market_release_plans VALUES (?,1,?,?,?,?,?,?,?,0)',(request_id,person,agency,d.absolute_day,total,method,debt_id,d.absolute_day+7))
            return dict(c.execute('SELECT * FROM market_release_plans WHERE id=?',(request_id,)).fetchone())

def internal_market_salary(c,person):
    age=c.execute('SELECT age FROM idols WHERE person_id=?',(person,)).fetchone()
    values={r[0]:r[1] for r in c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(person,))}
    return market_salary([values[s] for s in SKILLS],age[0])

def public_people(c,*,agency=None,available=False,person_ids=None):
    from .profile_service import ProfileService
    public=ProfileService.public_ids(c);out=[];d=current_game_date(c)
    sql="""SELECT p.id,p.name,p.photo_path,i.age,r.agency_id,r.career_status,k.last_agency,k.debut_season
        FROM people p JOIN idols i ON i.person_id=p.id JOIN roster_memberships r ON r.person_id=p.id
        LEFT JOIN market_careers k ON k.person_id=p.id WHERE r.career_status!='retired'
        AND (i.status='candidate' OR r.agency_id IS NOT NULL OR k.debut_season IS NOT NULL)"""
    args=[]
    if agency:sql+=' AND r.agency_id=?';args.append(agency)
    if available:sql+=' AND r.agency_id IS NULL'
    if person_ids is not None:
        if not person_ids:return ()
        sql+=' AND p.id IN ('+','.join('?' for _ in person_ids)+')';args.extend(person_ids)
    for r in c.execute(sql+' ORDER BY p.name,p.id',args).fetchall():
        p=dict(r);exact=p['id'] in public
        if exact:
            raw=dict(c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(p['id'],)));skills=[raw[s] for s in SKILLS]
            health=c.execute('SELECT health FROM idols WHERE person_id=?',(p['id'],)).fetchone()[0]
            injury=c.execute('SELECT injured FROM player_conditions WHERE person_id=?',(p['id'],)).fetchone()
            ranges=None
        else:
            raw={x['skill']:(x['low'],x['high']) for x in c.execute('SELECT skill,low,high FROM draft_estimates WHERE person_id=?',(p['id'],))}
            ranges=[raw.get(s) for s in SKILLS]
            skills=[int(sum(v)/2) if v else 50 for v in ranges];health=None;injury=None
        contract=active_contract(c,p['id']) if d else None
        growth=0
        past=None
        if exact:
            for row in c.execute("SELECT r.deltas_json FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE r.person_id=? ORDER BY s.absolute_day DESC,r.rowid ASC LIMIT 4",(p['id'],)):growth+=sum(json.loads(row[0]))
            stats=c.execute('SELECT SUM(base_successes),SUM(base_attempts) FROM match_player_stats WHERE person_id=?',(p['id'],)).fetchone()
            if stats[1]:past=stats[0]/stats[1]
        p['inherited_debut']=bool(contract and c.execute('SELECT 1 FROM paid_draft_contracts WHERE contract_id=? AND negotiated=1',(contract['id'],)).fetchone())
        p.update(exact=exact,skills=skills,ranges=ranges,average=sum(skills)/8,health=health,injured=bool(injury and injury[0]),
            market=market_salary(skills,p['age']) if p['age']>=17 else None,annual=contract['annual_krw'] if contract else 0,
            contract_id=contract['id'] if contract else None,end_season=contract['end_season'] if contract else None,observed_growth=growth,
            past_success_rate=past,remaining_seasons=max(0,contract['end_season']-max(d.season,contract['start_season'] or d.season)+1) if contract and contract['end_season'] is not None else None)
        out.append(p)
    return tuple(out)

def release_penalty(c,contract,day):
    # Remaining basic pay only; no activity bonus, arrears or operating fees.
    d=GameDate(day);end=contract['end_day']
    if end is not None and end<=day:return 0
    if contract['end_season'] is None:raise MarketError('이 계약은 만료일 미정입니다. 잔여 기본 급여를 확정할 수 없어 유한 기간으로 재계약한 뒤 방출해야 합니다.')
    remaining=0
    for season in range(d.season,contract['end_season']+1):
        for cycle in range(1,7):
            start=regular_day(season,(cycle-1)*4+1);stop=start+28
            covered=max(0,min(stop,end if end is not None else stop)-max(start,day,contract['start_day']))
            if covered:remaining+=Fraction(salary_parts(contract['annual_krw'],cycle,0,0)[0]*covered,28)
    return round_10000(remaining.numerator,remaining.denominator*3) if remaining else 0

# Methods are kept on the common facade so human and AI share validation.
def _trade_validate(c,a,b,terms,*,trade_id=None):
    if a==b:raise MarketError('서로 다른 두 기획사를 선택해 주세요.')
    from .trade_policy import validate_slots
    try:validate_slots(c,a,b,trade_id)
    except ValueError as error:raise MarketError(str(error)) from error
    for agency in (a,b):
        counts=Counter(r['career_status'] for r in roster(c,agency))
        if counts['first_team']!=5 or sum(counts[s] for s in PRO)>16 or counts['second_team']>11:
            raise MarketError('트레이드 전에 1군 5명 및 프로 정원을 정상적으로 편성해 주세요.')
    pa=_owned(c,terms['pro_a'],a);pb=_owned(c,terms['pro_b'],b)
    for token,person in (('contract_a',pa['person_id']),('contract_b',pb['person_id'])):
        current=active_contract(c,person)
        if token in terms and (not current or terms[token]!=current['id']):raise MarketError('거래 제안 이후 계약 조건이 변경되었습니다. 새 제안이 필요합니다.')
    if pa['career_status'] not in PRO or pb['career_status'] not in PRO:raise MarketError('프로 1명 대 프로 1명 교환이 기본입니다.')
    extras_a=tuple(terms.get('trainees_a',()));extras_b=tuple(terms.get('trainees_b',()))
    people=(pa['person_id'],pb['person_id'],*extras_a,*extras_b)
    if len(set(people))!=len(people) or len(extras_a)+len(extras_b)>3:raise MarketError('중복 선수 또는 추가 연습생 최대 3명 제한을 위반했습니다.')
    for pending in c.execute("SELECT t.id,v.terms_json FROM market_trades t JOIN market_trade_versions v ON v.trade_id=t.id AND v.version=t.version WHERE t.status IN ('proposed','countered','accepted_pending') AND t.id!=?",(trade_id or '',)):
        other=json.loads(pending['terms_json'])
        if set(people)&{other['pro_a'],other['pro_b'],*other.get('trainees_a',()),*other.get('trainees_b',())}:raise MarketError('이미 다른 협상·예약 거래에 포함된 선수입니다.')
    for agency,people in ((a,extras_a),(b,extras_b)):
        for person in people:
            if _owned(c,person,agency)['career_status']!='trainee':raise MarketError('추가 보상은 보유 연습생만 가능합니다.')
    for person in (pa['person_id'],pb['person_id'],*extras_a,*extras_b):
        if not active_contract(c,person):raise MarketError('거래 선수의 유효 계약이 없습니다.')
    amount=terms.get('cash',0)
    if type(amount) is not int:raise MarketError('현금은 원 단위 정수여야 합니다.')
    if amount:FinanceService(None).validate_spend(a if amount>0 else b,abs(amount),connection=c)
    for agency,own,other in ((a,pa,pb),(b,pb,pa)):
        if debt(c,agency) and active_contract(c,other['person_id'])['annual_krw']>active_contract(c,own['person_id'])['annual_krw']:raise MarketError('채무 상태에서는 연봉 부담을 늘리는 거래를 승인하지 않습니다.')
    return pa,pb

def _trade_execute(c,trade):
    if trade['status']=='completed':return
    _safe_day(c)
    version=c.execute('SELECT * FROM market_trade_versions WHERE trade_id=? AND version=?',(trade['id'],trade['version'])).fetchone()
    terms=json.loads(version['terms_json']);a,b=trade['agency_a'],trade['agency_b'];pa,pb=_trade_validate(c,a,b,terms,trade_id=trade['id'])
    if date(c).absolute_day<trade['created_day']-trade['created_day']%7+7:raise MarketError('합의한 거래는 다음 주 월요일에 체결합니다.')
    moving=[(pa['person_id'],a,b,pb['career_status']),(pb['person_id'],b,a,pa['career_status'])]
    moving.extend((p,a,b,'trainee') for p in terms.get('trainees_a',()))
    moving.extend((p,b,a,'trainee') for p in terms.get('trainees_b',()))
    contracts={p:dict(active_contract(c,p)) for p,_,_,_ in moving}
    for person,_,_,role in moving:
        c.execute('DELETE FROM squad_leaders WHERE person_id=?',(person,))
        c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status=? WHERE person_id=?",('unassigned' if role=='trainee' else 'fa',person))
    for person,old,new,role in moving:
        injury=c.execute('SELECT injured FROM player_conditions WHERE person_id=?',(person,)).fetchone()
        if role=='first_team' and (injury and injury[0] or not promotion_allowed(c,person,date(c).absolute_day)):
            choices=[p for p in public_people(c,agency=new) if p['career_status']=='second_team' and not p['injured'] and promotion_allowed(c,p['id'],date(c).absolute_day)]
            if not choices:raise MarketError('부상·복귀 제한 선수를 대신할 정상 1군 배치가 불가능합니다.')
            substitute=max(choices,key=lambda p:(p['average'],p['id']))
            c.execute("UPDATE roster_memberships SET career_status='first_team' WHERE person_id=?",(substitute['id'],));role='second_team'
        contract=_new_contract(c,person,new,0,1,contracts[person]['kind'],inherit=contracts[person])
        c.execute('UPDATE roster_memberships SET agency_id=?,career_status=? WHERE person_id=?',(new,role,person))
        c.execute('UPDATE market_careers SET last_agency=?,unemployed_since=NULL WHERE person_id=?',(old,person))
        _history(c,person,old,new,'trade',contract,cash_amount=terms.get('cash',0),related=trade['id'])
    amount=terms.get('cash',0)
    if amount:
        payer,receiver=(a,b) if amount>0 else (b,a);amount=abs(amount)
        s=_settlement(c,payer,trade['id']);journal(c,s,'trade_payment',amount,cash_delta=-amount,description='트레이드 현금 보상')
        s=_settlement(c,receiver,trade['id']);income(c,s,'trade_income',amount)
    for agency in (a,b):
        counts=Counter(r['career_status'] for r in roster(c,agency))
        if sum(counts[s] for s in PRO)>16 or counts['first_team']!=5 or counts['second_team']>11:raise MarketError('거래 후 1군 5명 및 프로 정원을 위반했습니다.')
        c.execute('UPDATE squad_formations SET revision=revision+1 WHERE agency_id=?',(agency,))
    sync_rosters(c,date(c).absolute_day,'trade')
    c.execute("UPDATE market_trades SET status='completed',executed_day=?,execution_json=? WHERE id=?",(date(c).absolute_day,dump(terms),trade['id']))

def propose_trade(self,a,b,terms,*,request_id):
    with self.write() as c:
        if c.execute('SELECT 1 FROM market_trades WHERE id=?',(request_id,)).fetchone():return request_id
        _trade_validate(c,a,b,terms)
        terms=dict(terms,contract_a=active_contract(c,terms['pro_a'])['id'],contract_b=active_contract(c,terms['pro_b'])['id'])
        c.execute("INSERT INTO market_trades VALUES (?,1,?,?,'proposed',1,?,?,NULL,NULL)",(request_id,a,b,a,date(c).absolute_day))
        c.execute('INSERT INTO market_trade_versions VALUES (?,1,?,?,?,NULL)',(request_id,a,date(c).absolute_day,dump(terms)));return request_id

def trade_reply(self,identity,agency,action,*,terms=None,expected_version):
    with self.write() as c:
        if c.execute('SELECT 1 FROM ai_trade_windows WHERE trade_id=?',(identity,)).fetchone():
            from .ai_trades import respond
            return respond(c,identity,agency,action,terms=terms,expected_revision=expected_version)
        t=c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone()
        if not t:raise MarketError('거래를 찾을 수 없습니다.')
        if t['status']=='completed':return 'completed'
        if t['status'] not in ('proposed','countered') or t['version']!=expected_version:raise MarketError('제안 상태·버전이 변경되었습니다. 다시 확인해 주세요.')
        if agency not in (t['agency_a'],t['agency_b']) or agency==t['proposer']:raise MarketError('현재 제안을 받은 기획사만 응답할 수 있습니다.')
        if action=='counter':
            if t['version']>=3:raise MarketError('협상 제안은 최대 3회입니다.')
            _trade_validate(c,t['agency_a'],t['agency_b'],terms,trade_id=identity)
            terms=dict(terms,contract_a=active_contract(c,terms['pro_a'])['id'],contract_b=active_contract(c,terms['pro_b'])['id'])
            c.execute("UPDATE market_trades SET version=version+1,proposer=?,status='countered' WHERE id=?",(agency,identity))
            c.execute('INSERT INTO market_trade_versions VALUES (?,?,?,?,?,NULL)',(identity,t['version']+1,agency,date(c).absolute_day,dump(terms)))
        elif action in ('accept','reject'):
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            if action=='accept' and player and agency!=player[0]:
                action=_evaluate_trade(c,identity,agency)['action']
            if action=='accept':
                current=json.loads(c.execute('SELECT terms_json FROM market_trade_versions WHERE trade_id=? AND version=?',(identity,t['version'])).fetchone()[0])
                _trade_validate(c,t['agency_a'],t['agency_b'],current,trade_id=identity)
            c.execute('UPDATE market_trade_versions SET response=? WHERE trade_id=? AND version=?',(action,identity,t['version']))
            c.execute('UPDATE market_trades SET status=? WHERE id=?',('accepted_pending' if action=='accept' else 'rejected',identity))
        else:raise MarketError('수락·거절·역제안을 선택해 주세요.')
        return c.execute('SELECT status FROM market_trades WHERE id=?',(identity,)).fetchone()[0]

def trades(self):
    with closing(self.database.connect()) as c:
        rows=[]
        for t in c.execute('SELECT * FROM market_trades ORDER BY created_day DESC,id'):
            w=c.execute('SELECT * FROM ai_trade_windows WHERE trade_id=?',(t['id'],)).fetchone()
            rows.append(dict(t,ai_window=dict(w) if w else None,versions=[dict(v) for v in c.execute('SELECT * FROM market_trade_versions WHERE trade_id=? ORDER BY version',(t['id'],))]))
        return tuple(rows)

def evaluate_trade(self,identity,agency):
    with self.write() as c:return _evaluate_trade(c,identity,agency)
def _evaluate_trade(c,identity,agency,*,terms=None,round_number=None):
    t=c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone()
    if not t or agency not in (t['agency_a'],t['agency_b']):raise MarketError('해당 거래 참여자가 아닙니다.')
    if terms is None:terms=json.loads(c.execute('SELECT terms_json FROM market_trade_versions WHERE trade_id=? AND version=?',(identity,t['version'])).fetchone()[0])
    from .trade_policy import evaluate
    _trade_validate(c,t['agency_a'],t['agency_b'],terms,trade_id=identity)
    return evaluate(c,t,agency,terms,public_people(c))

def ai_trade_reply(self,identity,agency):
    result=self.evaluate_trade(identity,agency)
    with closing(self.database.connect()) as c:
        t=c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone();terms=json.loads(c.execute('SELECT terms_json FROM market_trade_versions WHERE trade_id=? AND version=?',(identity,t['version'])).fetchone()[0])
    action=result['action']
    if action=='counter':
        # Ask the other side to close the public value gap, in won; no RNG.
        adjustment=max(10000,round_10000(int(round(max(0,result['give']*1.1-result['receive'])*1000000))))
        terms['cash']=terms.get('cash',0)+(adjustment if agency==t['agency_b'] else -adjustment)
        try:return self.trade_reply(identity,agency,'counter',terms=terms,expected_version=t['version'])
        except MarketError:action='reject'
    return self.trade_reply(identity,agency,action,expected_version=t['version'])


def _settle_auctions(c,day,seed_factory):
    for a in c.execute("SELECT * FROM market_auctions WHERE status='open' AND deadline<=? ORDER BY deadline,id",(day,)).fetchall():
        bids=c.execute('SELECT * FROM market_bids WHERE auction_id=? ORDER BY annual DESC,absolute_day,id',(a['id'],)).fetchall()
        latest={}
        for b in bids:
            if b['agency_id'] not in latest:latest[b['agency_id']]=b
        valid=[];rejected={}
        for b in latest.values():
            try:_slot(c,b['agency_id'],excluding_auction=a['id']);_budget(c,b['agency_id'],b['annual'],exclude_auction=a['id'])
            except ValueError as error:rejected[b['agency_id']]=str(error)
            else:valid.append(b)
        owner=_owned(c,a['person_id'])['agency_id']
        if owner is not None:valid=[];rejected['ownership']='다른 유효 계약이 이미 존재합니다.'
        seed=seed_factory();winner=None
        if valid:
            highest=max(b['annual'] for b in valid);tied=sorted([b for b in valid if b['annual']==highest],key=lambda b:b['agency_id'])
            original=next((b for b in tied if b['agency_id']==a['original_agency']),None)
            winner=original or random.Random(seed).choice(tied)
            contract=_new_contract(c,a['person_id'],winner['agency_id'],winner['annual'],winner['duration'],'pro')
            pending=not c.execute('SELECT 1 FROM squad_formations WHERE agency_id=?',(winner['agency_id'],)).fetchone()
            _move(c,a['person_id'],winner['agency_id'],'pro_pending' if pending else 'second_team','fa',contract,a['id'])
        c.execute('UPDATE market_auctions SET status=?,winner=?,seed=?,result_json=? WHERE id=?',
            ('completed' if winner else 'failed',winner['agency_id'] if winner else None,str(seed),dump(dict(rejected=rejected,tied_agencies=[b['agency_id'] for b in valid if winner and b['annual']==winner['annual']],policy='former_club_then_uniform_lottery')),a['id']))

def _release_remaining(c,plan):
    return c.execute('''SELECT COALESCE(SUM(outstanding_krw),0) FROM finance_debts WHERE id=? OR
        (kind='release_due' AND settlement_id IN (SELECT settlement_id FROM market_installments WHERE plan_id=?))''',(plan['debt_id'],plan['id'])).fetchone()[0]

def _installments(c,day):
    for p in c.execute("""SELECT * FROM market_release_plans p WHERE method='installments' AND paid_count<10 AND next_day<=?
        AND NOT EXISTS(SELECT 1 FROM finance_settlements WHERE id='market:release-prepay:'||p.id||':'||p.agency_id)
        ORDER BY next_day,id""",(day,)).fetchall():
        ordinal=p['paid_count']+1;regular=round_10000(p['total'],10);amount=p['total']-regular*9 if ordinal==10 else regular
        s=_settlement(c,p['agency_id'],f'{p["id"]}:{ordinal}');paid=min(cash(c,p['agency_id']),amount);unpaid=amount-paid
        if amount:
            c.execute('UPDATE finance_debts SET outstanding_krw=outstanding_krw-? WHERE id=?',(amount,p['debt_id']))
            if unpaid:c.execute("INSERT INTO finance_debts(game_id,settlement_id,agency_id,person_id,kind,original_krw,outstanding_krw) VALUES (1,?,?,?,'release_due',?,?)",(s['id'],p['agency_id'],p['person_id'],unpaid,unpaid))
            journal(c,s,'release_installment',amount,cash_delta=-paid,debt_delta=-paid,person=p['person_id'],description=f'확정 위약금 {ordinal}/10회 · 실제 지급 {paid:,}원')
        c.execute('INSERT INTO market_installments VALUES (?,?,?,?)',(p['id'],ordinal,s['id'],amount))
        c.execute('UPDATE market_release_plans SET paid_count=?,next_day=next_day+7 WHERE id=?',(ordinal,p['id']))

def _expire(c,day):
    for r in c.execute('''SELECT x.*,t.root_id,t.start_season,t.end_season FROM finance_contracts x
        JOIN market_terms t ON t.contract_id=x.id JOIN roster_memberships r ON r.person_id=x.person_id AND r.agency_id=x.agency_id
        WHERE x.end_day<=? AND t.end_season IS NOT NULL AND r.career_status IN ('pro_pending','first_team','second_team','trainee')''',(day,)).fetchall():
        if active_contract(c,r['person_id'],day):continue
        if c.execute("SELECT 1 FROM market_negotiations WHERE person_id=? AND purpose='renew' AND status='open'",(r['person_id'],)).fetchone():raise MarketError('미완료 재계약 협상이 있습니다. 수락·3회 실패·협상 포기를 확정한 뒤 시장 날짜를 진행해 주세요.')
        age=c.execute('SELECT age FROM idols WHERE person_id=?',(r['person_id'],)).fetchone()[0]
        _move(c,r['person_id'],None,'retired' if age>=33 else 'fa','expiry',r)

def process_market(c,day,*,run_ai=True):
    if not c.execute('SELECT 1 FROM market_runtime').fetchone():return
    if c.execute('SELECT 1 FROM market_days WHERE absolute_day=?',(day,)).fetchone():return
    sync_terms(c);_expire(c,day);_installments(c,day);_settle_auctions(c,day,lambda:secrets.randbits(128))
    for t in c.execute("SELECT * FROM market_trades WHERE status='accepted_pending' AND id NOT IN (SELECT trade_id FROM ai_trade_windows) ORDER BY created_day,id").fetchall():
        if day%7:break
        if day<t['created_day']-t['created_day']%7+7:continue
        try:
            c.execute('SAVEPOINT market_pending');_trade_execute(c,t);c.execute('RELEASE market_pending')
        except (ValueError,sqlite3.IntegrityError) as error:
            c.execute('ROLLBACK TO market_pending');c.execute('RELEASE market_pending')
            c.execute("UPDATE market_trades SET status='void',execution_json=? WHERE id=?",(dump(dict(error=str(error))),t['id']))
    if run_ai:
        ai_market_day(c,day)
        from .ai_trades import generate,generate_ai_pairs
        generate_ai_pairs(c)
        generate(c)
    c.execute('INSERT INTO market_days VALUES (1,?)',(day,))

def force_sale(self,agency,*,request_id):
    with self.write() as c:
        done=c.execute("SELECT * FROM market_history WHERE related_id=? AND kind='forced_sale'",(request_id,)).fetchone()
        if done:return dict(done)
        _safe_day(c)
        if debt(c,agency)<=0:raise MarketError('상환할 채무가 없습니다.')
        candidates=sorted([p for p in public_people(c,agency=agency) if p['career_status'] in PRO],key=lambda p:(-p['annual'],p['id']))
        for p in candidates:
            contract=dict(active_contract(c,p['id']));price=contract['annual_krw']//2
            player=c.execute('SELECT agency_id FROM player_settings').fetchone()
            for buyer, in c.execute('SELECT id FROM agencies WHERE id!=? AND id!=? ORDER BY id',(agency,player[0] if player else '')):
                try:_slot(c,buyer);FinanceService(None).validate_spend(buyer,price,connection=c);_budget(c,buyer,contract['annual_krw'])
                except MarketError:continue
                except ValueError:continue
                s=_settlement(c,buyer,request_id);journal(c,s,'forced_sale_payment',price,cash_delta=-price,person=p['id'],description='강제 매각 매입 · 계약 승계')
                s=_settlement(c,agency,request_id);income(c,s,'forced_sale_income',price)
                next_contract=_new_contract(c,p['id'],buyer,0,1,'pro',inherit=contract)
                _move(c,p['id'],buyer,'second_team','forced_sale',next_contract,request_id,cash_amount=price)
                return dict(person_id=p['id'],buyer=buyer,price=price)
        return dict(completed=False,reason='현금과 선수단 자리를 확보한 구매자가 없어 채무를 유지합니다.')

def abandon(self,negotiation,agency):
    with self.write() as c:
        n=c.execute('SELECT * FROM market_negotiations WHERE id=? AND agency_id=?',(negotiation,agency)).fetchone()
        if not n:raise MarketError('해당 기획사의 협상이 아닙니다.')
        if n['status']=='open':
            if n['purpose'] in ('founding','renew'):_entry_day(c,agency,n['purpose'])
            c.execute("UPDATE market_negotiations SET status='abandoned' WHERE id=?",(negotiation,))
            if n['purpose']=='founding':
                _move(c,n['person_id'],None,'fa','founding_contract_failed',related=negotiation)
                c.execute("UPDATE founding_contracts SET status='failed' WHERE person_id=?",(n['person_id'],))
        if n['purpose']=='draft':
            from .annual_draft import sync_session
            sync_session(c,date(c).season)

def ai_market_day(c,day):
    from .founding import staged
    if date(c).is_founding and staged(c):
        # No regular payroll, roster rotation or renewals during founding.
        # Existing public-value FA policy is used only on the two FA days.
        if date(c).weekday() not in (3,5):return
        player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
        for agency, in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player[0] if player else '',)).fetchall():
            for p in sorted(public_people(c,available=True),key=lambda p:(-p['average'] if p['average'] is not None else 0,p['id'])):
                if sum(r['career_status'] in PRO for r in roster(c,agency))>=16:break
                if p['age']<17:continue
                c.execute('SAVEPOINT founding_ai_fa')
                try:
                    class Bound(MarketService):
                        @contextmanager
                        def write(self):yield c
                    api=Bound(None);identity=api.start_negotiation(agency,p['id'],'fa')
                    api.offer(identity,(p['market']*110+99)//100//10000*10000,1,request_id=f'founding-fa:{day}:{agency}:{p["id"]}')
                    c.execute('RELEASE founding_ai_fa')
                except (ValueError,sqlite3.IntegrityError):
                    c.execute('ROLLBACK TO founding_ai_fa');c.execute('RELEASE founding_ai_fa')
        return
    """Daily decision worker uses exactly the public projection and facade APIs.
    It runs inside the date transaction through a connection-backed adapter.
    """
    d=GameDate(day)
    if d.is_maintenance or (d.is_preparation and not d.is_founding):
        from .maintenance_ai import run
        run(c);return
    if d.is_postseason or (d.is_regular and d.weekday()!=0):return
    class Bound(MarketService):
        @contextmanager
        def write(self):yield c
    api=Bound(None)
    own=c.execute('SELECT agency_id FROM player_settings').fetchone();player=own[0] if own else None
    agencies=[r[0] for r in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player or '',))]
    for agency in agencies:
        c.execute('SAVEPOINT market_ai')
        try:
            members=[p for p in public_people(c,agency=agency)]
            if d.is_offseason and d.week==1:
                for p in members:
                    if p['career_status'] not in PRO or p['end_season'] is None or p['end_season']>d.season:continue
                    n=api.start_negotiation(agency,p['id'],'renew')
                    row=c.execute('SELECT status FROM market_negotiations WHERE id=?',(n,)).fetchone()
                    if row[0]!='open':continue
                    previous=c.execute('SELECT annual FROM market_offers WHERE negotiation_id=? ORDER BY ordinal DESC LIMIT 1',(n,)).fetchone()
                    annual=raised_offer(previous[0]) if previous else p['market']
                    api.offer(n,annual,1,request_id=f'ai:{n}:{day}')
            # Valid renewal offers must survive a later optional trade/release
            # rejection. The encompassing date transaction still rolls back
            # everything on a real storage/advance failure.
            c.execute('RELEASE market_ai');c.execute('SAVEPOINT market_ai')
            if d.is_offseason and d.week==1 and d.weekday()==0:
                # Release only a clearly cheaper upgrade opportunity under a
                # finite contract; no invented probabilistic release policy.
                free=[p for p in public_people(c,available=True) if p['age']>=17]
                for p in members:
                    if p['career_status'] not in PRO or p['end_season'] is None or p['end_season']<=d.season:continue
                    upgrade=any(q['average']>p['average'] and q['market']<p['annual'] for q in free)
                    if upgrade and p['annual']>p['market'] and not debt(c,agency):
                        api.release(agency,p['id'],'immediate',request_id=f'ai:release:{agency}:{day}')
                        break
            if d.is_offseason and d.week==3:
                available=[p for p in public_people(c,available=True) if p['age']>=17]
                if sum(p['career_status'] in PRO for p in members)<16 and available:
                    team=[sum(p['skills'][i] for p in members)/max(1,len(members)) for i in range(8)]
                    best=max(available,key=lambda p:(player_value(p,team),p['id']))
                    top=c.execute("SELECT COALESCE(MAX(b.annual),0) FROM market_bids b JOIN market_auctions a ON a.id=b.auction_id WHERE a.person_id=? AND a.status='open'",(best['id'],)).fetchone()[0]
                    annual=max(best['market'],raised_offer(top) if top else 0)
                    if annual<=best['market']*1.1:api.bid(agency,best['id'],annual,1,request_id=f'ai:bid:{agency}:{best["id"]}:{day}')
                # Free trainees are requested by the common Monday batch.
                # No immediate AI signing and no total trainee cap.
            if d.is_maintenance or (d.is_preparation and not d.is_founding):
                trainees=[p for p in members if p['career_status']=='trainee' and p['age']>=17]
                if trainees:
                    target=max(trainees,key=lambda p:(p['average'],p['id']));n=api.start_negotiation(agency,target['id'],'debut')
                    if c.execute('SELECT status FROM market_negotiations WHERE id=?',(n,)).fetchone()[0]=='open':api.offer(n,30000000,1,request_id=f'ai:debut:{n}:{day}')
            if d.is_regular and d.weekday()==0 and _vacancies(c,agency)>0:
                free=[p for p in public_people(c,available=True) if p['age']>=17]
                if free:
                    target=max(free,key=lambda p:(p['average'],p['id']));n=api.start_negotiation(agency,target['id'],'fa')
                    if c.execute('SELECT status FROM market_negotiations WHERE id=?',(n,)).fetchone()[0]=='open':
                        previous=c.execute('SELECT annual FROM market_offers WHERE negotiation_id=? ORDER BY ordinal DESC LIMIT 1',(n,)).fetchone()
                        annual=raised_offer(previous[0]) if previous else target['market']
                        api.offer(n,annual,1,request_id=f'ai:regular-fa:{n}:{day}')
            for t in c.execute("SELECT * FROM market_trades WHERE status IN ('proposed','countered') AND id NOT IN (SELECT trade_id FROM ai_trade_windows) AND proposer!=? AND (agency_a=? OR agency_b=?)",(agency,agency,agency)).fetchall():
                result=_evaluate_trade(c,t['id'],agency)
                if result['action']=='counter':
                    terms=json.loads(c.execute('SELECT terms_json FROM market_trade_versions WHERE trade_id=? AND version=?',(t['id'],t['version'])).fetchone()[0]);adjustment=max(10000,round_10000(int(round(max(0,result['give']*1.1-result['receive'])*1000000))));terms['cash']=terms.get('cash',0)+(adjustment if agency==t['agency_b'] else -adjustment)
                    api.trade_reply(t['id'],agency,'counter',terms=terms,expected_version=t['version'])
                else:api.trade_reply(t['id'],agency,result['action'],expected_version=t['version'])
            if d.weekday()==0 and debt(c,agency)>0:api.force_sale(agency,request_id=f'ai:sale:{agency}:{day}')
            if d.weekday()==0:
                counts=Counter(p['career_status'] for p in public_people(c,agency=agency))
                while counts['first_team']<5:
                    options=[p for p in public_people(c,agency=agency) if p['career_status']=='second_team' and not p['injured'] and promotion_allowed(c,p['id'],day)]
                    if not options:break
                    selected=max(options,key=lambda p:(p['average'],p['id']))
                    c.execute('DELETE FROM squad_leaders WHERE person_id=?',(selected['id'],))
                    c.execute("UPDATE roster_memberships SET career_status='first_team' WHERE person_id=?",(selected['id'],))
                    c.execute('UPDATE squad_formations SET revision=revision+1 WHERE agency_id=?',(agency,))
                    counts['first_team']+=1
                sync_rosters(c,day,'ai_market_roster')
            c.execute('RELEASE market_ai')
        except (ValueError,sqlite3.IntegrityError):
            c.execute('ROLLBACK TO market_ai');c.execute('RELEASE market_ai')

def connect_draft_pick(self,agency,person,season,*,pick_id):
    """Adapter for the future annual draft engine, never called by the market UI."""
    with self.write() as c:
        d=_entry_day(c,agency,'draft')
        if season!=d.season:raise MarketError('현재 시즌의 확정 지명만 연결할 수 있습니다.')
        if c.execute('SELECT 1 FROM annual_sessions WHERE season=?',(season,)).fetchone():
            linked=c.execute("SELECT 1 FROM annual_turns WHERE season=? AND pick_id=? AND agency_id=? AND person_id=? AND status!='scheduled'",(season,pick_id,agency,person)).fetchone()
            if not linked:raise MarketError('통합 드래프트의 실제 지명 순서를 통해 계약을 연결해 주세요.')
        if c.execute('SELECT 1 FROM market_draft_rights WHERE id=?',(pick_id,)).fetchone():return
        p=_owned(c,person)
        if p['agency_id'] is not None or p['career_status']=='retired':raise MarketError('미소속 비은퇴 후보만 통합 드래프트에 연결할 수 있습니다.')
        if c.execute('SELECT COUNT(*) FROM market_draft_rights WHERE season=? AND agency_id=?',(season,agency)).fetchone()[0]>=3:raise MarketError('통합 드래프트는 기획사별 최대 3지명입니다.')
        c.execute('INSERT INTO market_draft_rights VALUES (?,1,?,?,?,0)',(pick_id,season,agency,person))
        c.execute('INSERT OR IGNORE INTO market_draft_outcomes VALUES (1,?,?,1)',(season,person))
        p=_owned(c,person)
        if 14<=p['age']<=16:
            _budget(c,agency,20000000);contract=_new_contract(c,person,agency,20000000,1,'draft_trainee');c.execute('INSERT INTO paid_draft_contracts VALUES (?,1,0)',(contract['id'],));_move(c,person,agency,'trainee','draft_trainee',contract,pick_id)
            c.execute('UPDATE market_draft_rights SET consumed=1 WHERE id=?',(pick_id,))

def record_draft_outcome(self,season,person,*,picked):
    with self.write() as c:
        d=date(c)
        if d.season!=season or d.is_regular or d.is_postseason or d.week<2:raise MarketError('해당 비시즌 드래프트 결과만 기록할 수 있습니다.')
        record_outcome(c,season,person,picked=picked)

def record_outcome(c,season,person,*,picked):
    c.execute('INSERT OR IGNORE INTO market_draft_outcomes VALUES (1,?,?,?)',(season,person,int(picked)))
    p=_owned(c,person)
    prior=c.execute('SELECT picked FROM market_draft_outcomes WHERE person_id=? AND season=?',(person,season-1)).fetchone()
    last=c.execute('SELECT unemployed_since FROM market_careers WHERE person_id=?',(person,)).fetchone()
    if not picked and prior and prior[0]==0 and p['agency_id'] is None and p['career_status']!='retired' and last and last[0] is not None and last[0]<=season-1:
        _move(c,person,None,'retired','two_drafts_unselected')

def release_quote(self,agency,person):
    with closing(self.database.connect()) as c:
        _owned(c,person,agency);contract=active_contract(c,person)
        if contract is None:raise MarketError('유효한 계약이 없습니다.')
        total=release_penalty(c,contract,date(c).absolute_day)
        return dict(total=total,installment=round_10000(total,10),cash=cash(c,agency),debt=debt(c,agency))


def promote_contracted_trainee(self,agency,person,*,expected_contract=None):
    with self.write() as c:
        _entry_day(c,agency,'debut');p=_owned(c,person,agency);contract=active_contract(c,person)
        if p['career_status']=='second_team' and contract and c.execute('SELECT 1 FROM paid_draft_contracts WHERE contract_id=? AND negotiated=1',(contract['id'],)).fetchone():return dict(contract)
        if p['career_status']!='trainee' or p['age']<17 or not contract or not c.execute('SELECT 1 FROM paid_draft_contracts WHERE contract_id=? AND negotiated=1',(contract['id'],)).fetchone():raise MarketError('협상한 계약을 보유한 17세 이상 연습생만 계약 승계 승격이 가능합니다.')
        if expected_contract is not None and contract['id']!=expected_contract:raise MarketError('계약이 변경되었습니다. 다시 확인해 주세요.')
        _slot(c,agency)
        _move(c,person,agency,'second_team','debut',dict(contract),'promotion:'+contract['id'])
        return dict(contract)

MarketService.promote_contracted_trainee=promote_contracted_trainee
