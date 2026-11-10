"""Public roster fit, season limits and durable one-shot trade decisions."""
import hashlib,json,random,secrets
from .market_rules import market_salary
from .game_clock import GameDate,current_game_date

V21_STATEMENTS=(
'''CREATE TABLE trade_rng(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,state_json TEXT NOT NULL)''',
'''CREATE TABLE trade_decisions(game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
 decision_key TEXT NOT NULL,probability REAL NOT NULL,roll REAL NOT NULL,accepted INTEGER NOT NULL,
 PRIMARY KEY(game_id,decision_key))''',
"CREATE INDEX trade_season_lookup ON market_trades(status,executed_day,agency_a,agency_b)",
)
ACTIVE=('proposed','countered','accepted_pending')
PRO=('first_team','second_team','pro_pending')

def acceptance_probability(ratio):
    r=ratio-1
    return max(0.,min(1.,.7*(1+(4 if r<0 else 1.5)*r)))

def decision(c,key,probability):
    row=c.execute('SELECT accepted FROM trade_decisions WHERE game_id=1 AND decision_key=?',(key,)).fetchone()
    if row:return bool(row[0])
    if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
    # Recheck after acquiring the writer lock (also covers independent callers).
    row=c.execute('SELECT accepted FROM trade_decisions WHERE game_id=1 AND decision_key=?',(key,)).fetchone()
    if row:return bool(row[0])
    row=c.execute('SELECT state_json FROM trade_rng WHERE game_id=1').fetchone()
    rng=random.Random()
    if row:
        def tuples(v):return tuple(map(tuples,v)) if isinstance(v,list) else v
        rng.setstate(tuples(json.loads(row[0])))
    else:rng.seed(secrets.randbits(256))
    roll=rng.random();accepted=roll<probability
    c.execute('INSERT OR REPLACE INTO trade_rng VALUES (1,?)',(json.dumps(rng.getstate()),))
    c.execute('INSERT INTO trade_decisions VALUES (1,?,?,?,?)',(key,probability,roll,int(accepted)))
    return accepted

def season_slots(c,agency,excluding=None):
    season=current_game_date(c).season;count=0
    for t in c.execute("SELECT id,status,executed_day FROM market_trades WHERE (agency_a=? OR agency_b=?) AND status IN ('completed','accepted_pending')",(agency,agency)):
        if t['id']==excluding:continue
        if t['status']=='accepted_pending' or (t['executed_day'] is not None and GameDate(t['executed_day']).season==season):count+=1
    return count

def validate_slots(c,a,b,excluding=None):
    for agency in (a,b):
        if season_slots(c,agency,excluding)>=2:raise ValueError('기획사당 시즌 트레이드는 최대 2회입니다. 예약된 거래도 포함합니다.')

def busy(c,agency):
    return c.execute("SELECT 1 FROM market_trades WHERE (agency_a=? OR agency_b=?) AND status IN ('proposed','countered','accepted_pending')",(agency,agency)).fetchone() is not None

def weekly_proposed(c,agency,day):
    return c.execute('SELECT 1 FROM market_trades WHERE agency_a=? AND created_day=?',(agency,day)).fetchone() is not None

def coverage(members):
    if not members:return [0.]*8
    result=[]
    for i in range(8):
        values=sorted((p['skills'][i] for p in members),reverse=True)
        result.append(.4*values[0]+.35*sum(values[:2])/2+.25*sum(values[:5])/5)
    return result

def quality(members):
    def score(group):
        values=coverage(group)
        return .65*sum(values)/8+.35*sum(sorted(values)[:2])/2
    first=[p for p in members if p['career_status']=='first_team']
    return .6*score(members)+.4*score(first)

def exchange(members,outgoing,incoming):
    remaining=[p for p in members if p['id']!=outgoing['id']]
    replacement=dict(incoming,career_status=outgoing['career_status'])
    before=quality(members);without=quality(remaining);after=quality(remaining+[replacement])
    # Unique specialists cost more to lose; redundant roles have a smaller loss.
    give=market_salary(outgoing['skills'],outgoing['age'])+max(0,before-without)*1500000
    receive=market_salary(incoming['skills'],incoming['age'])+max(0,after-without)*1500000
    return give,receive,after-before

def useful(members,outgoing,incoming):
    values=coverage(members);weak=min(range(8),key=lambda i:values[i])
    return (max(values)-min(values)>=8 and min(values)<75
        and incoming['skills'][weak]>=outgoing['skills'][weak]+8
        and exchange(members,outgoing,incoming)[2]>=.5)

def evaluate(c,trade,agency,terms,people):
    a=agency==trade['agency_a'];players={p['id']:p for p in people}
    own=terms['pro_a' if a else 'pro_b'];incoming=terms['pro_b' if a else 'pro_a']
    members=[p for p in people if p['agency_id']==agency and p['career_status'] in PRO]
    give,receive,gain=exchange(members,players[own],players[incoming])
    give+=sum(market_salary(players[p]['skills'],players[p]['age'])*.5 for p in terms.get('trainees_a' if a else 'trainees_b',()))
    receive+=sum(market_salary(players[p]['skills'],players[p]['age'])*.5 for p in terms.get('trainees_b' if a else 'trainees_a',()))
    payment=terms.get('cash',0)*(1 if a else -1)
    give+=max(0,payment)*.5;receive+=max(0,-payment)*.5
    ratio=receive/max(1,give);probability=acceptance_probability(ratio) if gain>=-.5 else 0.
    key='accept:'+trade['id']+':'+agency+':'+hashlib.sha256(json.dumps(terms,sort_keys=True).encode()).hexdigest()
    accepted=decision(c,key,probability) if gain>=-.5 else False
    return dict(ratio=ratio,probability=probability,action='accept' if accepted else 'reject',give=give,receive=receive,composition_gain=gain)
