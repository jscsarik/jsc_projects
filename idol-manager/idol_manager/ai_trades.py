"""Weekly AI invitations, persisted chat, and next-Monday closing only."""
from contextlib import closing
import json,sqlite3
from .game_clock import current_game_date

def message(c,identity,sender,text):
    c.execute('INSERT INTO ai_trade_messages(trade_id,absolute_day,sender,message) VALUES (?,?,?,?)',
        (identity,current_game_date(c).absolute_day,sender,text))

def terms_of(c,t):
    return json.loads(c.execute('SELECT terms_json FROM market_trade_versions WHERE trade_id=? AND version=?',(t['id'],t['version'])).fetchone()[0])

def generate_ai_pairs(c):
    """One 15% search roll per free AI and Monday; only mutual roster gains."""
    from .market_service import public_people,PRO,_trade_validate,_evaluate_trade,active_contract
    from .trade_policy import busy,weekly_proposed,season_slots,decision,useful,exchange
    d=current_game_date(c)
    if not d or not d.is_regular or d.weekday()!=0:return
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if not player:return
    if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
    people=public_people(c)
    agencies=[r[0] for r in c.execute('SELECT agency_id FROM squad_formations WHERE agency_id!=? ORDER BY agency_id',(player[0],))]
    teams={a:[p for p in people if p['agency_id']==a and p['career_status'] in PRO] for a in agencies}
    for a in agencies:
        if busy(c,a) or weekly_proposed(c,a,d.absolute_day) or season_slots(c,a)>=2:continue
        if sum(p['career_status']=='first_team' for p in teams[a])!=5:continue
        if not decision(c,f'search:{d.absolute_day}:{a}',.15):continue
        # Recording the search even when no combination exists prevents rerolls.
        if c.execute('SELECT 1 FROM trade_decisions WHERE decision_key=?',('searched:'+str(d.absolute_day)+':'+a,)).fetchone():continue
        c.execute('INSERT INTO trade_decisions VALUES (1,?,0,0,0)',('searched:'+str(d.absolute_day)+':'+a,))
        options=[]
        for b in agencies:
            if b==a or busy(c,b) or season_slots(c,b)>=2:continue
            if sum(p['career_status']=='first_team' for p in teams[b])!=5:continue
            for pa in teams[a]:
                if pa['injured']:continue
                for pb in teams[b]:
                    if pb['injured'] or not useful(teams[a],pa,pb) or not useful(teams[b],pb,pa):continue
                    give,receive,ga=exchange(teams[a],pa,pb)
                    if receive<give:continue
                    gb=exchange(teams[b],pb,pa)[2]
                    options.append((ga+gb,b,pa['id'],pb['id']))
        if not options:continue
        _,b,pa,pb=max(options)
        identity=f'ai-pair:{d.absolute_day}:{a}:{b}'
        terms=dict(pro_a=pa,pro_b=pb,cash=0,trainees_a=[],trainees_b=[])
        try:_trade_validate(c,a,b,terms)
        except ValueError:continue
        terms.update(contract_a=active_contract(c,pa)['id'],contract_b=active_contract(c,pb)['id'])
        c.execute("INSERT INTO market_trades VALUES (?,1,?,?,'proposed',1,?,?,NULL,NULL)",(identity,a,b,a,d.absolute_day))
        c.execute('INSERT INTO market_trade_versions VALUES (?,1,?,?,?,NULL)',(identity,a,d.absolute_day,json.dumps(terms)))
        # Only the recipient rolls; a rejection ends this week's proposal.
        result=_evaluate_trade(c,identity,b,terms=terms)
        accepted=result['action']=='accept'
        c.execute('UPDATE market_trades SET status=? WHERE id=?',('accepted_pending' if accepted else 'rejected',identity))
        c.execute('UPDATE market_trade_versions SET response=? WHERE trade_id=? AND version=1',(result['action'],identity))
        c.execute('INSERT INTO ai_trade_windows(trade_id,deadline_day) VALUES (?,?)',(identity,d.absolute_day+7))


def generate(c):
    from .market_service import public_people,PRO,_trade_validate,active_contract
    from .trade_policy import busy,weekly_proposed,season_slots,useful,exchange
    d=current_game_date(c)
    if not d or not d.is_regular or d.weekday()!=0:return
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if not player or not c.execute('SELECT 1 FROM squad_formations WHERE agency_id=?',(player[0],)).fetchone():return
    if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
    player=player[0];people=public_people(c)
    targets=[p for p in people if p['agency_id']==player and p['career_status'] in PRO]
    for agency, in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player,)).fetchall():
        if not c.execute('SELECT 1 FROM squad_formations WHERE agency_id=?',(agency,)).fetchone():continue
        if c.execute('SELECT 1 FROM ai_trade_checks WHERE game_id=1 AND absolute_day=? AND agency_id=?',(d.absolute_day,agency)).fetchone():continue
        c.execute('INSERT INTO ai_trade_checks VALUES (1,?,?)',(d.absolute_day,agency))
        if busy(c,agency) or weekly_proposed(c,agency,d.absolute_day) or season_slots(c,agency)>=2 or season_slots(c,player)>=2:continue
        own=[p for p in people if p['agency_id']==agency and p['career_status'] in PRO]
        first=[p for p in own if p['career_status']=='first_team']
        spare=[p for p in own if p['career_status']=='second_team' and not p['injured']]
        if not first or not spare or not targets:continue
        team=[sum(p['skills'][i] for p in first)/len(first) for i in range(8)]
        weak=min(range(8),key=lambda i:team[i])
        if team[weak]>=75:continue
        options=[(exchange(own,p,q)[2],p['id'],q['id'],p,q) for p in spare for q in targets if useful(own,p,q)]
        if not options:continue
        _,_,_,outgoing,incoming=max(options,key=lambda x:x[:3])
        terms=dict(pro_a=outgoing['id'],pro_b=incoming['id'],cash=0,trainees_a=[],trainees_b=[])
        try:_trade_validate(c,agency,player,terms)
        except ValueError:continue
        terms.update(contract_a=active_contract(c,outgoing['id'])['id'],contract_b=active_contract(c,incoming['id'])['id'])
        identity=f'ai-weekly:{d.absolute_day}:{agency}:{player}'
        c.execute("INSERT INTO market_trades VALUES (?,1,?,?,'proposed',1,?,?,NULL,NULL)",(identity,agency,player,agency,d.absolute_day))
        c.execute('INSERT INTO market_trade_versions VALUES (?,1,?,?,?,NULL)',(identity,agency,d.absolute_day,json.dumps(terms)))
        c.execute('INSERT INTO ai_trade_windows(trade_id,deadline_day) VALUES (?,?)',(identity,d.absolute_day+7))
        message(c,identity,agency,'새로운 트레이드를 제안합니다. 다음 주 월요일 마감까지 협상할 수 있습니다.')

def respond(c,identity,agency,action,*,terms=None,expected_revision):
    from .market_service import MarketError,_trade_validate,_evaluate_trade,active_contract
    t=c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone()
    window=c.execute('SELECT * FROM ai_trade_windows WHERE trade_id=?',(identity,)).fetchone()
    if not t or not window or agency!=t['agency_b']:raise MarketError('플레이어에게 도착한 AI 제안이 아닙니다.')
    day=current_game_date(c).absolute_day
    if t['status'] not in ('proposed','countered') or not t['created_day']<=day<=window['deadline_day']:raise MarketError('진행 중인 협상 기간이 아닙니다.')
    if expected_revision!=window['revision']:raise MarketError('제안이 변경되었습니다. 채팅을 다시 확인해 주세요.')
    status=t['status']
    if action=='accept':
        _trade_validate(c,t['agency_a'],t['agency_b'],terms_of(c,t),trade_id=identity)
        status='accepted_pending';message(c,identity,agency,'제안을 수락했습니다. 다음 주 월요일 마감에 체결합니다.')
    elif action=='reject':status='rejected';message(c,identity,agency,'제안을 거절했습니다.')
    elif action=='counter':
        if window['counter_count']>=3:raise MarketError('역제안은 최대 3회입니다. 남아 있는 제안을 수락하거나 거절할 수 있습니다.')
        _trade_validate(c,t['agency_a'],t['agency_b'],terms,trade_id=identity)
        terms=dict(terms,contract_a=active_contract(c,terms['pro_a'])['id'],contract_b=active_contract(c,terms['pro_b'])['id'])
        count=window['counter_count']+1
        result=_evaluate_trade(c,identity,t['agency_a'],terms=terms,round_number=count)
        accepted=result['action']=='accept'
        history=json.loads(window['counter_history_json']);history.append(dict(ordinal=count,day=day,terms=terms,accepted=accepted))
        c.execute('UPDATE ai_trade_windows SET counter_count=?,counter_history_json=? WHERE trade_id=?',(count,json.dumps(history),identity))
        message(c,identity,agency,f'역제안 {count}/3회를 제출했습니다.')
        message(c,identity,t['agency_a'],'제안하신 조건을 수락하겠습니다.' if accepted else '해당 조건으로는 거래하기 어렵습니다. 기존 제안은 계속 유효합니다.')
        if accepted:
            status='accepted_pending'
            c.execute("INSERT INTO market_trade_versions VALUES (?,2,?,?,?,'accept')",(identity,agency,day,json.dumps(terms)))
            c.execute('UPDATE market_trades SET version=2 WHERE id=?',(identity,))
    else:raise MarketError('수락·거절·역제안 중 선택해 주세요.')
    c.execute('UPDATE market_trades SET status=? WHERE id=?',(status,identity))
    c.execute('UPDATE ai_trade_windows SET revision=revision+1 WHERE trade_id=?',(identity,))
    return status

def close_due(c):
    from .market_service import _trade_execute
    day=current_game_date(c)
    if not day or day.is_founding or day.weekday()!=0:return
    if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
    rows=c.execute("SELECT t.* FROM market_trades t JOIN ai_trade_windows w ON w.trade_id=t.id WHERE w.deadline_day<=? AND t.status IN ('proposed','countered','accepted_pending') ORDER BY w.deadline_day,t.id",(day.absolute_day,)).fetchall()
    for t in rows:
        if t['status']=='accepted_pending':
            c.execute('SAVEPOINT ai_trade_close')
            try:
                _trade_execute(c,t)
                if t['id'].startswith('ai-pair:'):
                    for agency in (t['agency_a'],t['agency_b']):
                        if c.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id=? AND career_status='first_team'",(agency,)).fetchone()[0]!=5:
                            raise ValueError('AI 간 거래 체결 후 1군은 정확히 5명이어야 합니다.')
                c.execute('RELEASE ai_trade_close')
                message(c,t['id'],t['agency_a'],'트레이드가 정상적으로 체결되었습니다.')
            except (ValueError,sqlite3.IntegrityError) as error:
                c.execute('ROLLBACK TO ai_trade_close');c.execute('RELEASE ai_trade_close')
                c.execute("UPDATE market_trades SET status='void',execution_json=? WHERE id=?",(json.dumps(dict(error=str(error))),t['id']))
                message(c,t['id'],t['agency_a'],'체결 실패: '+str(error))
        else:
            c.execute("UPDATE market_trades SET status='expired' WHERE id=?",(t['id'],))
            message(c,t['id'],t['agency_a'],'협상 기한이 만료되었습니다.')
        c.execute('UPDATE ai_trade_windows SET revision=revision+1 WHERE trade_id=?',(t['id'],))

class AITradeService:
    def __init__(self,database):self.database=database
    def inbox(self):
        with closing(self.database.connect()) as c:
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            if not player:return ()
            rows=[]
            for r in c.execute('SELECT t.*,w.* FROM market_trades t JOIN ai_trade_windows w ON w.trade_id=t.id WHERE t.agency_b=? ORDER BY t.created_day DESC,t.id',(player[0],)):
                value=dict(r);value['terms']=terms_of(c,r)
                value['messages']=[dict(m) for m in c.execute('SELECT * FROM ai_trade_messages WHERE trade_id=? ORDER BY id',(r['id'],))]
                value['unread']=any(m['id']>r['read_seq'] for m in value['messages']);rows.append(value)
            return tuple(rows)
    def respond(self,identity,agency,action,*,terms=None,expected_revision):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');return respond(c,identity,agency,action,terms=terms,expected_revision=expected_revision)
    def read(self,identity):
        with closing(self.database.connect()) as c,c:
            c.execute('UPDATE ai_trade_windows SET read_seq=COALESCE((SELECT MAX(id) FROM ai_trade_messages WHERE trade_id=?),0) WHERE trade_id=?',(identity,identity))
