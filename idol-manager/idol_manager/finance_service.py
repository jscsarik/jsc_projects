from .game_clock import regular_day
"""Forward-only integer accounting. Mutations share the calendar's transaction.

Reads never settle. Income repays the oldest obligations first. Cash is stored
only in agencies.funds_krw; debt is separate, never a negative bank balance.
"""
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path
import json,sqlite3
from .game_clock import GameDate,current_game_date,DAYS_PER_SEASON
from .finance_policy import discretionary_budget

PRO=('pro_pending','first_team','second_team')
class FinanceError(ValueError):pass

def load_rules():
    rules=json.loads((Path(__file__).resolve().parents[1]/'config/finance.json').read_text(encoding='utf-8-sig'))
    for key in ('sponsor_krw','season_bonus_krw','trainee_weekly_krw','second_weekly_krw','focus_weekly_krw','first_contract_annual_krw'):
        if type(rules.get(key)) is not int or rules[key]<0:raise FinanceError(f'재정 설정 {key}: 0 이상의 원 단위 정수가 필요합니다.')
    if rules['pay_weeks']!=[4,8,12,16,20,24]:raise FinanceError('정기 급여는 정규 4·8·12·16·20·24주에만 정산합니다.')
    return rules
def encode(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)
def round_10000(numerator,denominator=1):
    return ((numerator+denominator*5000)//(denominator*10000))*10000

def salary_parts(annual,cycle,first_weeks,second_weeks):
    regular=round_10000(annual,6)
    base=max(0,annual-5*regular) if cycle==6 else min(regular,max(0,annual-(cycle-1)*regular))
    # Each adjustment is recorded independently; neither is cash income.
    bonus=round_10000(base,10) if first_weeks>=3 else 0
    reduction=round_10000(base,10) if second_weeks>=3 else 0
    return base,bonus,reduction,base+bonus-reduction

def cash(c,agency):
    row=c.execute('SELECT funds_krw FROM agencies WHERE id=?',(agency,)).fetchone()
    if row is None:raise FinanceError('존재하지 않는 기획사입니다.')
    return row[0]
def debt(c,agency):
    return c.execute('SELECT COALESCE(SUM(outstanding_krw),0) FROM finance_debts WHERE agency_id=?',(agency,)).fetchone()[0]

def begin(c,agency,day,kind,*,season=None,week=None):
    date=GameDate(day);season=date.season if season is None else season;week=date.week if week is None else week
    key=f'{agency}:{season}:{week}:{kind}'
    if c.execute('SELECT 1 FROM finance_settlements WHERE id=?',(key,)).fetchone():return None
    c.execute('INSERT INTO finance_settlements VALUES (?,1,?,?,?,?,?)',(key,agency,season,week,day,kind))
    return dict(id=key,agency=agency,season=season,week=week,day=day)

def journal(c,s,kind,amount,*,cash_delta=0,debt_delta=0,person=None,description=''):
    previous=cash(c,s['agency']);after=previous+cash_delta
    if after<0:raise FinanceError('현금 잔액은 음수가 될 수 없습니다.')
    if cash_delta:c.execute('UPDATE agencies SET funds_krw=? WHERE id=?',(after,s['agency']))
    c.execute('''INSERT INTO finance_ledger(game_id,settlement_id,agency_id,season,week,absolute_day,kind,amount,
        cash_delta,debt_delta,cash_before,cash_after,person_id,description) VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (s['id'],s['agency'],s['season'],s['week'],s['day'],kind,amount,cash_delta,debt_delta,previous,after,person,description))

def income(c,s,kind,amount):
    journal(c,s,kind,amount,cash_delta=amount,description='확정 수입 · 기존 채무 우선 상환')
    repay(c,s)

def repay(c,s):
    for d in c.execute("SELECT * FROM finance_debts WHERE agency_id=? AND outstanding_krw>0 AND kind!='release_scheduled' ORDER BY id",(s['agency'],)).fetchall():
        paid=min(cash(c,s['agency']),d['outstanding_krw'])
        if not paid:break
        c.execute('UPDATE finance_debts SET outstanding_krw=outstanding_krw-? WHERE id=?',(paid,d['id']))
        if d['payroll_id']:c.execute('UPDATE finance_payroll SET paid_krw=paid_krw+? WHERE id=?',(paid,d['payroll_id']))
        journal(c,s,'debt_repayment',paid,cash_delta=-paid,debt_delta=-paid,person=d['person_id'],description=f'채무 #{d["id"]} 상환 · {d["kind"]}')

def obligation(c,s,kind,amount,*,person=None,payroll=None):
    paid=min(cash(c,s['agency']),amount);unpaid=amount-paid
    if paid:journal(c,s,kind,paid,cash_delta=-paid,person=person,description='실제 현금 지급')
    if unpaid:
        c.execute('''INSERT INTO finance_debts(game_id,settlement_id,agency_id,person_id,payroll_id,kind,original_krw,outstanding_krw)
            VALUES (1,?,?,?,?,?,?,?)''',(s['id'],s['agency'],person,payroll,kind,unpaid,unpaid))
        journal(c,s,'unpaid_salary' if payroll else 'unpaid_operating',unpaid,debt_delta=unpaid,person=person,description=kind+' 지급 의무 잔액')
    return paid,unpaid

def ensure_pro_contracts(c,day,rules):
    # There was no pre-v12 salary store. The master specifies first pro salary
    # of 30m; seed only missing pro contracts, effective now, never backdated.
    for r in c.execute("SELECT person_id,agency_id FROM roster_memberships WHERE career_status IN ('pro_pending','first_team','second_team') ORDER BY person_id").fetchall():
        from .founding import waiting
        if waiting(c):continue
        if not c.execute('SELECT 1 FROM finance_contracts WHERE person_id=? AND (end_day IS NULL OR end_day>?)',(r[0],day)).fetchone():
            c.execute('INSERT INTO finance_contracts VALUES (?,1,?,?,?,?,?,NULL,?)',
                (f'initial:{r[0]}:{day}',r[0],r[1],'pro',rules['first_contract_annual_krw'],day,'master_first_pro_30m_forward_only'))
    for r in c.execute("SELECT person_id,agency_id FROM roster_memberships WHERE career_status='trainee'").fetchall():
        if c.execute('SELECT 1 FROM finance_contracts WHERE person_id=? AND (end_day IS NULL OR end_day>?)',(r[0],day)).fetchone():continue
        drafted=c.execute('SELECT 1 FROM draft_picks WHERE person_id=?',(r[0],)).fetchone() is not None
        c.execute('INSERT INTO finance_contracts VALUES (?,1,?,?,?,?,?,NULL,?)',
            (f'trainee:{r[0]}:{day}',r[0],r[1],'draft_trainee' if drafted else 'free_trainee',10000000 if drafted else 0,day,'master_trainee_pay_timing_unresolved'))

def initialize_finance(c,*,new_game=False):
    previous=c.row_factory;c.row_factory=sqlite3.Row
    try:
        day=current_game_date(c)
        if day is None or c.execute('SELECT 1 FROM finance_runtime WHERE game_id=1').fetchone():return
        closed=[r[0] for r in c.execute("SELECT season FROM season_finals WHERE status IN ('completed','legacy_closed')")]
        rules=load_rules()
        c.execute('INSERT INTO finance_runtime VALUES (1,?,?,?)',(day.absolute_day,encode(closed),encode(rules)))
        for agency, in c.execute('SELECT id FROM agencies ORDER BY id').fetchall():
            s=begin(c,agency,day.absolute_day,'opening')
            journal(c,s,'initial_funds' if new_game else 'opening_balance',cash(c,agency),description='기존 현금을 기초 잔액으로 등록 · 추가 지급 없음')
        ensure_pro_contracts(c,day.absolute_day,rules)
    finally:c.row_factory=previous

def role_week(days,priority):
    counts=Counter(days)
    return min(counts,key=lambda role:(-counts[role],priority.index(role) if role in priority else 99)) if counts else None

def payroll_activity(c,person,agency,start,end,rules):
    roles=defaultdict(list)
    for r in c.execute('SELECT absolute_day,role FROM development_days WHERE person_id=? AND agency_id=? AND absolute_day BETWEEN ? AND ?',(person,agency,start,end)):
        roles[(r[0]-start)//7].append(r[1])
    second=sum(role_week(v,rules['role_tie_priority'])=='second_team' for v in roles.values())
    if rules['second_week_policy']=='any_day':second=sum('second_team' in v for v in roles.values())
    # Actual recorded first-team appearances, not registration or phantom forfeits.
    first=set()
    for day, in c.execute('''SELECT DISTINCT regular_day(m.season,m.week,m.weekday) AS day
        FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id
        WHERE p.person_id=? AND p.agency_id=? AND day BETWEEN ? AND ?''',(person,agency,start,end)):
        first.add((day-start)//7)
    for r in c.execute('''SELECT r.id,r.input_json,regular_day(e.season,e.week,6) AS day
        FROM special_rounds r JOIN special_events e ON e.id=r.event_id
        WHERE r.status='completed' AND day BETWEEN ? AND ?''',(start,end)):
        data=json.loads(r['input_json'])
        if data.get('conditions',{}).get('squads',{}).get(person)!='first_team':continue
        if c.execute('SELECT 1 FROM special_player_stats WHERE round_id=? AND person_id=? AND agency_id=?',(r['id'],person,agency)).fetchone():first.add((r['day']-start)//7)
    return len(first),second,dict(first_weeks=sorted(first),role_days={str(k):dict(Counter(v)) for k,v in roles.items()},known_days=sum(map(len,roles.values())))

def settle_payroll(c,s,runtime,rules):
    cycle=s['week']//4;start=regular_day(s['season'],s['week']-3);end=s['day']
    # Never turn an upgrade into a backdated pay run, even when the old
    # growth history happens to cover previous weeks.
    partial_rollout=start<runtime['rollout_day']
    if partial_rollout:
        journal(c,s,'payroll_not_backfilled',0,description='도입 전 기존 급여 소급 없음 · 신규 시장 계약의 확인 가능한 미래 구간만 정산')
    contracts=c.execute('''SELECT * FROM finance_contracts WHERE agency_id=? AND (kind='pro' OR id IN (SELECT contract_id FROM paid_draft_contracts)) AND start_day<?
        AND (end_day IS NULL OR end_day>?) AND (end_day IS NULL OR end_day>start_day)
        ORDER BY person_id,start_day,id''',(s['agency'],end+1,start)).fetchall()
    if partial_rollout:contracts=[r for r in contracts if r['source']=='market19' and r['start_day']>=runtime['rollout_day']]
    unpaid_total=0
    for contract in contracts:
        first,second,facts=payroll_activity(c,contract['person_id'],s['agency'],start,end,rules)
        from .market_payroll import allocated_base
        base,covered_days=allocated_base(c,contract,s['season'],cycle,start,end)
        bonus=round_10000(base,10) if first>=3 else 0
        reduction=round_10000(base,10) if second>=3 else 0
        due=base+bonus-reduction
        facts.update(contract_days=covered_days,allocation='effective_days_over_28_v19')
        identity=f'{contract["id"]}:{s["season"]}:{cycle}'
        c.execute('INSERT INTO finance_payroll VALUES (?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (identity,s['id'],contract['id'],contract['person_id'],s['agency'],s['season'],cycle,contract['annual_krw'],base,first,second,bonus,reduction,due,0,encode(facts)))
        journal(c,s,'salary_base',base,person=contract['person_id'],description=f'{cycle}/6회 기본 급여 의무')
        if bonus:journal(c,s,'first_bonus',bonus,person=contract['person_id'],description=f'실제 1군 활동 {first}주 +10%')
        if reduction:journal(c,s,'second_reduction',-reduction,person=contract['person_id'],description=f'2군 최다 소속 {second}주 -10% · 수입 아님')
        paid,unpaid=obligation(c,s,'salary_payment',due,person=contract['person_id'],payroll=identity)
        c.execute('UPDATE finance_payroll SET paid_krw=? WHERE id=?',(paid,identity));unpaid_total+=unpaid
    if unpaid_total:
        c.execute('INSERT INTO finance_points VALUES (?,1,?,?,-2,?)',(s['id'],s['season'],s['agency'],f'{cycle}회 급여 미지급 {unpaid_total:,}원'))

def settle_week(c,end):
    runtime=c.execute('SELECT * FROM finance_runtime WHERE game_id=1').fetchone()
    if runtime is None:return
    date=GameDate(end);start=end-6
    if date.weekday()!=6 or not date.is_regular or start<runtime['rollout_day']:return
    rules=json.loads(runtime['rules_json']);ensure_pro_contracts(c,start,rules)
    for agency, in c.execute('SELECT id FROM agencies ORDER BY id').fetchall():
        s=begin(c,agency,end,'weekly')
        if s is None:continue
        income(c,s,'weekly_sponsor',rules['sponsor_krw'])
        groups=defaultdict(set)
        for person,role in c.execute("SELECT DISTINCT person_id,role FROM development_days WHERE agency_id=? AND absolute_day BETWEEN ? AND ? AND role IN ('second_team','trainee')",(agency,start,end)):
            groups[role].add(person)
        # Per-person per-week, never a daily repeat; actual managed days only.
        for role,key in (('trainee','trainee_weekly_krw'),('second_team','second_weekly_krw')):
            for person in sorted(groups[role]):obligation(c,s,'trainee_care' if role=='trainee' else 'second_training',rules[key],person=person)
        if date.week in rules['pay_weeks']:settle_payroll(c,s,runtime,rules)

def close_season(c,season,day):
    runtime=c.execute('SELECT * FROM finance_runtime WHERE game_id=1').fetchone()
    if runtime is None or season in json.loads(runtime['closed_seasons_json']) or day<runtime['rollout_day']:return
    final=c.execute('SELECT status FROM season_finals WHERE season=?',(season,)).fetchone()
    if not final or final[0]!='completed':return
    rules=json.loads(runtime['rules_json'])
    for agency, in c.execute('SELECT id FROM agencies ORDER BY id').fetchall():
        s=begin(c,agency,day,'bonus',season=season,week=27)
        if s:income(c,s,'season_bonus',rules['season_bonus_krw'])

def advance_finance(c,day,tomorrow):
    runtime=c.execute('SELECT * FROM finance_runtime WHERE game_id=1').fetchone()
    if not runtime:return
    ensure_pro_contracts(c,day,json.loads(runtime['rules_json']))
    if GameDate(day).weekday()==6:settle_week(c,day)
    if GameDate(tomorrow).day_in_season==203:close_season(c,GameDate(day).season,day)

class FinanceService:
    def __init__(self,database):self.database=database
    def ledger(self,agency,*,season=None,person=None):
        where=['agency_id=?'];args=[agency]
        if season is not None:where.append('season=?');args.append(season)
        if person:where.append('person_id=?');args.append(person)
        with closing(self.database.connect()) as c:return tuple(dict(r) for r in c.execute('SELECT * FROM finance_ledger WHERE '+' AND '.join(where)+' ORDER BY id DESC',args))
    def payroll(self,agency=None,*,person=None):
        sql='''SELECT x.*,p.name,p.photo_path,r.career_status FROM finance_payroll x JOIN people p ON p.id=x.person_id
            LEFT JOIN roster_memberships r ON r.person_id=x.person_id WHERE 1=1''';args=[]
        if agency:sql+=' AND x.agency_id=?';args.append(agency)
        if person:sql+=' AND x.person_id=?';args.append(person)
        with closing(self.database.connect()) as c:return tuple(dict(r) for r in c.execute(sql+' ORDER BY x.season DESC,x.cycle DESC,p.name',args))
    def contracts(self,agency=None,*,person=None):
        where=[];args=[]
        if agency:where.append('x.agency_id=?');args.append(agency)
        if person:where.append('x.person_id=?');args.append(person)
        with closing(self.database.connect()) as c:
            return tuple(dict(r) for r in c.execute('''SELECT x.*,p.name,p.photo_path,r.career_status FROM finance_contracts x
                JOIN people p ON p.id=x.person_id LEFT JOIN roster_memberships r ON r.person_id=x.person_id'''+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY p.name,x.start_day DESC',args))
    def dashboard(self,agency):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN');day=current_game_date(c);now=day.absolute_day if day else 0;date=day or GameDate(0)
            balance=cash(c,agency);owed=debt(c,agency);runtime=c.execute('SELECT * FROM finance_runtime WHERE game_id=1').fetchone()
            rules=json.loads(runtime['rules_json']) if runtime else load_rules()
            entries=[dict(r) for r in c.execute('SELECT * FROM finance_ledger WHERE agency_id=? AND season=? ORDER BY id',(agency,date.season))]
            def totals(rows):return sum(max(0,r['cash_delta']) for r in rows),sum(max(0,-r['cash_delta']) for r in rows)
            season_in,season_out=totals(entries);week_in,week_out=totals([r for r in entries if now-now%7<=r['absolute_day']<=now])
            contract_rows=c.execute("SELECT id,annual_krw,kind,start_day,end_day FROM finance_contracts WHERE agency_id=? AND start_day<=? AND (end_day IS NULL OR end_day>?)",(agency,now,now)).fetchall()
            paid={r[0] for r in c.execute('SELECT contract_id FROM paid_draft_contracts')}
            annual=sum(r['annual_krw'] for r in contract_rows if r['kind']=='pro' or r['id'] in paid);unresolved=sum(r['annual_krw'] for r in contract_rows if r['kind']=='draft_trainee' and r['id'] not in paid)
            roster=Counter(r[0] for r in c.execute('SELECT career_status FROM roster_memberships WHERE agency_id=?',(agency,)))
            weekly=roster['second_team']*rules['second_weekly_krw']+roster['trainee']*rules['trainee_weekly_krw']
            rollout=runtime['rollout_day'] if runtime else now
            from .market_payroll import projected_salary
            pay_season=date.season+1 if date.is_offseason else date.season
            current_regular_week=date.week if date.is_regular else 1
            next_week=next((w for w in rules['pay_weeks'] if w>=current_regular_week and regular_day(pay_season,w-3)>=rollout and not c.execute("SELECT 1 FROM finance_settlements WHERE agency_id=? AND season=? AND week=? AND kind='weekly'",(agency,pay_season,w)).fetchone()),None)
            cycle=next_week//4 if next_week else 1
            next_pay=projected_salary(c,agency,pay_season,next_week) if next_week else 0
            forecast=[];projected=balance-owed
            forecast_start=now-now%7
            if c.execute("SELECT 1 FROM finance_settlements WHERE agency_id=? AND season=? AND week=? AND kind='weekly'",(agency,date.season,date.week)).fetchone():forecast_start+=7
            for offset in range(4):
                future=GameDate(forecast_start+offset*7);sponsor=rules['sponsor_krw'] if future.is_regular and future.absolute_day>=rollout else 0;cost=weekly if future.is_regular and future.absolute_day>=rollout else 0
                pay=projected_salary(c,agency,future.season,future.week) if future.is_regular and future.week in rules['pay_weeks'] else 0
                if c.execute("SELECT 1 FROM finance_settlements WHERE agency_id=? AND season=? AND week=? AND kind='weekly'",(agency,future.season,future.week)).fetchone():sponsor=cost=pay=0
                projected+=sponsor-cost-pay;forecast.append(dict(date=str(future),income=sponsor,operating=cost,payroll=pay,net=projected))
            remaining=[w for w in range(1,25) if (date.is_regular and w>=date.week) and regular_day(date.season,w)>=rollout and not c.execute("SELECT 1 FROM finance_settlements WHERE agency_id=? AND season=? AND week=? AND kind='weekly'",(agency,date.season,w)).fetchone()]
            unpaid_cycles=[w for w in remaining if w in rules['pay_weeks'] and regular_day(date.season,w-3)>=rollout]
            remaining_salary=sum(projected_salary(c,agency,date.season,w) for w in unpaid_cycles)
            bonus_pending=bool(runtime and date.season not in json.loads(runtime['closed_seasons_json']) and not c.execute("SELECT 1 FROM finance_settlements WHERE agency_id=? AND season=? AND kind='bonus'",(agency,date.season)).fetchone())
            end_projection=balance-owed+len(remaining)*(rules['sponsor_krw']-weekly)-remaining_salary+(rules['season_bonus_krw'] if bonus_pending else 0)
            return dict(agency_id=agency,date=str(date),cash=balance,debt=owed,net=balance-owed,week_income=week_in,week_expense=week_out,
                season_income=season_in,season_expense=season_out,annual_payroll=annual,weekly_cost=weekly,next_pay_week=next_week,next_pay_season=pay_season,next_payroll=next_pay,
                forecast=forecast,end_projection=end_projection,ledger=entries,rollout_day=runtime['rollout_day'] if runtime else None,
                trainee_salary_unresolved=unresolved,forecast_notice='현재 소속·기본 계약 유지 가정. 보너스/감액·향후 계약 변동은 제외. 도입 전 회차는 소급 정산하지 않음.')
    def validate_spend(self,agency,amount,*,connection=None):
        if type(amount) is not int or amount<0:raise FinanceError('지출 금액은 0 이상의 원 단위 정수여야 합니다.')
        if connection is None:
            with closing(self.database.connect()) as c:return self.validate_spend(agency,amount,connection=c)
        if debt(connection,agency):raise FinanceError('채무가 있어 신규 계약·영입·선택적 훈련을 승인할 수 없습니다.')
        if cash(connection,agency)<amount:raise FinanceError('현금이 부족합니다. 지급 의무와 예상 운영비를 확인해 주세요.')
        return True
    def budget(self,agency,style='balanced'):
        d=self.dashboard(agency);return discretionary_budget(d['cash'],d['debt'],d['next_payroll'],d['weekly_cost'],style)
    def sale_candidates(self,agency):
        with closing(self.database.connect()) as c:
            day=current_game_date(c);now=day.absolute_day if day else 0
            if debt(c,agency)<=0:return ()
            rows=c.execute("""SELECT x.person_id,p.name,x.annual_krw FROM finance_contracts x JOIN people p ON p.id=x.person_id
                JOIN roster_memberships r ON r.person_id=x.person_id WHERE x.agency_id=? AND r.agency_id=x.agency_id
                AND r.career_status IN ('pro_pending','first_team','second_team') AND x.kind='pro' AND x.start_day<=?
                AND (x.end_day IS NULL OR x.end_day>?) ORDER BY x.annual_krw DESC,x.person_id""",(agency,now,now)).fetchall()
            result=[]
            for row in rows:
                price=row['annual_krw']//2;buyers=[]
                for other, in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(agency,)):
                    counts=Counter(r[0] for r in c.execute('SELECT career_status FROM roster_memberships WHERE agency_id=?',(other,)))
                    if not debt(c,other) and cash(c,other)>=price and sum(counts[k] for k in PRO)<16 and (counts['first_team']<5 or counts['second_team']<11):buyers.append(other)
                result.append(dict(person_id=row['person_id'],name=row['name'],annual_krw=row['annual_krw'],price=price,buyers=buyers,
                    executable=bool(buyers and now%7==0),reason='선수 시장에서 월요일 강제 매각 가능 · 계약 승계/현금/채무를 동시 처리' if buyers and now%7==0 else '구매자 자금·자리 또는 월요일 실행 조건 미충족 · 채무 유지'))
            return tuple(result)
