from .game_clock import regular_day
"""Atomic, resumable special sessions and isolated standings/individual records."""
from collections import Counter
from contextlib import closing
from dataclasses import asdict
import json
import random
import secrets
import sqlite3

from .config import SKILLS
from .game_clock import current_game_date,DAYS_PER_SEASON
from .initial_setup import initial_setup_reason
from .league import standings
from .conditions import public_condition,seed_for,commit_appearance_conditions
from .condition_rules import injury_probability
from .match_policy import choose_representative
from .match_service import ABILITY_NAMES
from .match_types import MatchTeam,MatchPlayer,Judgment,MatchError,UnresolvedMatch
from .special_engine import ContestInput,ContestResult,SPECIAL_MAIN,ENGINE_VERSION,calculate_contest,stage_points
from .special_policy import select_special


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class SpecialService:
    def __init__(self,database,*,seed_factory=None):
        self.database=database
        self.seed_factory=seed_factory or (lambda:secrets.randbits(128))

    @staticmethod
    def _event(connection,event_id,*,current=False):
        row=connection.execute('SELECT * FROM special_events WHERE id=?',(event_id,)).fetchone()
        if row is None:raise MatchError('특별전 일정을 찾을 수 없습니다.')
        if current:
            day=current_game_date(connection)
            if day is None or not day.is_regular or (day.season,day.week,day.weekday())!=(row['season'],row['week'],6):
                raise MatchError('현재 게임 날짜의 특별전만 진행할 수 있습니다.')
            reason=initial_setup_reason(connection)
            if reason:raise MatchError(reason)
            if connection.execute("SELECT 1 FROM scheduled_matches WHERE season=? AND regular_day(season,week,weekday)<=? AND status!='completed' LIMIT 1",(day.season,day.absolute_day)).fetchone():
                raise MatchError('이전 정규 경기를 모두 완료한 뒤 특별전을 시작해 주세요.')
            if connection.execute("SELECT 1 FROM special_events WHERE season=? AND week<? AND status!='completed' LIMIT 1",(row['season'],row['week'])).fetchone():
                raise MatchError('앞선 특별전을 먼저 완료해 주세요.')
        return row

    def events(self):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN');day=current_game_date(c)
            result=[]
            for row in c.execute('SELECT * FROM special_events ORDER BY season,week'):
                published=bool(day and regular_day(row['season'],row['week'],0)<=day.absolute_day)
                today=bool(day and day.is_regular and (day.season,day.week,day.weekday())==(row['season'],row['week'],6))
                result.append(dict(id=row['id'],season=row['season'],week=row['week'],
                    event_type=row['event_type'] if published else '월요일 공개 예정',published=published,today=today,status=row['status']))
            return tuple(result)

    def state(self,event_id):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN');event=self._event(c,event_id)
            session=c.execute('SELECT groups_json,standings_json FROM special_sessions WHERE event_id=?',(event_id,)).fetchone()
            rounds=[]
            for row in c.execute("SELECT id,stage,content_name,main_json,required,base_attempts,status,error,agencies_json FROM special_rounds WHERE event_id=? ORDER BY CASE stage WHEN 'upper' THEN 0 WHEN 'lower' THEN 1 ELSE 2 END",(event_id,)):
                rounds.append(dict(id=row['id'],stage=row['stage'],content_name=row['content_name'],
                    main_skills=json.loads(row['main_json']),required=row['required'],base_attempts=row['base_attempts'],status=row['status'],error=row['error'],agencies=json.loads(row['agencies_json'])))
            return dict(event_id=event_id,status=event['status'],groups=json.loads(session[0]) if session else None,
                        seed_standings=json.loads(session[1]) if session else (),rounds=rounds)

    @staticmethod
    def _insert_round(c,event,stage,content_id,name,main,required,attempts,agencies,seed):
        c.execute('''INSERT INTO special_rounds(id,event_id,stage,content_id,content_name,main_json,required,base_attempts,agencies_json,seed)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',(f'{event}:{stage}',event,stage,content_id,name,encode(main),required,attempts,encode(agencies),str(seed)))

    def start(self,event_id):
        try:
            with closing(self.database.connect()) as c,c:
                c.execute('BEGIN IMMEDIATE')
                session=c.execute('SELECT engine_version FROM special_sessions WHERE event_id=?',(event_id,)).fetchone()
                if session:
                    if session[0]!=ENGINE_VERSION:raise MatchError('저장된 특별전 엔진 버전으로 재개해야 합니다.')
                    return
                event=self._event(c,event_id,current=True)
                if event['status']!='scheduled':raise MatchError('특별전 상태와 저장된 단계가 일치하지 않습니다.')
                league=standings(c,event['season'])
                if len(league)!=10:raise MatchError('특별전에는 기획사 10개가 필요합니다.')
                groups={'upper':[r['agency_id'] for r in league[:5]],'lower':[r['agency_id'] for r in league[5:]]}
                seed=self.seed_factory()
                if type(seed) is not int or seed<0:raise MatchError('특별전 난수 시드 오류입니다.')
                c.execute('INSERT INTO special_sessions VALUES (?,?,?,?,?)',(event_id,ENGINE_VERSION,str(seed),encode(league),encode(groups)))
                for stage in ('upper','lower'):
                    self._insert_round(c,event_id,stage,'special:'+event['event_type'],event['event_type'],SPECIAL_MAIN[event['event_type']],10,30,groups[stage],seed_for(seed,stage))
                c.execute("UPDATE special_events SET status='in_progress' WHERE id=?",(event_id,))
        except sqlite3.Error as error:raise MatchError('특별전 시작 저장에 실패했습니다. 현재 세이브를 유지했습니다.') from error

    @staticmethod
    def _roster(c,agency):
        rows=c.execute('''SELECT p.id,p.name,p.photo_path,i.health,r.career_status,a.skill,a.value
            FROM roster_memberships r JOIN people p ON p.id=r.person_id JOIN idols i ON i.person_id=p.id
            JOIN abilities a ON a.person_id=p.id WHERE r.agency_id=? AND r.career_status IN('first_team','second_team')
            ORDER BY CASE r.career_status WHEN 'first_team' THEN 0 ELSE 1 END,p.id,a.skill''',(agency,))
        people={}
        for row in rows:
            item=people.setdefault(row['id'],dict(name=row['name'],path=row['photo_path'],health=row['health'],squad=row['career_status'],skills={}))
            item['skills'][row['skill']]=row['value']
        if any(set(p['skills'])!=set(SKILLS) for p in people.values()):raise MatchError('특별전 선수의 현재 능력치가 불완전합니다.')
        from .franchise import eligible
        franchises=eligible(c,agency)
        return tuple((MatchPlayer(identity,agency,p['name'],p['health'],tuple(p['skills'][s] for s in SKILLS),identity in franchises),p['squad'],p['path']) for identity,p in people.items())

    @staticmethod
    def _pool(c,row,agency):
        roster=SpecialService._roster(c,agency)
        if row['stage']=='final':
            origin=c.execute('''SELECT input_json FROM special_rounds WHERE event_id=? AND stage IN('upper','lower')
                AND status='completed' ''',(row['event_id'],)).fetchall()
            original={p['id'] for r in origin for t in json.loads(r[0])['teams'] if t['agency_id']==agency for p in t['players']}
            roster=tuple(item for item in roster if item[0].id in original)
        return roster

    @staticmethod
    def _leaders(c,agency):
        return {row['person_id']:(2 if row['squad']=='first_team' else 1) for row in c.execute('SELECT person_id,squad FROM squad_leaders WHERE agency_id=?',(agency,))}

    def selection(self,round_id):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN')
            row=c.execute('SELECT * FROM special_rounds WHERE id=?',(round_id,)).fetchone()
            if not row:raise MatchError('특별전 단계를 찾을 수 없습니다.')
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            agency=player[0] if player else None
            agencies=json.loads(row['agencies_json'])
            if agency not in agencies or row['status']=='completed':return dict(options=(),count=0,first_count=0,fixed=None,agency=agency)
            event=self._event(c,row['event_id']);day=regular_day(event['season'],event['week'],6)
            leaders=self._leaders(c,agency);options=[];fixed=None
            if row['input_json']:
                contest=ContestInput.from_dict(json.loads(row['input_json']));team=next(t for t in contest.teams if t.agency_id==agency)
                paths={p.id:path for p,_,path in self._roster(c,agency)}
                fixed=tuple(p.id for p in team.players)
                for p in team.players:
                    options.append(dict(player=p,squad=contest.conditions['squads'][p.id],path=paths.get(p.id,''),condition=contest.conditions['public'][p.id],available=True,leader=contest.leader_attempts.get(p.id,0)))
            else:
                for p,squad,path in self._pool(c,row,agency):
                    condition=public_condition(c,p.id,day)
                    options.append(dict(player=p,squad=squad,path=path,condition=asdict(condition),available=not condition.injured,leader=leaders.get(p.id,0)))
            count=min(row['required'],sum(o['available'] for o in options))
            return dict(options=tuple(options),count=count,first_count=min(count,sum(o['available'] and o['squad']=='first_team' for o in options)),fixed=fixed,agency=agency)

    def _prepare(self,round_id,lineups):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM special_rounds WHERE id=?',(round_id,)).fetchone()
            if row is None:raise MatchError('특별전 단계를 찾을 수 없습니다.')
            if row['status']=='completed':return self._load(c,round_id)
            self._event(c,row['event_id'],current=True)
            if row['status']=='blocked':raise UnresolvedMatch(row['error'])
            if row['input_json']:
                contest=ContestInput.from_dict(json.loads(row['input_json']))
                for agency,ids in (lineups or {}).items():
                    team=next((t for t in contest.teams if t.agency_id==agency),None)
                    if team is None or len(ids)!=len(set(ids)) or set(ids)!={p.id for p in team.players}:raise MatchError('저장된 특별전 출전자를 변경할 수 없습니다.')
                return contest,int(row['seed'])
            agencies=json.loads(row['agencies_json'])
            if set(lineups or {})-set(agencies):raise MatchError('이번 단계 참가 기획사의 선수만 지정할 수 있습니다.')
            event=self._event(c,row['event_id']);day=regular_day(event['season'],event['week'],6)
            main=tuple(json.loads(row['main_json']));teams=[];probabilities={};leader_counts={}
            context={'public':{},'injury_probabilities':{},'squads':{}}
            for agency in agencies:
                roster=self._pool(c,row,agency)
                conditions={p.id:public_condition(c,p.id,day) for p,_,_ in roster}
                eligible=tuple((p,squad) for p,squad,_ in roster if not conditions[p.id].injured)
                count=min(row['required'],len(eligible));first_count=min(count,sum(squad=='first_team' for _,squad in eligible))
                leaders=self._leaders(c,agency)
                if lineups and agency in lineups:
                    ids=tuple(lineups[agency]);by_id={p.id:(p,squad) for p,squad in eligible}
                    if len(ids)!=len(set(ids)) or len(ids)!=count or set(ids)-set(by_id):raise MatchError(f'부상자를 제외한 최초 참가 대상 중 정확히 {count}명을 선택해 주세요.')
                    if sum(by_id[i][1]=='first_team' for i in ids)!=first_count:raise MatchError('출전 가능한 1군을 우선 선발하고 부족분만 2군으로 채워 주세요.')
                    selected=tuple(by_id[i][0] for i in sorted(ids))
                else:selected=select_special(eligible,row['required'],main,conditions,leaders,row['base_attempts'])
                selected=tuple(sorted(selected,key=lambda p:p.id));first_leader=next((p for p,n in leaders.items() if n==2),None)
                rep=choose_representative(selected,main,row['required'],first_leader,penalties={p.id:conditions[p.id].penalty for p in selected})
                teams.append(MatchTeam(agency,selected,first_leader,rep))
                squads={p.id:squad for p,squad in eligible}
                for p in selected:
                    condition=conditions[p.id]
                    probabilities[p.id]={skill:p.value(skill)/100*(1-condition.penalty) for skill in SKILLS}
                    leader_counts[p.id]=leaders.get(p.id,0)
                    context['public'][p.id]=asdict(condition);context['squads'][p.id]=squads[p.id]
                    context['injury_probabilities'][p.id]=injury_probability(p.health,condition.registration_weeks,'match')
            session=c.execute('SELECT standings_json FROM special_sessions WHERE event_id=?',(row['event_id'],)).fetchone()
            seed_order=tuple(r['agency_id'] for r in json.loads(session[0]) if r['agency_id'] in agencies)
            contest=ContestInput(round_id,row['content_id'],row['required'],main,tuple(teams),probabilities,leader_counts,row['base_attempts'],seed_order,context)
            c.execute("UPDATE special_rounds SET input_json=?,status='prepared' WHERE id=?",(encode(contest.to_dict()),round_id))
            return contest,int(row['seed'])

    @staticmethod
    def _load(c,round_id):
        row=c.execute('SELECT result_json FROM special_rounds WHERE id=?',(round_id,)).fetchone()
        if row is None or row[0] is None:return None
        summary=json.loads(row[0])
        events=tuple(Judgment(r['sequence'],r['agency_id'],r['person_id'],r['phase'],r['skill'],r['tick'],r['round_number'],r['attempt'],r['probability'],r['roll'],bool(r['success'])) for r in c.execute('SELECT * FROM special_judgments WHERE round_id=? ORDER BY sequence',(round_id,)))
        return ContestResult(round_id,tuple(summary['teams']),tuple(summary['players']),events,tuple(summary.get('teamwork',())))

    def result(self,round_id):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN');return self._load(c,round_id)

    @staticmethod
    def _store(c,row,result,groups):
        for team in result.teams:
            c.execute('INSERT INTO special_team_results VALUES (?,?,?,?,?,?)',(row['id'],team['agency_id'],team['rank'],team['base_score'],team['tiebreak_score'],int(team['forfeit'])))
        for p in result.players:
            fields=('person_id','agency_id','content_id','base_attempts','base_successes','base_failures','main_attempts','support_attempts','leader_attempts','leader_successes','deathmatch_attempts','deathmatch_successes','success_rate')
            c.execute('INSERT INTO special_player_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(row['id'],*(p[k] for k in fields)))
        attempts=Counter((e.person_id,e.phase,e.skill) for e in result.events)
        successes=Counter((e.person_id,e.phase,e.skill) for e in result.events if e.success)
        c.executemany('INSERT INTO special_ability_stats VALUES (?,?,?,?,?,?,?)',[(row['id'],p,phase,skill,n,successes[(p,phase,skill)],n-successes[(p,phase,skill)]) for (p,phase,skill),n in attempts.items()])
        c.executemany('INSERT INTO special_judgments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',[(row['id'],e.sequence,e.agency_id,e.person_id,e.phase,e.skill,e.tick,e.round_number,e.attempt,e.probability,e.roll,int(e.success)) for e in result.events])
        for agency,delta in stage_points(row['stage'],result.teams,groups).items():
            c.execute('INSERT INTO special_points VALUES (?,?,?,?,?)',(row['event_id'],agency,row['stage'],row['id'],delta))
        c.execute("UPDATE special_rounds SET result_json=?,status='completed',error='' WHERE id=?",(encode(result.summary()),row['id']))

    @staticmethod
    def _create_final(c,event_id):
        rows=c.execute("SELECT id,stage,status FROM special_rounds WHERE event_id=? AND stage IN('upper','lower')",(event_id,)).fetchall()
        if len(rows)!=2 or any(r['status']!='completed' for r in rows):return
        if c.execute("SELECT 1 FROM special_rounds WHERE event_id=? AND stage='final'",(event_id,)).fetchone():return
        agencies=[]
        for r in sorted(rows,key=lambda r:r['stage']=='lower'):
            ranks=(4,5) if r['stage']=='upper' else (1,2)
            agencies.extend(a[0] for a in c.execute('SELECT agency_id FROM special_team_results WHERE round_id=? AND rank IN (?,?) ORDER BY rank',(r['id'],*ranks)))
        event=c.execute('SELECT season FROM special_events WHERE id=?',(event_id,)).fetchone()
        seed=int(c.execute('SELECT seed FROM special_sessions WHERE event_id=?',(event_id,)).fetchone()[0])
        rules=json.loads(c.execute('SELECT rules_json FROM season_schedules WHERE season=?',(event[0],)).fetchone()[0])
        rng=random.Random(seed_for(seed,'followup-content'));content=rng.choice(rules['contents'])
        required=rng.randint(content['participants_min'],content['participants_max'])
        SpecialService._insert_round(c,event_id,'final',content['id'],content['name'],tuple(ABILITY_NAMES[s] for s in content['main_abilities']),required,60,agencies,seed_for(seed,'final'))

    def play(self,round_id,*,lineups=None):
        try:
            prepared=self._prepare(round_id,lineups)
            if isinstance(prepared,ContestResult):return prepared
            contest,seed=prepared;unresolved=None
            with closing(self.database.connect()) as c,c:
                c.execute('BEGIN IMMEDIATE');cached=self._load(c,round_id)
                if cached is not None:return cached
                row=c.execute('SELECT * FROM special_rounds WHERE id=?',(round_id,)).fetchone()
                if not row or row['status']!='prepared' or row['input_json']!=encode(contest.to_dict()):raise MatchError('특별전 준비 상태가 변경되었습니다.')
                session=c.execute('SELECT groups_json,engine_version FROM special_sessions WHERE event_id=?',(row['event_id'],)).fetchone()
                if session['engine_version']!=ENGINE_VERSION:raise MatchError('특별전 엔진 버전이 다릅니다.')
                try:result=calculate_contest(contest,random.Random(seed))
                except UnresolvedMatch as error:
                    unresolved=error;c.execute("UPDATE special_rounds SET status='blocked',error=? WHERE id=?",(str(error),round_id))
                else:
                    self._store(c,row,result,json.loads(session['groups_json']))
                    event=self._event(c,row['event_id']);day=regular_day(event['season'],event['week'],6)
                    commit_appearance_conditions(c,result.players,contest.conditions,seed,day,f'special:{round_id}',seed_label='special-injury-v1')
                    self._create_final(c,row['event_id'])
                    if c.execute("SELECT COUNT(*) FROM special_rounds WHERE event_id=? AND status='completed'",(row['event_id'],)).fetchone()[0]==3:
                        c.execute("UPDATE special_events SET status='completed' WHERE id=?",(row['event_id'],))
            if unresolved:raise unresolved
            return result
        except sqlite3.Error as error:raise MatchError('특별전 저장에 실패했습니다. 완료되지 않은 결과·승점·피로·부상 기록은 반영되지 않았습니다. 다시 시도해 주세요.') from error

    def player_records(self,person_id):
        with closing(self.database.connect()) as c:
            return tuple(dict(r) for r in c.execute('''SELECT p.*,r.stage,e.season,e.week FROM special_player_stats p
                JOIN special_rounds r ON r.id=p.round_id JOIN special_events e ON e.id=r.event_id
                WHERE p.person_id=? ORDER BY e.season,e.week,CASE r.stage WHEN 'final' THEN 1 ELSE 0 END''',(person_id,)))

    def final_summary(self,event_id):
        """All ten agencies' actual group/followup ranks, never a fabricated overall ranking."""
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN')
            session=c.execute('SELECT groups_json FROM special_sessions WHERE event_id=?',(event_id,)).fetchone()
            if not session:return ()
            groups=json.loads(session[0])
            ranks={(r['agency_id'],r['stage']):r['rank'] for r in c.execute('''SELECT t.agency_id,r.stage,t.rank
                FROM special_team_results t JOIN special_rounds r ON r.id=t.round_id WHERE r.event_id=?''',(event_id,))}
            points={(r['agency_id'],r['stage']):r['delta'] for r in c.execute('SELECT * FROM special_points WHERE event_id=?',(event_id,))}
            names=dict(c.execute('SELECT id,name FROM agencies'));result=[]
            for group in ('upper','lower'):
                for a in sorted(groups[group],key=lambda a:(ranks.get((a,group),99),a)):
                    initial=points.get((a,group),0);followup=points.get((a,'final'),0)
                    result.append(dict(agency_id=a,name=names[a],group=group,group_rank=ranks.get((a,group)),
                        followup_rank=ranks.get((a,'final')),group_points=initial,followup_points=followup,points=initial+followup))
            return tuple(result)
