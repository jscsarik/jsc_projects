from .game_clock import regular_day
"""Final ranking and best-of-three playoffs, isolated from regular statistics."""
from collections import Counter
from contextlib import closing
from dataclasses import asdict,replace
import json,random,secrets,uuid

from .config import SKILLS
from .game_clock import current_game_date,DAYS_PER_SEASON
from .league import standings
from .match_service import MatchService
from .match_types import MatchInput,MatchTeam,MatchPlayer,MatchError,MatchResult,Judgment,UnresolvedMatch
from .match_engine import calculate_match,validate_input
from .match_policy import choose_representative
from .conditions import public_condition,commit_appearance_conditions,sync_rosters,promotion_allowed,risk_event,seed_for
from .condition_rules import injury_probability
from .special_engine import ContestInput,calculate_ranked_contest
from .lineup_planning import PublicFixture


def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)


def forfeit_lottery(agencies,seed):
    order=sorted(agencies);random.Random(seed_for(seed,'forfeit-lottery-v1')).shuffle(order);return order


def roster_change_reason(c,agency,*,fill_vacancy=False):
    day=current_game_date(c)
    if day is None:return '저장된 게임 날짜가 없습니다.'
    frozen=c.execute("SELECT 1 FROM final_contests WHERE season=? AND kind='tie' AND status!='completed'",(day.season,)).fetchone()
    if frozen:return '정규 시즌 종료 선수단을 사용하는 동률 결정전을 먼저 완료해 주세요.'
    if c.execute("SELECT 1 FROM final_contests WHERE absolute_day=? AND status='prepared' AND (json_extract(agencies_json,'$[0]')=? OR json_extract(agencies_json,'$[1]')=?)",(day.absolute_day,agency,agency)).fetchone():
        return '경기가 이미 시작되어 출전자와 선수단을 변경할 수 없습니다.'
    if fill_vacancy and day.is_preparation and not day.is_founding:
        count=c.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id=? AND career_status='first_team'",(agency,)).fetchone()[0]
        if count<5:return ''
    if day.weekday()==0:return ''
    if day.is_postseason and day.weekday()==4:
        for r in c.execute("SELECT * FROM final_contests WHERE absolute_day=? AND kind='post' AND game_number=3 AND status='scheduled'",(day.absolute_day,)):
            agencies=json.loads(r['agencies_json'])
            wins=Counter(json.loads(p[0])['order'][0] for p in c.execute("SELECT result_json FROM final_contests WHERE season=? AND kind='post' AND round_number=? AND status='completed'",(r['season'],r['round_number'])))
            if agency in agencies and all(wins[a]==1 for a in agencies):return ''
    return '월요일 또는 참가 중인 포스트시즌 1승 1패 금요일 최종전 시작 전에만 변경할 수 있습니다.'


class FinalsService:
    def prepare_current(self):
        """Repair a missing bracket only after the existing regular season is complete."""
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');day=current_game_date(c)
            if day and day.is_postseason and not c.execute('SELECT 1 FROM season_finals WHERE season=?',(day.season,)).fetchone():
                if day.week!=1 or day.weekday()!=0:raise MatchError('포스트시즌 대진이 누락되어 있습니다. 현재 날짜는 유지됩니다. 백업 복사본에서 진행 기록을 점검해 주세요.')
                self.ensure_started(c,day.season)

    def __init__(self,database,*,seed_factory=None):
        self.database=database;self.seed_factory=seed_factory or (lambda:secrets.randbits(128))
        self.lineup_policy=MatchService(database).lineup_policy

    @staticmethod
    def _content(c,season,rng):
        payload=json.loads(c.execute('SELECT rules_json FROM season_schedules WHERE season=?',(season,)).fetchone()[0])
        content=rng.choice(payload['contents']);return content,rng.randint(content['participants_min'],content['participants_max'])

    @staticmethod
    def _new_contest(c,season,kind,round_number,number,day,agencies):
        seed=secrets.randbits(128);rng=random.Random(seed)
        content,required=FinalsService._content(c,season,rng)
        c.execute('''INSERT INTO final_contests(id,season,kind,round_number,game_number,absolute_day,agencies_json,content_json,required)
            VALUES (?,?,?,?,?,?,?,?,?)''',(str(uuid.uuid4()),season,kind,round_number,number,day,dump(agencies),dump(content),required))

    @staticmethod
    def ensure_started(c,season):
        if c.execute('SELECT 1 FROM season_finals WHERE season=?',(season,)).fetchone():return
        if c.execute("SELECT 1 FROM scheduled_matches WHERE season=? AND status!='completed' UNION ALL SELECT 1 FROM special_events WHERE season=? AND status!='completed'",(season,season)).fetchone():
            raise MatchError('정규 585경기와 특별전 6회를 모두 완료해야 최종 순위를 확정할 수 있습니다.')
        table=standings(c,season);frozen={}
        for agency in (r['agency_id'] for r in table):
            players=MatchService._public_first_team(c,agency)
            leader=c.execute("SELECT person_id FROM squad_leaders WHERE agency_id=? AND squad='first_team'",(agency,)).fetchone()
            frozen[agency]=dict(players=[asdict(p) for p in players],leader=leader[0] if leader else None,
                injured=[p.id for p in players if public_condition(c,p.id,regular_day(season,24,6)).injured])
        c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (?,'ties',?,?)",(season,dump(frozen),dump(table)))
        groups={}
        for row in table:groups.setdefault(row['points'],[]).append(row['agency_id'])
        for i,agencies in enumerate(groups.values(),1):
            if len(agencies)>1:FinalsService._new_contest(c,season,'tie',i,1,(season-1)*224+182,agencies)
        FinalsService._seed(c,season)

    @staticmethod
    def _seed(c,season):
        if c.execute("SELECT 1 FROM final_contests WHERE season=? AND kind='tie' AND status!='completed'",(season,)).fetchone():return
        row=c.execute('SELECT * FROM season_finals WHERE season=?',(season,)).fetchone()
        if row['final_order_json']:return
        groups={}
        for r in json.loads(row['standings_json']):groups.setdefault(r['points'],[]).append(r['agency_id'])
        results={frozenset(json.loads(r['agencies_json'])):json.loads(r['result_json'])['order'] for r in c.execute("SELECT * FROM final_contests WHERE season=? AND kind='tie'",(season,))}
        order=[a for score in sorted(groups,reverse=True) for a in (results[frozenset(groups[score])] if len(groups[score])>1 else groups[score])]
        c.execute("UPDATE season_finals SET status='seeded',final_order_json=? WHERE season=?",(dump(order),season))
        c.execute("INSERT INTO season_honors VALUES (?,?,'regular_first')",(season,order[0]))
        for a in order[:4]:c.execute("INSERT INTO season_honors VALUES (?,?,'qualification')",(season,a))
        FinalsService._series(c,season,1,order[2],order[3])
        day=current_game_date(c)
        if day and day.is_postseason and day.week==1 and day.weekday()==0:
            from .conditions import forced_demotions,repair_ai_leaders
            forced_demotions(c,day.absolute_day);repair_ai_leaders(c,day.absolute_day)

    @staticmethod
    def _series(c,season,round_number,a,b):
        c.execute('INSERT INTO final_series VALUES (?,?,?,?,NULL)',(season,round_number,a,b))
        for game in (1,2):FinalsService._new_contest(c,season,'post',round_number,game,(season-1)*224+182+(round_number-1)*7+game+1,(a,b))

    def rows(self,*,today_only=True,season=None):
        with closing(self.database.connect()) as c:
            day=current_game_date(c)
            if day is None:return ()
            where='absolute_day=?' if today_only else 'season=?' if season is not None else '1=1'
            args=(day.absolute_day,) if today_only else (season,) if season is not None else ()
            query='SELECT * FROM final_contests WHERE '+where+' ORDER BY absolute_day,kind,round_number,game_number'
            return tuple(dict(r) for r in c.execute(query,args))

    def season_state(self,season=None):
        with closing(self.database.connect()) as c:
            day=current_game_date(c);season=season or (day.season if day else 1)
            row=c.execute('SELECT * FROM season_finals WHERE season=?',(season,)).fetchone()
            return dict(row) if row else None

    def _options(self,c,row,agency):
        day=row['absolute_day'];saved=c.execute('SELECT frozen_json FROM season_finals WHERE season=?',(row['season'],)).fetchone()
        if row['kind']=='tie':
            data=json.loads(saved[0])[agency]
            players=tuple(MatchPlayer(p['id'],p['agency_id'],p['name'],p['health'],tuple(p['skills'])) for p in data['players'])
            leader=data['leader'];injured=set(data['injured'])
        else:
            players=MatchService._public_first_team(c,agency);injured={p.id for p in players if public_condition(c,p.id,day).injured}
            leader_row=c.execute("SELECT person_id FROM squad_leaders WHERE agency_id=? AND squad='first_team'",(agency,)).fetchone()
            leader=leader_row[0] if leader_row else None
        conditions={p.id:public_condition(c,p.id,day) for p in players}
        if row['kind']=='tie':conditions={p:replace(v,penalty=0,last_day=None,streak=0,projected_days=1) for p,v in conditions.items()}
        return players,leader,injured,conditions

    def selection(self,identity):
        with closing(self.database.connect()) as c:
            row=c.execute('SELECT * FROM final_contests WHERE id=?',(identity,)).fetchone()
            if row is None:raise MatchError('포스트시즌/동률 결정전을 찾을 수 없습니다.')
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone();agency=player[0] if player else None
            if agency not in json.loads(row['agencies_json']):return (),0,None
            players,leader,injured,conditions=self._options(c,row,agency)
            paths=dict(c.execute('SELECT id,photo_path FROM people'))
            fixed=None
            if row['input_json']:
                data=json.loads(row['input_json']);team=next(t for t in data['teams'] if t['agency_id']==agency)
                fixed=tuple(p['id'] for p in team['players'])
            return tuple(dict(player=p,photo_path=paths.get(p.id,''),leader=p.id==leader,condition=conditions[p.id],available=p.id not in injured) for p in players),min(row['required'],len(players)-len(injured)),fixed

    def _prepare(self,c,row,lineups):
        if row['input_json']:
            data=json.loads(row['input_json'])
            if data.get('regular_random_pool') not in (None,'all8-v2'):raise MatchError('저장된 경기의 무작위 판정 규칙을 확인해 주세요.')
            if lineups:
                for team in data['teams']:
                    if team['agency_id'] in lineups and set(lineups[team['agency_id']])!={p['id'] for p in team['players']}:raise MatchError('시작한 경기의 출전자를 변경할 수 없습니다.')
            return data,json.loads(row['condition_json'])
        agencies=json.loads(row['agencies_json'])
        if set(lineups or {})-set(agencies):raise MatchError('참가 기획사만 출전자를 지정할 수 있습니다.')
        content=json.loads(row['content_json']);main=tuple(content['main_abilities'])
        from .match_service import ABILITY_NAMES
        main=tuple(ABILITY_NAMES[s] for s in main)
        teams=[];probabilities={};context={'public':{},'injury_probabilities':{}}
        for agency in agencies:
            if row['kind']=='post' and row['game_number']==3:self._manage_ai(c,row,agency)
            players,leader,injured,conditions=self._options(c,row,agency);eligible=tuple(p for p in players if p.id not in injured)
            count=min(row['required'],len(eligible))
            if lineups and agency in lineups:
                identities=tuple(lineups[agency]);by_id={p.id:p for p in eligible}
                if len(identities)!=count or len(set(identities))!=count or set(identities)-set(by_id):raise MatchError(f'출전 가능한 1군 {count}명을 중복 없이 선택해 주세요.')
                selected=tuple(by_id[p] for p in sorted(identities))
            else:
                future=[]
                if row['kind']=='post':
                    for nxt in c.execute("SELECT absolute_day,content_json,required,agencies_json FROM final_contests WHERE season=? AND kind='post' AND round_number=? AND absolute_day>? ORDER BY absolute_day",(row['season'],row['round_number'],row['absolute_day'])):
                        if agency in json.loads(nxt['agencies_json']):future.append(PublicFixture(nxt['absolute_day'],tuple(ABILITY_NAMES[s] for s in json.loads(nxt['content_json'])['main_abilities']),nxt['required']))
                selected=tuple(self.lineup_policy.select_for_match(eligible,row['required'],main,leader,conditions,row['absolute_day'],tuple(future)))
            if len(selected)!=count or len({p.id for p in selected})!=count or any(p not in eligible for p in selected):
                raise MatchError('출전 가능한 1군 인원과 선택 정책의 결과가 일치하지 않습니다. 선택 누락을 몰수로 처리하지 않습니다.')
            rep=choose_representative(selected,main,row['required'],leader,penalties={p:cond.penalty for p,cond in conditions.items()})
            teams.append(MatchTeam(agency,selected,leader,rep))
            for p in selected:
                probabilities[p.id]={s:p.value(s)/100*(1-conditions[p.id].penalty) for s in SKILLS}
                context['public'][p.id]=asdict(conditions[p.id]);context['injury_probabilities'][p.id]=injury_probability(p.health,conditions[p.id].registration_weeks,'match')
        match=MatchInput(row['id'],content['id'],row['required'],main,tuple(teams),probabilities)
        ids=[p.id for t in teams for p in t.players]
        if len(ids)!=len(set(ids)):raise MatchError('결정전 출전자가 중복되었습니다.')
        for team in teams[1:]:validate_input(replace(match,teams=(teams[0],team)))
        return dict(match.to_dict(),regular_random_pool='all8-v2'),context

    def _manage_ai(self,c,row,agency):
        player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
        if (player and agency==player[0]) or roster_change_reason(c,agency):return
        from .squads import SquadService
        from .match_service import ABILITY_NAMES
        content=json.loads(row['content_json']);main=tuple(ABILITY_NAMES[s] for s in content['main_abilities'])
        roster=SquadService._members(c,agency)
        eligible=[p for p in roster if p.squad in ('first_team','second_team') and not public_condition(c,p.id,row['absolute_day']).injured
                  and (p.squad=='first_team' or promotion_allowed(c,p.id,row['absolute_day']))]
        def value(p):
            condition=public_condition(c,p.id,row['absolute_day'])
            values=[getattr(p,s) for s in SKILLS]
            return (sum(values[SKILLS.index(s)] for s in main)*30/len(main)+sum(values[i] for i,s in enumerate(SKILLS) if s not in main)*30/(8-len(main)))*(1-condition.penalty)
        chosen=sorted(eligible,key=lambda p:(-value(p),-p.health,p.id))[:5]
        first={p.id for p in roster if p.squad=='first_team'}
        if len(chosen)<5:return
        desired={p.id for p in chosen}
        if desired!=first:
            c.executemany("UPDATE roster_memberships SET career_status='pro_pending' WHERE person_id=?",[(p,) for p in sorted(first-desired)])
            c.executemany("UPDATE roster_memberships SET career_status='first_team' WHERE person_id=?",[(p,) for p in sorted(desired-first)])
            c.executemany("UPDATE roster_memberships SET career_status='second_team' WHERE person_id=?",[(p,) for p in sorted(first-desired)])
            SquadService._validate_counts(c,agency);SquadService._bump(c,agency);sync_rosters(c,row['absolute_day'],'postseason_friday')
        for squad in ('first_team','second_team'):
            members=SquadService._members(c,agency);pool=[p for p in members if p.squad==squad]
            if pool:SquadService._set_leader(c,agency,squad,max(pool,key=lambda p:(p.leadership,p.health,p.id)).id)

    def play(self,identity,*,lineups=None):
        # Preparation is committed separately so restart reuses the exact seed,
        # lineup and probabilities; final result + injuries + bracket are atomic.
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM final_contests WHERE id=?',(identity,)).fetchone()
            if not row:raise MatchError('경기를 찾을 수 없습니다.')
            if row['status']=='completed':
                if lineups:self._prepare(c,row,lineups)
                return self._result(row)
            day=current_game_date(c)
            if not day or day.absolute_day!=row['absolute_day']:raise MatchError('현재 날짜의 결정전/포스트시즌 경기만 진행할 수 있습니다.')
            if c.execute("SELECT 1 FROM final_contests WHERE season=? AND absolute_day<? AND status!='completed'",(row['season'],day.absolute_day)).fetchone():raise MatchError('이전 결정전을 먼저 완료해 주세요.')
            data,context=self._prepare(c,row,lineups);seed=int(row['seed']) if row['seed'] else self.seed_factory()
            if type(seed) is not int or seed<0:raise MatchError('경기 난수 시드가 올바르지 않습니다.')
            c.execute("UPDATE final_contests SET status='prepared',input_json=?,condition_json=?,seed=? WHERE id=?",(dump(data),dump(context),str(seed),identity))
        match=MatchInput.from_dict(data)
        forfeits=[t.agency_id for t in match.teams if not t.players]
        lottery=[]
        if row['kind']=='tie' and len(forfeits)>1:
            lottery=forfeit_lottery(forfeits,seed)
        if len(match.teams)==2:
            result=(calculate_match(match,random.Random(seed)) if data.get('regular_random_pool')=='all8-v2'
                    else calculate_match(match,random.Random(seed),include_main_in_random=False));order=[result.winner_id,result.loser_id]
            if result.resolution=='double_forfeit':
                if row['kind']=='post':
                    with closing(self.database.connect()) as c:
                        ranks=json.loads(c.execute('SELECT final_order_json FROM season_finals WHERE season=?',(row['season'],)).fetchone()[0])
                    order=sorted(forfeits,key=ranks.index)
                else:order=lottery
                result=replace(result,resolution='forfeit',winner_id=order[0],loser_id=order[1],
                    teams=tuple(dict(t,outcome='win' if t['agency_id']==order[0] else 'loss',points=0) for t in result.teams))
            saved=result.summary()
        else:
            contest=ContestInput(identity,match.content_id,match.required,match.main_skills,match.teams,match.probabilities,
                {p.id:2 if p.id==t.leader_id else 0 for t in match.teams for p in t.players},60,tuple(t.agency_id for t in match.teams),{})
            result=calculate_ranked_contest(contest,random.Random(seed),support_pool=SKILLS if data.get('regular_random_pool')=='all8-v2' else None);order=[t['agency_id'] for t in result.teams if not t['forfeit']]+(lottery or forfeits);saved=result.summary()
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');latest=c.execute('SELECT * FROM final_contests WHERE id=?',(identity,)).fetchone()
            if latest['status']=='completed':return self._result(latest)
            if latest['input_json']!=dump(data) or latest['seed']!=str(seed):raise MatchError('경기 준비 저장이 변경되었습니다.')
            if current_game_date(c).absolute_day!=row['absolute_day']:raise MatchError('경기 중 날짜가 변경되었습니다.')
            saved['order']=order
            if row['kind']=='tie':saved['teams']=sorted((dict(t,rank=order.index(t['agency_id'])+1) for t in saved['teams']),key=lambda t:t['rank'])
            saved['forfeits']={a:'출전 가능한 1군 0명' for a in forfeits}
            saved['forfeit_policy']='higher_frozen_regular_seed' if row['kind']=='post' and len(forfeits)==2 else 'seeded_uniform_lottery' if lottery else 'normal'
            saved['lottery_order']=lottery
            saved['lottery_seed_label']='forfeit-lottery-v1' if lottery else None
            c.execute("UPDATE final_contests SET status='completed',result_json=?,events_json=? WHERE id=?",(dump(saved),dump([asdict(e) for e in result.events]),identity))
            if row['kind']=='post':
                commit_appearance_conditions(c,result.players,context,seed,row['absolute_day'],f'post:{identity}')
                self._advance_series(c,row,order[0])
            else:
                rng=random.Random(seed_for(seed,'tie-injury-v1'))
                for p in sorted(result.players,key=lambda p:p['person_id']):
                    if not p['base_attempts']:continue
                    person=p['person_id']
                    risk_event(c,key=f'tie:{identity}:{person}',person=person,day=row['absolute_day'],kind='match',
                        probability=context['injury_probabilities'][person],rng=rng,details={'contest_type':'tie','contest_id':identity,'fatigue_penalty':0})
                self._seed(c,row['season'])
            return self._result(c.execute('SELECT * FROM final_contests WHERE id=?',(identity,)).fetchone())

    @staticmethod
    def _result(row):
        return dict(summary=json.loads(row['result_json']),events=tuple(Judgment(**e) for e in json.loads(row['events_json'])),kind=row['kind'])

    def result(self,identity):
        with closing(self.database.connect()) as c:
            row=c.execute("SELECT * FROM final_contests WHERE id=? AND status='completed'",(identity,)).fetchone()
            return self._result(row) if row else None

    @staticmethod
    def _advance_series(c,row,winner):
        season,round_number=row['season'],row['round_number']
        wins=Counter(json.loads(r[0])['order'][0] for r in c.execute("SELECT result_json FROM final_contests WHERE season=? AND kind='post' AND round_number=? AND status='completed'",(season,round_number)))
        series=c.execute('SELECT * FROM final_series WHERE season=? AND round_number=?',(season,round_number)).fetchone()
        if wins[winner]<2:
            if row['game_number']==2:FinalsService._new_contest(c,season,'post',round_number,3,(season-1)*224+182+(round_number-1)*7+4,(series['agency_a'],series['agency_b']))
            return
        c.execute('UPDATE final_series SET winner_id=? WHERE season=? AND round_number=?',(winner,season,round_number))
        if round_number<3:
            order=json.loads(c.execute('SELECT final_order_json FROM season_finals WHERE season=?',(season,)).fetchone()[0])
            FinalsService._series(c,season,round_number+1,order[2-round_number],winner)
        else:
            c.execute("UPDATE season_finals SET status='completed',champion_id=? WHERE season=?",(winner,season))
            c.execute("INSERT OR IGNORE INTO season_honors VALUES (?,?,'champion')",(season,winner))
            regular=json.loads(c.execute('SELECT final_order_json FROM season_finals WHERE season=?',(season,)).fetchone()[0])
            losers=[]
            for s in c.execute('SELECT * FROM final_series WHERE season=? ORDER BY round_number DESC',(season,)):
                losers.append(s['agency_a'] if s['agency_b']==s['winner_id'] else s['agency_b'])
            c.execute('UPDATE season_finals SET playoff_order_json=? WHERE season=?',(dump([winner,*losers,*regular[4:]]),season))
            from .finance_service import close_season
            close_season(c,season,row['absolute_day'])
            from .awards import finalize,AwardError
            try:finalize(c,season)
            except AwardError:
                # Missing historical facts must not erase a completed final.
                # Awards UI reports the issue; offseason entry remains gated.
                pass

    def honors(self):
        with closing(self.database.connect()) as c:return tuple(dict(r) for r in c.execute('''SELECT a.id,a.name,
            SUM(h.kind='regular_first') regular_titles,SUM(h.kind='qualification') qualifications,SUM(h.kind='champion') trophies
            FROM agencies a LEFT JOIN season_honors h ON h.agency_id=a.id GROUP BY a.id ORDER BY a.name'''))
