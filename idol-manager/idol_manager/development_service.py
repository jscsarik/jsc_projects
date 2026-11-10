"""Transactional weekly development. Only this internal engine reads PA."""
from collections import Counter,defaultdict
from contextlib import closing
import json,random,secrets,sqlite3,uuid

from .config import SKILLS
from .game_clock import GameDate,current_game_date,DAYS_PER_SEASON
from .conditions import seed_for
from .development_rules import Development,ROLES,primary_role,phase,load_rules
from .health_rules import health_after_age


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)


def initialize_development(c):
    old_factory=c.row_factory;c.row_factory=sqlite3.Row
    try:
        day=current_game_date(c)
        if day is None or c.execute('SELECT 1 FROM development_runtime WHERE game_id=1').fetchone():return
        c.execute('INSERT INTO development_runtime VALUES (1,?,?,?)',(day.absolute_day,str(secrets.randbits(128)),encode(load_rules())))
        # Backfill only provable current-week roles. Do not invent unknown
        # pre-rollout history, perform past growth or modify any CA/PA/age.
        current=c.execute('''SELECT r.person_id,r.agency_id,r.career_status,c.history_known_since
            FROM roster_memberships r JOIN player_conditions c ON c.person_id=r.person_id''').fetchall()
        changes=defaultdict(list)
        for row in c.execute("SELECT person_id,absolute_day,details_json FROM condition_events WHERE kind='roster' ORDER BY rowid DESC"):
            changes[row['person_id']].append((row['absolute_day'],json.loads(row['details_json'])))
        for d in range(day.absolute_day-day.weekday(),day.absolute_day):
            for row in current:
                if d<row['history_known_since']:continue
                role=row['career_status']
                for changed,detail in changes[row['person_id']]:
                    if changed>d:role=detail.get('from',role)
                if role in ROLES:c.execute('INSERT OR IGNORE INTO development_days VALUES (1,?,?,?,?,0)',(d,row['person_id'],row['agency_id'],role))
    finally:c.row_factory=old_factory


def capture_day(c,day):
    c.execute('''INSERT OR IGNORE INTO development_days(game_id,absolute_day,person_id,agency_id,role,leader)
        SELECT 1,?,r.person_id,r.agency_id,r.career_status,
            CASE WHEN l.person_id IS NOT NULL THEN 1 ELSE 0 END
        FROM roster_memberships r JOIN idols i ON i.person_id=r.person_id LEFT JOIN squad_leaders l
        ON l.person_id=r.person_id AND l.agency_id=r.agency_id AND l.squad=r.career_status
        WHERE r.career_status IN ('first_team','second_team','trainee')''',(day,))


def activity(c,start,end):
    facts=defaultdict(lambda:dict(main_successes=[0]*8,basic_successes=[0]*8,attempts=[0]*8,games=set(),dates=set(),fatigue=False,injured=False))
    def add(person,day,game,phase_name,skill,success):
        if phase_name not in ('main','support'):return
        f=facts[person];i=SKILLS.index(skill);f['attempts'][i]+=1
        f['basic_successes'][i]+=int(success)
        if phase_name=='main':f['main_successes'][i]+=int(success)
        f['games'].add(game);f['dates'].add(day)
    for r in c.execute('''SELECT e.person_id,e.phase,e.skill,e.success,m.id,
        regular_day(m.season,m.week,m.weekday) AS day FROM match_events e
        JOIN scheduled_matches m ON m.id=e.match_id WHERE day BETWEEN ? AND ? AND e.phase IN ('main','support')''',(start,end)):
        add(r['person_id'],r['day'],'regular:'+r['id'],r['phase'],r['skill'],r['success'])
    for r in c.execute('''SELECT r.id,r.input_json,regular_day(e.season,e.week,6) AS day
        FROM special_rounds r JOIN special_events e ON e.id=r.event_id
        WHERE r.status='completed' AND day BETWEEN ? AND ?''',(start,end)):
        squads=json.loads(r['input_json'])['conditions']['squads']
        for e in c.execute('SELECT person_id,phase,skill,success FROM special_judgments WHERE round_id=?',(r['id'],)):
            if squads.get(e['person_id'])=='first_team':add(e['person_id'],r['day'],'special:'+r['id'],e['phase'],e['skill'],e['success'])
    for r in c.execute("SELECT id,absolute_day,events_json FROM final_contests WHERE kind='post' AND status='completed' AND absolute_day BETWEEN ? AND ?",(start,end)):
        for e in json.loads(r['events_json']):add(e['person_id'],r['absolute_day'],'post:'+r['id'],e['phase'],e['skill'],e['success'])
    dates=defaultdict(set)
    for person,day in c.execute('SELECT person_id,absolute_day FROM appearance_days WHERE absolute_day BETWEEN ? AND ?',(start-2,end)):dates[person].add(day)
    for person,days in dates.items():
        facts[person]['fatigue']=any(d>=start and d-1 in days and d-2 in days for d in days)
    for person, in c.execute("SELECT DISTINCT person_id FROM condition_events WHERE absolute_day BETWEEN ? AND ? AND occurred=1 AND kind IN ('match','first_rest','second')",(start,end)):
        facts[person]['injured']=True
    return facts


def _players(c):
    players={}
    for r in c.execute('''SELECT i.person_id,i.age,i.health,r.agency_id,r.career_status,a.skill,a.value,a.potential
        FROM idols i JOIN roster_memberships r ON r.person_id=i.person_id JOIN abilities a ON a.person_id=i.person_id ORDER BY i.person_id'''):
        p=players.setdefault(r['person_id'],dict(age=r['age'],health=r['health'],agency=r['agency_id'],role=r['career_status'],ca={},pa={}))
        p['ca'][r['skill']]=r['value'];p['pa'][r['skill']]=r['potential']
    for p in players.values():
        if set(p['ca'])!=set(SKILLS) or set(p['pa'])!=set(SKILLS):raise ValueError('현재 능력치·개별 성장 상한 기록이 불완전합니다.')
        p['ca']=tuple(p['ca'][s] for s in SKILLS);p['pa']=tuple(p['pa'][s] for s in SKILLS)
    return players


def _begin(c,day,kind,start,end,runtime):
    if c.execute('SELECT 1 FROM development_settlements WHERE absolute_day=? AND kind=?',(day,kind)).fetchone():return None
    identity=str(uuid.uuid4());seed=seed_for(runtime['seed'],f'{kind}:{day}')
    c.execute('INSERT INTO development_settlements VALUES (?,1,?,?,?,?,?,?)',
        (identity,day,kind,start,end,str(seed),json.loads(runtime['rules_json'])['version']+('|all-general-success-v2' if kind=='growth' else '')))
    return identity,seed


def _store(c,settlement,person,p,model,role,reasons,facts,bonus=False,age_after=None):
    after=tuple(model.values);age_after=p['age'] if age_after is None else age_after
    if age_after!=p['age']:
        health_after=health_after_age(p['health'],age_after-p['age'])
        facts=dict(facts,health_before=p['health'],health_after=health_after,health_change=health_after-p['health'])
    c.execute('INSERT INTO development_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (settlement,person,p['agency'],role,p['age'],age_after,encode(p['ca']),encode(after),encode([b-a for a,b in zip(p['ca'],after)]),int(bonus),encode(reasons),encode(facts)))
    c.executemany('INSERT INTO development_trials VALUES (?,?,?,?)',[(settlement,person,i,encode(trial)) for i,trial in enumerate(model.trials,1)])
    if after!=p['ca']:
        c.executemany('UPDATE abilities SET value=? WHERE person_id=? AND skill=?',[(value,person,s) for s,value in zip(SKILLS,after)])
        c.execute('UPDATE idols SET average=? WHERE person_id=?',(round(sum(after)/8,2),person))
    if age_after!=p['age']:c.execute('UPDATE idols SET age=?,health=? WHERE person_id=?',(age_after,health_after,person))


def settle_week(c,day,runtime,rules):
    start,end=day-7,day-1
    if start<0 or end<runtime['rollout_day'] or phase(GameDate(end)) not in rules['active_phases']:return
    existing=_begin(c,day,'growth',start,end,runtime)
    if existing is None:return
    settlement,seed=existing;players=_players(c);records=defaultdict(list)
    for r in c.execute('SELECT * FROM development_days WHERE absolute_day BETWEEN ? AND ? ORDER BY absolute_day',(start,end)):records[r['person_id']].append(dict(r))
    played=activity(c,start,end);models={};selected={};reasons={};public_facts={}
    from .training_service import focus_choices
    focused=focus_choices(c,start)
    for person,days in sorted(records.items()):
        role=primary_role(Counter(r['role'] for r in days))
        if role is None:continue
        p=players[person];model=Development(p['ca'],p['pa'],random.Random(seed_for(seed,person)))
        f=played[person];why=[]
        if role=='first_team' and f['injured']:why.append('injury')
        if role=='first_team' and f['fatigue']:why.append('three_consecutive_days')
        if len(days)<7:why.append('partial_role_history')
        agency=days[-1]['agency_id'];waiting=False
        if role=='first_team' and GameDate(start).is_postseason:
            waiting=not any(agency in json.loads(r[0]) for r in c.execute("SELECT agencies_json FROM final_contests WHERE kind='post' AND absolute_day BETWEEN ? AND ?",(start,end)))
            if waiting:why.append('postseason_waiting')
        if role=='first_team':
            if not f['games'] and not waiting:why.append('no_appearance')
            model.first(f['basic_successes'],f['attempts'],appeared=bool(f['games']),excluded=f['injured'] or f['fatigue'],waiting=waiting,rules=rules)
        elif role=='second_team':model.second(rules=rules,focus=focused.get(person))
        else:model.trainee(rules=rules)
        # Eligibility is frozen when a Tuesday second-team sheet is confirmed.
        if role!='second_team' and person in focused:model.focus_training(focused[person],rules=rules)
        models[person]=model;selected[person]=role;reasons[person]=why
        public_facts[person]=dict(role_days=dict(Counter(r['role'] for r in days)),covered_days=len(days),
            actual_games=len(f['games']),appearance_dates=sorted(f['dates']),main_successes=f['main_successes'],basic_successes=f['basic_successes'],success_ranking='all_general_v2',attempts=f['attempts'])
    # Weekly second-team leader bonus is separate from the one basic profile.
    sunday=c.execute("SELECT person_id,agency_id,leader FROM development_days WHERE absolute_day=? AND role='second_team' ORDER BY person_id",(end,)).fetchall()
    for leader in sunday:
        identity=leader['person_id']
        if not leader['leader'] or identity not in models:continue
        rng=random.Random(seed_for(seed,'second-leader:'+str(leader['agency_id'])))
        chance=models[identity].values[7]/(rules['weekly_basic']['leader_percent_divisor']*100)
        roll=rng.random();models[identity].trials.append(dict(kind='second_leader_roll',skill='leadership',probability=chance,roll=roll,success=roll<chance))
        if roll<chance:
            pool=[r['person_id'] for r in sunday if r['agency_id']==leader['agency_id'] and r['person_id'] in models]
            if pool:
                person=rng.choice(pool);model=models[person];eligible=[i for i in range(8) if model.values[i]<model.potentials[i]]
                if eligible:model.change(rng.choice(eligible),1,'second_leader')
    for person,model in models.items():
        model.additional(rules=rules)
        f=played[person]
        _store(c,settlement,person,players[person],model,selected[person],reasons[person],public_facts[person],
            bonus=selected[person]=='first_team' and bool(f['games']) and not(f['injured'] or f['fatigue']))


def settle_aging(c,day,runtime,rules):
    if day<rules['aging_anchor_day'] or (day-rules['aging_anchor_day'])%rules['aging_interval_days'] or phase(GameDate(day)) not in rules['active_phases']:return
    existing=_begin(c,day,'aging',day-rules['aging_interval_days'],day-1,runtime)
    if existing is None:return
    settlement,seed=existing
    for person,p in _players(c).items():
        model=Development(p['ca'],p['pa'],random.Random(seed_for(seed,person)));model.aging(p['age'],rules=rules)
        _store(c,settlement,person,p,model,p['role'],[],dict(cycle_day=day))


def settle_birthday(c,day,runtime,rules):
    date=GameDate(day)
    if date.day_in_season not in (91,182):return
    milestone=12 if date.day_in_season==91 else 24
    if c.execute('SELECT 1 FROM age_milestones WHERE game_id=1 AND season=? AND regular_week=?',(date.season,milestone)).fetchone():return
    from .coach_schema import initialize_age_policy
    initialize_age_policy(c)
    adopted=c.execute('SELECT rollout_day FROM age_policy WHERE game_id=1').fetchone()[0]
    if day<=adopted:return
    existing=_begin(c,day,'birthday',day,day,runtime)
    if existing is None:return
    settlement,seed=existing
    c.execute('INSERT INTO age_milestones VALUES (1,?,?,?)',(date.season,milestone,day))
    for person,p in _players(c).items():
        model=Development(p['ca'],p['pa'],random.Random(seed_for(seed,person)))
        _store(c,settlement,person,p,model,p['role'],[],dict(season=date.season,regular_week=milestone,age_policy='regular-halves-ended'),age_after=min(100,p['age']+1))


def apply_monday(c,day):
    if day%7:raise ValueError('성장·노화 정산은 월요일에만 가능합니다.')
    runtime=c.execute('SELECT * FROM development_runtime WHERE game_id=1').fetchone()
    if runtime is None or day<=runtime['rollout_day']:return
    rules=json.loads(runtime['rules_json'])
    settle_birthday(c,day,runtime,rules);settle_week(c,day,runtime,rules);settle_aging(c,day,runtime,rules)


def advance_development(c,day,tomorrow):
    capture_day(c,day)
    if tomorrow%7==0:apply_monday(c,tomorrow)


class DevelopmentService:
    def __init__(self,database):self.database=database

    def settle_current(self):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');day=current_game_date(c)
            if day is None:raise ValueError('저장된 게임 날짜가 없습니다.')
            apply_monday(c,day.absolute_day)

    def periods(self):
        with closing(self.database.connect()) as c:return tuple(dict(r) for r in c.execute("SELECT id,absolute_day,kind,period_start,period_end FROM development_settlements ORDER BY absolute_day DESC,CASE kind WHEN 'growth' THEN 0 WHEN 'birthday' THEN 1 ELSE 2 END"))

    def history(self,settlement=None,*,agency=None,changed_only=False):
        # Unseen/unpicked people also age internally, but their exact CA must
        # never leak through annual/aging history before agency registration.
        where=['r.agency_id IS NOT NULL'];args=[]
        if settlement:where.append('r.settlement_id=?');args.append(settlement)
        if agency:where.append('r.agency_id=?');args.append(agency)
        query='''SELECT r.settlement_id,r.person_id,p.name,p.photo_path,r.agency_id,r.role,r.age_before,r.age_after,
            r.ca_before_json,r.ca_after_json,r.deltas_json,r.bonus_applied,r.reasons_json,r.facts_json,s.absolute_day,s.kind
            FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id JOIN people p ON p.id=r.person_id'''
        if where:query+=' WHERE '+' AND '.join(where)
        query+=' ORDER BY s.absolute_day DESC,s.kind,p.name,r.person_id'
        with closing(self.database.connect()) as c:rows=[dict(r) for r in c.execute(query,args)]
        if changed_only:rows=[r for r in rows if r['age_before']!=r['age_after'] or any(json.loads(r['deltas_json'])) or json.loads(r['reasons_json'])]
        return tuple(rows)
