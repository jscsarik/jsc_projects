"""25차 bounded real-engine diagnostics. Never opens the user's save writable."""
from pathlib import Path
from contextlib import closing,contextmanager
from collections import Counter,defaultdict
from unittest.mock import patch
import argparse,csv,hashlib,json,random,secrets,sqlite3,sys,time,traceback,uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from idol_manager.service import GameService
from idol_manager.config import load_settings,SKILLS
from idol_manager.draft_estimates import public_prospects
from idol_manager.conditions import public_condition,promotion_allowed
from idol_manager.annual_policy import choose,offer_amount
from idol_manager.market_service import _slot,_budget


def dump(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf8')
    for attempt in range(6):
        try:tmp.replace(path);return
        except PermissionError:
            if attempt==5:raise
            time.sleep(.05*(attempt+1))
def csvfile(path,rows):
    columns=list(dict.fromkeys(k for r in rows for k in r)) or ['status']
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,columns);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list,tuple)) else v for k,v in row.items()})
def state(rng):return list(rng.getstate())
def restore(rng,value):rng.setstate((value[0],tuple(value[1]),value[2]))
def ratio(k,n):return k/n if n else None


@contextmanager
def seeded_entropy(entropy,identities):
    # Process-local test adapter only. Production entropy/functions are restored.
    with patch.object(secrets,'randbits',entropy.getrandbits),patch.object(secrets,'token_bytes',lambda n=32:entropy.getrandbits(n*8).to_bytes(n,'big')),patch.object(uuid,'uuid4',lambda:uuid.UUID(int=identities.getrandbits(128),version=4)),patch.object(random,'SystemRandom',lambda:entropy):yield


@contextmanager
def public_policy(database):
    original=database.connect
    def connect():
        c=original()
        def allow(action,table,column,*_):
            if action==sqlite3.SQLITE_READ and (table=='annual_secrets' or column in ('potential','archetype')):return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        c.set_authorizer(allow);return c
    with patch.object(database,'connect',side_effect=connect):yield


def schedule_audit(c,season):
    rows=c.execute('SELECT * FROM scheduled_matches WHERE season=?',(season,)).fetchall()
    parts=c.execute('SELECT * FROM match_participants WHERE season=?',(season,)).fetchall()
    teams=Counter(p['agency_id'] for p in parts);pair_members=defaultdict(list)
    for p in parts:pair_members[p['match_id']].append(p['agency_id'])
    pairs=Counter(tuple(sorted(v)) for v in pair_members.values());contents=Counter(r['content_id'] for r in rows)
    days=Counter((r['week'],r['weekday']) for r in rows)
    special=c.execute('SELECT week,weekday FROM special_events WHERE season=?',(season,)).fetchall()
    collisions=c.execute('''SELECT season,week,weekday,day_order,agency_id,COUNT(*) n FROM match_participants
        WHERE season=? GROUP BY season,week,weekday,day_order,agency_id HAVING n>1''',(season,)).fetchall()
    checks=dict(matches_585=len(rows)==585,ten_agencies=len(teams)==10,each_117=all(v==117 for v in teams.values()),
        pairs_13=len(pairs)==45 and all(v==13 for v in pairs.values()),contents_30=len(contents)==30,
        content_distribution=Counter(contents.values())==Counter({19:15,20:15}),doubleheaders_3=Counter(days.values())==Counter({5:111,10:3}),
        specials_6=len(special)==6,special_dates_separate=all((r[0],r[1]) not in days for r in special),
        no_time_conflicts=not collisions,late_award_content=all(r['week']>=21 for r in rows if r['content_name']=='연말시상식'))
    return dict(season=season,status='PASS' if all(checks.values()) else 'FAIL',**checks)


def quick_audit(c):
    queries={
        'ca_pa_bounds':'SELECT COUNT(*) FROM abilities WHERE value<0 OR value>100 OR value>potential',
        'health_bounds':'SELECT COUNT(*) FROM idols WHERE health<0 OR health>90',
        'negative_cash':'SELECT COUNT(*) FROM agencies WHERE funds_krw<0',
        'pro_capacity':"SELECT COUNT(*) FROM (SELECT agency_id, SUM(career_status IN('first_team','second_team','pro_pending')) pro,SUM(career_status='first_team') f,SUM(career_status='second_team') s FROM roster_memberships WHERE agency_id IS NOT NULL GROUP BY agency_id HAVING pro>16 OR f>5 OR s>11)",
        'overlapping_contracts':'''SELECT COUNT(*) FROM finance_contracts a JOIN finance_contracts b ON a.person_id=b.person_id AND a.id<b.id AND a.start_day<COALESCE(b.end_day,9223372036854775807) AND b.start_day<COALESCE(a.end_day,9223372036854775807)''',
        'bad_match_totals':"SELECT COUNT(*) FROM match_player_stats WHERE base_attempts!=60 OR main_attempts!=30 OR support_attempts!=30 OR base_successes+base_failures!=60",
        'bad_team_result':'''SELECT COUNT(*) FROM match_team_stats t JOIN match_results r ON r.match_id=t.match_id WHERE t.points!=CASE WHEN t.agency_id=r.winner_id THEN 1 ELSE 0 END OR t.outcome!=CASE WHEN t.agency_id=r.winner_id THEN 'win' ELSE 'loss' END''',
        'duplicate_growth':'SELECT COUNT(*) FROM (SELECT absolute_day,kind,COUNT(*) n FROM development_settlements GROUP BY absolute_day,kind HAVING n>1)',
        'bad_birthday_health':'''SELECT COUNT(*) FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE s.kind='birthday' AND (r.age_after!=r.age_before+1 OR json_extract(r.facts_json,'$.health_after')!=MAX(0,json_extract(r.facts_json,'$.health_before')-1))''',
        'young_aging':'''SELECT COUNT(*) FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE s.kind='aging' AND age_before<28 AND EXISTS(SELECT 1 FROM json_each(r.deltas_json) WHERE value!=0)''',
        'retired_draft':'''SELECT COUNT(*) FROM annual_turns t JOIN market_history h ON h.person_id=t.person_id AND h.kind LIKE '%retir%' AND h.absolute_day<t.picked_day'''}
    result={k:c.execute(q).fetchone()[0] for k,q in queries.items()};result['foreign_keys']=len(c.execute('PRAGMA foreign_key_check').fetchall())
    return result


class Simulation:
    def __init__(self,args):
        self.args=args;self.output=args.output.resolve();allowed=(ROOT/'diagnostics').resolve()
        self.resource_root=Path(getattr(args,'resource_root',ROOT)).resolve()
        if self.resource_root!=ROOT and (not self.resource_root.is_relative_to(allowed) or not (self.resource_root/'qa_world.json').exists()):raise ValueError('가상 공급은 표식이 있는 diagnostics 전용 리소스만 허용합니다.')
        if not self.output.is_relative_to(allowed) or self.output==allowed:raise ValueError('출력은 프로젝트 diagnostics 아래 전용 하위 폴더여야 합니다.')
        self.output.mkdir(parents=True,exist_ok=True);self.path=self.output/'simulation.sqlite3'
        self.marker=self.output/'run_manifest.json';self.checkpoint=self.output/'checkpoint.json'
        if self.path.resolve()==(ROOT/'data/idol_manager.sqlite3').resolve():raise ValueError('실제 세이브 실행 금지')
        if self.path.exists() and not args.resume:raise ValueError('이미 있는 테스트 DB입니다. 새 폴더 또는 --resume을 사용하세요.')
        if args.resume and not self.marker.exists():raise ValueError('시뮬레이션 전용 표식이 없습니다.')
        self.started=time.monotonic();self.deadline=self.started+args.budget_seconds
        self.entropy=random.Random(args.seed);self.identities=random.Random(args.seed+1);self.calendar_rng=random.Random(args.seed+2)
        self.issues=[];self.seasons=[];self.initial={};self.ends={};self.policy_day=None;self.audit=[];self.metrics=[];self.lifecycle=[];self.current_action='setup'
        if args.resume:
            saved=json.loads(self.checkpoint.read_text(encoding='utf8'));self.args.seed=saved['seed']
            for rng,key in ((self.entropy,'entropy'),(self.identities,'identities'),(self.calendar_rng,'calendar_rng')):restore(rng,saved[key])
            for key in ('issues','seasons','initial','policy_day','audit','metrics','lifecycle'):setattr(self,key,saved[key])
            self.ends=saved.get('ends',{})

    def rows(self,sql,args=()):
        with closing(self.service.database.connect()) as c:return [dict(r) for r in c.execute(sql,args)]

    def save(self):
        value={k:getattr(self,k) for k in ('issues','seasons','initial','ends','policy_day','audit','metrics','lifecycle')}
        value.update(seed=self.args.seed,entropy=state(self.entropy),identities=state(self.identities),calendar_rng=state(self.calendar_rng),action=self.current_action)
        dump(self.checkpoint,value)

    def budget(self):
        self.save()
        if time.monotonic()>=self.deadline:raise TimeoutError('실행 예산 도달: 트랜잭션이 끝난 체크포인트에서 중단했습니다.')

    def snapshot(self,season):
        self.initial[str(season)]=self.population_snapshot()

    def population_snapshot(self):
        return dict(players=self.rows("SELECT person_id,age,health,average FROM idols WHERE status!='unseen'"),agencies=self.rows('''SELECT a.id,a.funds_krw,COALESCE((SELECT SUM(outstanding_krw) FROM finance_debts d WHERE d.agency_id=a.id),0) debt FROM agencies a'''))

    def setup(self):
        paths=sorted(p for p in (self.resource_root/'assets/idols').rglob('*') if p.is_file())
        photo_digest=hashlib.sha256(''.join(str(p.relative_to(self.resource_root))+':'+hashlib.sha256(p.read_bytes()).hexdigest() for p in paths).encode()).hexdigest()
        if self.args.resume:
            marker=json.loads(self.marker.read_text(encoding='utf8'))
            if marker.get('photo_manifest_digest')!=photo_digest:
                raise ValueError('사진 입력이 변경되었습니다. 기존 진단 DB를 변경하지 않고 중단합니다. 동일 입력으로 복원하거나 새 진단 폴더를 사용하세요.')
        self.service=GameService(self.resource_root,self.path);self.service.calendar.rng=self.calendar_rng
        if self.args.resume:
            day=self.service.calendar.state().date
            # Compatibility with the first v25 checkpoint, taken exactly at a
            # completed-season boundary. Never infer an older boundary later.
            previous=str(day.season-1)
            if day.day_in_season==0 and previous in self.initial and previous not in self.ends:self.ends[previous]=self.population_snapshot()
            return
        dump(self.marker,dict(test_only=True,source_root=str(self.resource_root),seed=self.args.seed,policy='player-public-rotation-v1; existing-nine-AI-unchanged',
            photo_files=len(paths),photo_manifest_digest=photo_digest,
            entropy='test process only: seeded secrets, UUID4, SystemRandom; clock timestamps excluded from semantic reproducibility',source_capabilities='code v16 / 21+24; no dedicated 22/23 snapshots or weekly AI rotation'))
        self.service.database.create_game(self.service.scan.people,load_settings(),random.Random(self.args.seed+3))
        self.service.calendar.initialize();self.service.draft_session.select_agency('ador');self.service.draft.start(rng=random.Random(self.args.seed+4))
        while self.service.draft.state().status!='completed':
            with public_policy(self.service.database):
                snap=self.service.draft_session.snapshot();person=self.service.draft_session.policy.choose(snap.candidates)
            t=snap.state.next_turn;self.service.draft.pick(t.agency_id,person,expected_pick_number=t.pick_number)
        for n in self.service.market.negotiations('ador'):
            if n['purpose']=='founding' and n['status']=='open':
                p=next(p for p in self.service.market.public_people() if p['id']==n['person_id'])
                self.service.market.offer(n['id'],p['market']*11//10,1,request_id='simulation:'+n['id'])
        s=self.service.squads.snapshot();plan=self.service.squads.policy.plan(s.members);self.service.squads.confirm_initial(plan.first_team_ids)
        for squad in ('first_team','second_team'):
            s=self.service.squads.snapshot()
            self.service.squads.set_leader(squad,next(p.id for p in s.members if p.squad==squad),expected_revision=s.revision)
        for day in range(-7,0):self.service.calendar.advance_day(expected_absolute_day=day)
        self.player_policy();self.snapshot(1);self.save()

    def player_policy(self):
        """Public owned CA + health/registration only. Does not replace nine AI."""
        service=self.service;d=service.calendar.state().date
        if d.weekday()!=0:return
        with public_policy(service.database):
            s=service.squads.snapshot()
            if d.is_regular:
                with closing(service.database.connect()) as c:
                    conditions={p.id:public_condition(c,p.id,d.absolute_day) for p in s.members}
                    ready={p.id for p in s.members if promotion_allowed(c,p.id,d.absolute_day)}
                used=service.squads.normal_changes_today()
                for outgoing in sorted((p for p in s.members if p.squad=='first_team' and conditions[p.id].registration_weeks>=3 and p.id not in used),key=lambda p:(-conditions[p.id].registration_weeks,p.id)):
                    eligible=[p for p in s.members if p.squad=='second_team' and p.id not in used and p.id in ready and not conditions[p.id].injured and conditions[p.id].registration_weeks==0]
                    if not eligible:break
                    incoming=max(eligible,key=lambda p:(p.average,p.health,p.id));service.squads.swap(outgoing.id,incoming.id,expected_revision=service.squads.snapshot().revision);used.update((outgoing.id,incoming.id))
            for squad in ('first_team','second_team'):
                s=service.squads.snapshot();pool=[p for p in s.members if p.squad==squad]
                if pool and not dict(s.leaders).get(squad):service.squads.set_leader(squad,max(pool,key=lambda p:(p.leadership,p.health,p.id)).id,expected_revision=s.revision)
            if not d.is_regular and not d.is_postseason and d.week==3:
                own=service.market.public_people(agency='ador')
                if sum(p['career_status']=='trainee' for p in own)<4:
                    juniors=[p for p in service.market.public_people(available=True) if p['age']<17]
                    if juniors:
                        p=max(juniors,key=lambda p:(p['average'],p['id']))
                        try:service.market.sign_trainee('ador',p['id'],request_id=f'sim:trainee:{d.absolute_day}')
                        except ValueError as e:self.issues.append(dict(severity='P2',season=d.season,agency='ador',action='player_trainee',error=str(e)))

    def annual(self):
        api=self.service.annual_draft;api.start()
        while True:
            s=api.state();t=s['turn']
            if not t:break
            self.current_action=f'annual:{s["season"]}:{t["pick_number"]}';self.budget()
            with public_policy(self.service.database):
                if t['agency_id']!='ador':api.ai_step();continue
                if t['status']=='scheduled':
                    legal=[]
                    with closing(self.service.database.connect()) as c:
                        for p in s['candidates']:
                            try:
                                if p['age']>=17:_slot(c,'ador')
                                _budget(c,'ador',10000000 if p['age']<17 else 30000000);legal.append(p)
                            except ValueError:continue
                    if not legal:raise ValueError('플레이어가 합법적으로 계약 가능한 후보가 없습니다. 지명권 보존 상태로 중단합니다.')
                    p=choose(legal,self.service.market.public_people(agency='ador'));api.pick('ador',p['id'],expected_pick=t['pick_number'])
                    s=api.state();t=s['turn']
                if t and t['agency_id']=='ador' and t['status']=='negotiating':
                    p=api.person(t['person_id']);offers=s['negotiation']['offers'];amount=offer_amount(p,offers,'balanced')
                    api.offer('ador',amount,1,expected_pick=t['pick_number'],request_id=f'sim:annual:{s["season"]}:{t["pick_number"]}:{len(offers)+1}')

    def run(self):
        with seeded_entropy(self.entropy,self.identities):
            try:
                self.setup();self.current_action='run'
                while True:
                    d=self.service.calendar.state().date
                    if d.season>self.args.seasons:break
                    if str(d.season) not in self.initial:self.snapshot(d.season)
                    self.budget()
                    if d.weekday()==0 and self.policy_day!=d.absolute_day:
                        self.current_action=f'player-policy:{d.absolute_day}';self.player_policy();self.policy_day=d.absolute_day
                    if d.day_in_season==196:self.annual()
                    for f in self.service.matches.fixtures():
                        if f.status=='completed':continue
                        self.current_action=f'regular:{f.id}';self.budget();result=self.service.matches.play(f.id)
                        self.measure_match(result,f)
                    for event in self.service.specials.events():
                        if not event['today'] or event['status']=='completed':continue
                        self.current_action=f'special:{event["id"]}';self.service.specials.start(event['id'])
                        while True:
                            remaining=[r for r in self.service.specials.state(event['id'])['rounds'] if r['status']!='completed']
                            if not remaining:break
                            self.budget();self.service.specials.play(remaining[0]['id'])
                    for contest in self.service.finals.rows():
                        if contest['status']=='completed':continue
                        self.current_action=f'final:{contest["id"]}';self.budget();self.service.finals.play(contest['id'])
                    if d.weekday()==6:
                        with closing(self.service.database.connect()) as c:
                            result=quick_audit(c)
                            if d.week==1 and d.is_regular:self.audit.append(schedule_audit(c,d.season))
                        self.audit.append(dict(season=d.season,day=d.absolute_day,checks=result,status='PASS' if not any(result.values()) else 'FAIL'))
                        if any(result.values()):raise AssertionError('핵심 무결성 위반: '+str(result))
                        print(f'{d} / regular {self.rows("SELECT COUNT(*) n FROM match_results")[0]["n"]} / {round(time.monotonic()-self.started,1)}s',flush=True)
                    self.current_action=f'advance:{d.absolute_day}';self.service.calendar.advance_day(expected_absolute_day=d.absolute_day)
                    if d.day_in_season==216:
                        self.finish_season(d.season)
                        self.export('running')
                        # A failed completed-season audit must not expand.
                        if self.seasons[-1]['status']!='PASS':raise AssertionError('완료 시즌 검사 실패: 다음 시즌을 자동 실행하지 않습니다.')
                    self.save()
                status='completed'
            except TimeoutError as error:status='checkpoint';self.issues.append(dict(severity='P3',action=self.current_action,error=str(error),expected='time budget safe stop',fixed=False))
            except Exception as error:
                status='blocked';self.issues.append(dict(severity='P0',action=self.current_action,error=repr(error),expected='existing official services complete one season',traceback=traceback.format_exc(),fixed=False));print(traceback.format_exc(),flush=True)
            finally:
                if hasattr(self,'service'):self.save();self.export(status)
        return status

    def measure_match(self,r,f):
        # Saved input contains actual eligible public CA and pre-match fatigue.
        with closing(self.service.database.connect()) as c:
            row=c.execute('SELECT input_json,condition_json FROM match_runs WHERE match_id=?',(f.id,)).fetchone()
            data=json.loads(row[0]);conditions=json.loads(row[1]);strength={};sizes={}
            for team in data['teams']:
                ps=team['players'];sizes[team['agency_id']]=len(ps)
                strength[team['agency_id']]=sum(sum(p['skills'])/8 for p in ps)/len(ps) if ps else None
        score={t['agency_id']:t['total_score'] for t in r.teams};p=r.players
        self.metrics.append(dict(season=f.season,match_id=f.id,content_id=data['content_id'],resolution=r.resolution,winner=r.winner_id,
            sizes=sizes,public_ca=strength,score_gap=max(score.values())-min(score.values()),attempts=sum(v['base_attempts'] for v in p),successes=sum(v['base_successes'] for v in p),
            fatigue_penalized=sum(v.get('penalty',0)>0 for v in conditions.get('public',{}).values()),
            upset=bool(r.winner_id and strength.get(r.winner_id) is not None and any(v is not None and v-strength[r.winner_id]>=10 for v in strength.values()))))

    def finish_season(self,season):
        self.ends[str(season)]=self.population_snapshot()
        with closing(self.service.database.connect()) as c:
            a=schedule_audit(c,season);self.audit.append(a);errors=quick_audit(c)
            final=c.execute('SELECT champion_id FROM season_finals WHERE season=?',(season,)).fetchone()
            counts=dict(regular=c.execute('SELECT COUNT(*) FROM match_results r JOIN scheduled_matches m ON m.id=r.match_id WHERE m.season=?',(season,)).fetchone()[0],
                specials=c.execute("SELECT COUNT(*) FROM special_events WHERE season=? AND status='completed'",(season,)).fetchone()[0],
                awards=c.execute('SELECT COUNT(*) FROM (SELECT award_type FROM individual_awards WHERE season=? UNION SELECT award_type FROM award_outcomes WHERE season=?)',(season,season)).fetchone()[0],
                newcomers=c.execute('SELECT COUNT(*) FROM annual_entries WHERE intake_season=?',(season,)).fetchone()[0],
                annual_turns=c.execute("SELECT COUNT(*) FROM annual_turns WHERE season=? AND status IN('signed','failed')",(season,)).fetchone()[0])
            ok=a['status']=='PASS' and not any(errors.values()) and counts==dict(regular=585,specials=6,awards=11,newcomers=70,annual_turns=30)
            ok=ok and c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and bool(final and final[0])
            self.seasons.append(dict(season=season,status='PASS' if ok else 'FAIL',champion=final[0] if final else None,**counts))

    def export(self,status):
        db=self.service.database
        with closing(db.connect()) as c:
            d=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0]
            all_players=[dict(r) for r in c.execute('SELECT person_id,age,health,average FROM idols')]
            agencies=[dict(r) for r in c.execute('SELECT id,name,funds_krw FROM agencies')]
            finances=[];develop=[]
            for season,start in self.initial.items():
                season=int(season)
                end=self.ends.get(str(season));end_players=end['players'] if end else all_players;end_agencies=end['agencies'] if end else agencies
                exposed={r[0] for r in c.execute('SELECT person_id FROM initial_draft_candidates UNION SELECT person_id FROM annual_entries WHERE intake_season<?',(season,))}
                for agency in end_agencies:
                    a=agency['id'];ledger=[dict(r) for r in c.execute('SELECT kind,SUM(amount) amount,SUM(cash_delta) cash,SUM(debt_delta) debt FROM finance_ledger WHERE agency_id=? AND season=? GROUP BY kind',(a,season))]
                    finances.append(dict(season=season,agency_id=a,start_cash=next(r['funds_krw'] for r in start['agencies'] if r['id']==a),end_cash=agency['funds_krw'] if end else None,checkpoint_cash=agency['funds_krw'],checkpoint_debt=agency.get('debt',c.execute('SELECT COALESCE(SUM(outstanding_krw),0) FROM finance_debts WHERE agency_id=?',(a,)).fetchone()[0]),ledger=ledger,
                        sponsor=sum(r['amount'] for r in ledger if r['kind']=='weekly_sponsor'),bonus=sum(r['amount'] for r in ledger if r['kind']=='season_bonus'),
                        payroll_due=c.execute('SELECT COALESCE(SUM(due_krw),0) FROM finance_payroll WHERE agency_id=? AND season=?',(a,season)).fetchone()[0],
                        payroll_paid=c.execute('SELECT COALESCE(SUM(paid_krw),0) FROM finance_payroll WHERE agency_id=? AND season=?',(a,season)).fetchone()[0]))
                before={r['person_id']:r for r in start['players'] if r['person_id'] in exposed}
                for p in end_players:
                    old=before.get(p['person_id']);develop.append(dict(season=season,person_id=p['person_id'],start_ca=old['average'] if old else None,end_ca=p['average'] if end else None,checkpoint_ca=p['average'],ca_change=p['average']-old['average'] if old else None,age=p['age'],health=p['health']))
            injuries=[dict(r) for r in c.execute("SELECT (absolute_day/217)+1 season,kind,COUNT(*) opportunities,SUM(occurred) injuries,AVG(probability) expected_probability FROM condition_events WHERE kind IN('match','first_rest','second') GROUP BY season,kind")]
            registration=[dict(r) for r in c.execute("SELECT json_extract(details_json,'$.fatigue.registration_weeks') registration_weeks,COUNT(*) opportunities,SUM(occurred) injuries FROM condition_events WHERE kind='match' GROUP BY registration_weeks")]
            for r in injuries:r['observed_rate']=ratio(r['injuries'],r['opportunities'])
            population=[dict(r) for r in c.execute('SELECT career_status,COUNT(*) players FROM roster_memberships GROUP BY career_status')]
            history=[dict(r) for r in c.execute('SELECT (absolute_day/217)+1 season,kind,COUNT(*) count FROM market_history GROUP BY season,kind')]
            role_days=[dict(r) for r in c.execute('SELECT (absolute_day/217)+1 season,person_id,role,COUNT(*) days FROM development_days GROUP BY season,person_id,role')]
            growth=[dict(r) for r in c.execute('''SELECT (s.absolute_day/217)+1 season,r.person_id,json_extract(t.trial_json,'$.kind') kind,COUNT(*) trials,SUM(json_extract(t.trial_json,'$.applied')) applied FROM development_trials t JOIN development_results r ON r.settlement_id=t.settlement_id AND r.person_id=t.person_id JOIN development_settlements s ON s.id=r.settlement_id GROUP BY season,r.person_id,kind''')]
            audits=quick_audit(c);integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
            salary=[dict(r) for r in c.execute('SELECT agency_id,COUNT(*) contracts,SUM(annual_krw) annual FROM finance_contracts WHERE start_day<=? AND (end_day IS NULL OR end_day>?) GROUP BY agency_id',(d,d))]
        self.audit.append(dict(day=d,final_integrity=integrity,checks=audits))
        summary=dict(status=status,completed_seasons=len([s for s in self.seasons if s['status']=='PASS']),seed=self.args.seed,absolute_day=d,elapsed_seconds=round(time.monotonic()-self.started,3),
            requested_seasons=self.args.seasons,budget_seconds=self.args.budget_seconds,seasons=self.seasons,issues=self.issues,test_db=str(self.path),
            policy='player-public-rotation-v1; nine existing AI unchanged; lineups all use existing schedule-aware public policy',
            actual_matches=len(self.metrics),regular_success_rate=ratio(sum(r['successes'] for r in self.metrics),sum(r['attempts'] for r in self.metrics)),
            deathmatches=sum(r['resolution']=='deathmatch' for r in self.metrics),large_ca_upsets=sum(r['upset'] for r in self.metrics),population=population,
            not_tested=['10–20 seasons','full regression suite','counterfactual fatigue causation','outcomes after the checkpoint'],
            not_exercised=[k for k in ('expiry','retire','forced_sale') if not any(k in r['kind'] and r['count'] for r in history)],
            checkpoint='SQLite at last committed official action + RNG state checkpoint.json',user_save_modified=False)
        for name,rows in [('season_statistics',self.seasons),('agency_statistics',self.service.records.agencies()),('financial_statistics',finances),('player_development',develop),('injury_statistics',injuries),('injury_registration',registration),('regular_matches',self.metrics),('player_role_days',role_days),('growth_trials',growth),('contract_movement',history),('population',population),('salary_statistics',salary)]:csvfile(self.output/(name+'.csv'),rows)
        dump(self.output/'integrity_checks.json',self.audit);dump(self.output/'simulation_summary.json',summary)
        (self.output/'simulation_issues.txt').write_text('\n\n'.join(json.dumps(r,ensure_ascii=False,indent=2) for r in self.issues) or 'No detected issue at this checkpoint. Not proof of unexercised paths.',encoding='utf8')
        print(json.dumps({k:summary[k] for k in ('status','completed_seasons','absolute_day','elapsed_seconds','actual_matches')},ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=250029);p.add_argument('--seasons',type=int,default=1);p.add_argument('--budget-seconds',type=int,default=480);p.add_argument('--resume',action='store_true');p.add_argument('--allow-long-run',action='store_true')
    args=p.parse_args()
    if args.seasons<1 or args.seasons>20:p.error('seasons must be 1..20')
    if args.seasons>5 and not args.allow_long_run:p.error('10–20 seasons require explicit future authorization and --allow-long-run')
    if not 10<=args.budget_seconds<=900:p.error('budget-seconds must be 10..900')
    try:status=Simulation(args).run()
    except Exception:traceback.print_exc();return 1
    return 0 if status in ('completed','checkpoint') else 2
if __name__=='__main__':raise SystemExit(main())
