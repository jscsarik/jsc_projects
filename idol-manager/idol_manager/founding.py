"""First-game-only seven-day preparation. Existing saves have no setup row."""
from contextlib import closing,contextmanager
from .game_clock import current_game_date
def enabled(c):return bool(c.execute("SELECT 1 FROM sqlite_master WHERE name='founding_setup'").fetchone() and c.execute('SELECT 1 FROM founding_setup WHERE game_id=1').fetchone())
def waiting(c):return bool(enabled(c) and c.execute("SELECT 1 FROM founding_setup WHERE game_id=1 AND status IN ('pending','active')").fetchone())

def staged(c):
    return bool(enabled(c) and c.execute('SELECT 1 FROM founding_setup WHERE game_id=1 AND protocol=2').fetchone())

def advance_reason(c):
    """New founding week has stage gates, not a Monday formation gate."""
    draft=c.execute('SELECT status FROM draft_state WHERE id=1').fetchone()
    if not draft or draft[0]!='completed':return '창단 월요일: 최초 16라운드 드래프트를 완료해 주세요.'
    d=current_game_date(c)
    if d.weekday()>=1:
        reason=contract_reason(c)
        if reason:return reason
    return ''

def stage_hint(d):
    if not d:return ''
    if d.is_founding:return (
        '창단 월요일: 최초 16라운드 드래프트를 완료해 주세요.',
        '1~3라운드 지명 선수 3명의 계약을 진행해 주세요. 선수별 최대 3회 제안할 수 있습니다.',
        '1차 연습생 계약 신청 · 최대 2명. 하루 진행 시 접수 마감, 목요일에 추첨합니다.',
        '1차 연습생 계약 신청 결과를 확인해 주세요. FA 입찰·직접 협상이 가능합니다.',
        '2차 연습생 계약 신청 · 최대 2명. 하루 진행 시 접수 마감, 토요일에 추첨합니다.',
        '2차 연습생 추첨 결과 및 FA 시장. 기존 2일 입찰 기한을 유지합니다.',
        '창단 준비가 종료되었습니다. 다음 주 월요일에 최종 선수단을 편성합니다.'
    )[d.weekday()]
    if d.absolute_day==7:return '정규 리그 개막 준비: 1군 5명과 2군 선수단을 편성하고 리더를 지정해 주세요.'
    if d.absolute_day==9:return '정규 리그 개막!'
    return ''
def contract_reason(c,agency=None):
    if not waiting(c):return ''
    where=' AND agency_id=?' if agency else ''
    if c.execute("SELECT 1 FROM founding_contracts WHERE status='pending'"+where,(agency,) if agency else ()).fetchone():return '창단 1~3라운드 계약 협상을 먼저 완료해 주세요. 실패한 계약의 프로 결원은 FA 직접 협상으로 보충합니다.'
    return ''
def ready_reason(c):
    reason=contract_reason(c)
    if reason:return reason
    day=current_game_date(c)
    for agency, in c.execute('SELECT id FROM agencies ORDER BY id'):
        counts=dict(c.execute('SELECT career_status,COUNT(*) FROM roster_memberships WHERE agency_id=? GROUP BY career_status',(agency,)))
        if sum(counts.get(k,0) for k in ('pro_pending','first_team','second_team'))!=16:return '모든 기획사의 프로 16명 계약과 결원 보충을 완료해야 합니다.'
        if counts.get('first_team',0)!=5 or counts.get('second_team',0)!=11:return '창단 준비 월요일에 모든 기획사의 1군 5명·2군 11명 편성을 완료해 주세요.'
        if c.execute('''SELECT COUNT(*) FROM squad_leaders l JOIN roster_memberships r
            ON r.person_id=l.person_id AND r.agency_id=l.agency_id AND r.career_status=l.squad WHERE l.agency_id=?''',(agency,)).fetchone()[0]!=2:return '창단 준비 월요일에 1군·2군 리더 지정을 모두 완료해 주세요.'
        if c.execute('''SELECT 1 FROM roster_memberships r WHERE r.agency_id=? AND r.career_status IN ('first_team','second_team')
            AND NOT EXISTS(SELECT 1 FROM finance_contracts x WHERE x.person_id=r.person_id AND x.agency_id=r.agency_id
            AND x.kind='pro' AND x.start_day<=? AND (x.end_day IS NULL OR x.end_day>?))''',(agency,day.absolute_day,day.absolute_day)).fetchone():return '소속 프로의 유효 계약을 확인해 주세요.'
    return ''
def prepare_ai(c,player,*,fill=True):
    from .market_service import MarketService,public_people,active_contract
    from .market_rules import raised_offer
    class Bound(MarketService):
        @contextmanager
        def write(self):yield c
    market=Bound(None)
    for agency, in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player,)).fetchall():
        for row in c.execute("SELECT negotiation_id,person_id FROM founding_contracts WHERE agency_id=? AND status='pending' ORDER BY person_id",(agency,)).fetchall():
            basis=next(p['market'] for p in public_people(c,agency=agency) if p['id']==row['person_id'])
            for attempt in range(3):
                if c.execute('SELECT status FROM market_negotiations WHERE id=?',(row['negotiation_id'],)).fetchone()[0]!='open':break
                previous=c.execute('SELECT annual FROM market_offers WHERE negotiation_id=? ORDER BY ordinal DESC LIMIT 1',(row['negotiation_id'],)).fetchone()
                market.offer(row['negotiation_id'],raised_offer(previous[0]) if previous else basis,1,request_id=f'founding-ai:{row["person_id"]}:{attempt}')
        while fill and c.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id=? AND career_status IN ('pro_pending','first_team','second_team')",(agency,)).fetchone()[0]<16:
            options=[p for p in public_people(c,available=True) if p['age']>=17 and not c.execute("SELECT 1 FROM market_negotiations WHERE person_id=? AND status='open'",(p['id'],)).fetchone()]
            if not options:raise ValueError('AI 창단 결원을 채울 FA 후보가 없습니다. 기존 지명과 계약을 보존하고 준비를 중단합니다.')
            target=min(options,key=lambda p:(p['market'],p['id']))
            identity=market.start_negotiation(agency,target['id'],'fa',context='founding-replacement')
            market.offer(identity,(target['market']*110+99)//100//10000*10000,1,request_id=f'founding-ai-fa:{agency}:{target["id"]}')
def start(c):
    row=c.execute('SELECT status FROM founding_setup WHERE game_id=1').fetchone()
    if not row or row[0]!='pending':return
    c.execute("UPDATE founding_setup SET status='active',prep_day=0 WHERE game_id=1")
    if staged(c):return
    start_contracts(c)

def start_contracts(c):
    from .market_service import _new_contract,_move
    rows=c.execute('SELECT k.person_id,t.agency_id,t.round_number FROM draft_picks k JOIN draft_turns t ON t.pick_number=k.pick_number ORDER BY k.pick_number').fetchall()
    for r in rows:
        if c.execute('SELECT 1 FROM finance_contracts WHERE person_id=?',(r['person_id'],)).fetchone() or c.execute('SELECT 1 FROM founding_contracts WHERE person_id=?',(r['person_id'],)).fetchone():continue
        if r['round_number']>3:
            contract=_new_contract(c,r['person_id'],r['agency_id'],30000000,1,'pro')
            _move(c,r['person_id'],r['agency_id'],'pro_pending','founding_auto_contract',contract)
        else:
            identity='founding:'+r['person_id']
            c.execute("INSERT INTO market_negotiations VALUES (?,1,?,?,'founding','open',?,'founding')",(identity,r['agency_id'],r['person_id'],current_game_date(c).absolute_day))
            c.execute("INSERT INTO founding_contracts VALUES (1,?,?,?,'pending',?)",(r['person_id'],r['agency_id'],r['round_number'],identity))
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if player:
        prepare_ai(c,player[0],fill=not staged(c))
        if not staged(c):
            from .squads import SquadService
            SquadService(None)._initialize_ai(c,player[0])

class FoundingService:
    def __init__(self,database):self.database=database
    def state(self):
        with closing(self.database.connect()) as c:
            row=c.execute('SELECT * FROM founding_setup WHERE game_id=1').fetchone()
            return dict(row) if row else None
