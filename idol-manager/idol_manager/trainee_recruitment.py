"""Monday application sheets and one atomic, equally weighted lottery."""
from contextlib import closing
import json,random,secrets,sqlite3
from .game_clock import current_game_date
from .draft import BlindCandidate
class RecruitmentError(ValueError):pass

def initialize_rng(c,seed=None):
    if c.execute('SELECT 1 FROM game WHERE id=1').fetchone() and not c.execute('SELECT 1 FROM trainee_rng WHERE game_id=1').fetchone():
        rng=random.Random(secrets.randbits(256) if seed is None else seed)
        c.execute('INSERT INTO trainee_rng VALUES (1,?)',(json.dumps(rng.getstate()),))
def tuples(value):return tuple(map(tuples,value)) if isinstance(value,list) else value
def candidates(c):
    return tuple(BlindCandidate(**dict(r)) for r in c.execute('''SELECT p.id,p.name,p.photo_path,i.age FROM idols i
        JOIN people p ON p.id=i.person_id JOIN roster_memberships r ON r.person_id=i.person_id
        WHERE i.status='candidate' AND i.age>=14 AND r.agency_id IS NULL AND r.career_status IN ('unassigned','fa')
        AND (EXISTS(SELECT 1 FROM initial_draft_undrafted u WHERE u.person_id=i.person_id)
          OR EXISTS(SELECT 1 FROM market_draft_outcomes o WHERE o.person_id=i.person_id AND o.picked=0))
        AND NOT EXISTS(SELECT 1 FROM professional_history h WHERE h.person_id=i.person_id)
        AND NOT EXISTS(SELECT 1 FROM market_careers h WHERE h.person_id=i.person_id AND h.debut_season IS NOT NULL)
        AND NOT EXISTS(SELECT 1 FROM finance_contracts x WHERE x.person_id=i.person_id AND x.kind='pro')
        AND NOT EXISTS(SELECT 1 FROM market_auctions a WHERE a.person_id=i.person_id AND a.status='open')
        AND NOT EXISTS(SELECT 1 FROM market_negotiations n WHERE n.person_id=i.person_id AND n.status='open')
        AND NOT EXISTS(SELECT 1 FROM market_draft_rights d WHERE d.person_id=i.person_id AND d.consumed=0)
        ORDER BY p.id'''))
def current_monday(c):
    d=current_game_date(c)
    info=round_info(c)
    if d is None or d.absolute_day!=info['application_day']:raise RecruitmentError('연습생 신청은 창단 수·금요일 또는 일반 월요일에만 가능합니다.')
    draft=c.execute('SELECT status FROM draft_state WHERE id=1').fetchone()
    if not draft or draft[0]!='completed':raise RecruitmentError('최초 드래프트를 완료한 뒤 연습생을 신청해 주세요.')
    return info['key']

def round_info(c):
    d=current_game_date(c)
    from .founding import staged
    if d and d.is_founding and staged(c):
        second=d.weekday()>=4
        return dict(key=-14 if second else -21,application_day=4 if second else 2,draw_day=5 if second else 3,number=2 if second else 1)
    day=d.absolute_day-d.weekday() if d else 0
    return dict(key=day,application_day=day,draw_day=day,number=1)

def ensure_round(c,info):
    c.execute('INSERT OR IGNORE INTO trainee_rounds(game_id,round_key,application_day,draw_day,round_number) VALUES (1,?,?,?,?)',
        (info['key'],info['application_day'],info['draw_day'],info['number']))
def sheet(c,agency,day=None):
    d=current_game_date(c);info=round_info(c);day=info['key'] if day is None else day
    meta=c.execute('SELECT * FROM trainee_rounds WHERE game_id=1 AND round_key=?',(day,)).fetchone()
    if meta:info=dict(key=day,application_day=meta['application_day'],draw_day=meta['draw_day'],number=meta['round_number'])
    submitted=bool(meta and meta['submitted'])
    batch=c.execute('SELECT status FROM trainee_weeks WHERE game_id=1 AND absolute_day=?',(day,)).fetchone()
    row=c.execute('SELECT revision,confirmed FROM trainee_sheets WHERE game_id=1 AND absolute_day=? AND agency_id=?',(day,agency)).fetchone()
    targets=[dict(r) for r in c.execute('''SELECT a.person_id,p.name,a.status FROM trainee_applications a JOIN people p ON p.id=a.person_id
        WHERE a.game_id=1 AND a.absolute_day=? AND a.agency_id=? ORDER BY a.slot''',(day,agency))]
    results=[]
    if batch and batch[0]=='finalized':
        results=[dict(r,applicants=json.loads(r['applicants_json'])) for r in c.execute('SELECT * FROM trainee_results WHERE game_id=1 AND absolute_day=? ORDER BY person_id',(day,))]
    closed=bool(batch and batch[0]=='finalized')
    return dict(day=day,revision=row[0] if row else 0,confirmed=bool(row and row[1]),closed=closed,count=len(targets),limit=2,targets=targets,results=results,
        submitted=submitted,application_day=info['application_day'],draw_day=info['draw_day'],round_number=info['number'],
        can_apply=bool(d and d.absolute_day==info['application_day'] and not closed and not submitted))
def replace(c,agency,people,*,expected_revision=None):
    day=current_monday(c);people=tuple(people)
    if len(people)>2 or len(set(people))!=len(people):raise RecruitmentError('매주 서로 다른 후보 최대 2명까지 신청할 수 있습니다.')
    if not c.execute('SELECT 1 FROM agencies WHERE id=?',(agency,)).fetchone():raise RecruitmentError('존재하지 않는 기획사입니다.')
    prior=sheet(c,agency,day)
    if prior['closed'] or prior['submitted']:raise RecruitmentError('이미 신청 마감된 회차입니다. 신청 변경·재추첨할 수 없습니다.')
    if expected_revision is not None and expected_revision!=prior['revision']:raise RecruitmentError('신청 목록이 다른 창에서 변경되었습니다. 다시 확인해 주세요.')
    eligible={p.id for p in candidates(c)}
    if not set(people)<=eligible:raise RecruitmentError('소속·은퇴·프로 경력 또는 진행 중인 계약 때문에 신청할 수 없는 후보가 있습니다.')
    initialize_rng(c)
    ensure_round(c,round_info(c))
    c.execute("INSERT OR IGNORE INTO trainee_weeks(game_id,absolute_day,status) VALUES (1,?,'open')",(day,))
    c.execute('INSERT OR IGNORE INTO trainee_sheets(game_id,absolute_day,agency_id) VALUES (1,?,?)',(day,agency))
    c.execute('DELETE FROM trainee_applications WHERE game_id=1 AND absolute_day=? AND agency_id=?',(day,agency))
    c.executemany('INSERT INTO trainee_applications(game_id,absolute_day,agency_id,slot,person_id) VALUES (1,?,?,?,?)',[(day,agency,i,p) for i,p in enumerate(people)])
    c.execute('UPDATE trainee_sheets SET revision=revision+1,confirmed=1 WHERE game_id=1 AND absolute_day=? AND agency_id=?',(day,agency))
    return sheet(c,agency,day)
def request_one(c,agency,person,request_id):
    cached=c.execute('SELECT * FROM trainee_submission_keys WHERE id=?',(request_id,)).fetchone()
    if cached:
        if cached['agency_id']!=agency or cached['person_id']!=person:raise RecruitmentError('동일 요청 ID로 다른 후보를 신청할 수 없습니다.')
        return sheet(c,agency,cached['absolute_day'])
    prior=sheet(c,agency);ids=[r['person_id'] for r in prior['targets']]
    result=replace(c,agency,ids if person in ids else [*ids,person],expected_revision=prior['revision'])
    c.execute('INSERT INTO trainee_submission_keys VALUES (?,1,?,?,?)',(request_id,result['day'],agency,person))
    return result
def submit(c,day,*,expected_player_revision=None,policy=None):
    from .trainee_policy import choose_applications
    if day!=current_monday(c):raise RecruitmentError('현재 신청 회차만 마감할 수 있습니다.')
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if not player:raise RecruitmentError('플레이어 기획사를 선택해 주세요.')
    prior=sheet(c,player[0],day)
    if prior['closed'] or prior['submitted']:return prior['results']
    if expected_player_revision is not None and prior['revision']!=expected_player_revision:raise RecruitmentError('마감 확인 후 신청 목록이 변경되었습니다. 다시 확인해 주세요.')
    initialize_rng(c);raw=c.execute('SELECT state_json FROM trainee_rng WHERE game_id=1').fetchone()[0]
    rng=random.Random();rng.setstate(tuples(json.loads(raw)))
    available=candidates(c);eligible={p.id for p in available}
    if policy is None:
        from .recruitment_philosophy import ensure
        from .recruitment_policy import public_view,applications
        from .market_service import public_people
        philosophies=ensure(c)
        public_candidates=[public_view(p) for p in public_people(c,person_ids=[p.id for p in available])]
    c.execute("INSERT OR IGNORE INTO trainee_weeks(game_id,absolute_day,status) VALUES (1,?,'open')",(day,))
    if not c.execute('SELECT 1 FROM trainee_sheets WHERE game_id=1 AND absolute_day=? AND agency_id=?',(day,player[0])).fetchone():replace(c,player[0],())
    for agency, in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player[0],)).fetchall():
        if not c.execute('SELECT 1 FROM trainee_sheets WHERE game_id=1 AND absolute_day=? AND agency_id=?',(day,agency)).fetchone():
            if policy is not None:choices=policy(available,rng)
            else:
                own=[public_view(p) for p in public_people(c,agency=agency)]
                choices=applications(public_candidates,own,philosophies[agency])
            replace(c,agency,choices)
    c.execute('UPDATE trainee_rounds SET submitted=1 WHERE game_id=1 AND round_key=?',(day,))
    c.execute('UPDATE trainee_rng SET state_json=? WHERE game_id=1',(json.dumps(rng.getstate()),))
    return []

def finalize(c,day,*,expected_player_revision=None,policy=None):
    from .market_service import _new_contract,_move,_budget
    info=round_info(c);d=current_game_date(c)
    if day!=info['key'] or not d or d.absolute_day!=info['draw_day']:raise RecruitmentError('해당 회차 추첨일에만 결과를 확정할 수 있습니다.')
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if not player:raise RecruitmentError('플레이어 기획사를 선택해 주세요.')
    prior=sheet(c,player[0],day)
    if prior['closed']:return prior['results']
    if not prior['submitted']:
        submit(c,day,expected_player_revision=expected_player_revision,policy=policy)
    initialize_rng(c);raw=c.execute('SELECT state_json FROM trainee_rng WHERE game_id=1').fetchone()[0]
    rng=random.Random();rng.setstate(tuples(json.loads(raw)))
    eligible={p.id for p in candidates(c)}
    groups={}
    for p,a in c.execute('SELECT person_id,agency_id FROM trainee_applications WHERE game_id=1 AND absolute_day=? ORDER BY person_id,agency_id',(day,)):
        groups.setdefault(p,[]).append(a)
    for person,applicants in groups.items():
        winner=None;index=None;status='ineligible'
        if person in eligible:
            index=rng.randrange(len(applicants)) if len(applicants)>1 else 0;winner=applicants[index]
            c.execute('SAVEPOINT trainee_award')
            try:
                _budget(c,winner,0);contract=_new_contract(c,person,winner,0,1,'free_trainee')
                _move(c,person,winner,'trainee','trainee',contract,f'weekly-trainee:{day}:{person}')
                c.execute('RELEASE trainee_award');status='signed'
            except ValueError:
                c.execute('ROLLBACK TO trainee_award');c.execute('RELEASE trainee_award');status='contract_failed'
        c.execute('INSERT INTO trainee_results VALUES (1,?,?,?,?,?,?)',(day,person,winner,status,json.dumps(applicants),index))
        for agency in applicants:
            outcome='won' if status=='signed' and agency==winner else 'lost' if status=='signed' else status
            c.execute('UPDATE trainee_applications SET status=? WHERE game_id=1 AND absolute_day=? AND agency_id=? AND person_id=?',(outcome,day,agency,person))
    after=json.dumps(rng.getstate())
    c.execute("UPDATE trainee_weeks SET status='finalized',rng_before=?,rng_after=? WHERE game_id=1 AND absolute_day=?",(raw,after,day))
    c.execute('UPDATE trainee_rng SET state_json=? WHERE game_id=1',(after,))
    return sheet(c,player[0],day)['results']

class RecruitmentService:
    def __init__(self,database):self.database=database
    def candidates(self):
        with closing(self.database.connect()) as c:return candidates(c)
    def state(self,agency,day=None):
        with closing(self.database.connect()) as c:
            result=sheet(c,agency,day)
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            if not result['closed'] and (not player or agency!=player[0]):
                result.update(targets=[],count=0,revision=0,confirmed=False)
            return result
    def apply(self,agency,people,*,expected_revision=None):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');return replace(c,agency,people,expected_revision=expected_revision)
    def results(self,agency,day):return self.state(agency,day)['results']
