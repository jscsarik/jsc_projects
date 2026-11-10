"""Pure multi-agency ranking. No Qt, database, roster edits or hidden data."""
from collections import Counter
from dataclasses import dataclass,asdict
import math

from .config import SKILLS
from .match_types import MatchTeam,MatchPlayer,Judgment,MatchError,UnresolvedMatch
from .judgments import judge,basic_trials

ENGINE_VERSION='special-1'
SPECIAL_MAIN={
    '대학축제':('entertainment','appearance','physique'),
    'K-POP 페스티벌':('vocal','dance','rap'),
    '아이돌 체육대회':('leadership','entertainment','physique'),
}


@dataclass(frozen=True)
class ContestInput:
    round_id:str
    content_id:str
    required:int
    main_skills:tuple
    teams:tuple
    probabilities:dict
    leader_attempts:dict
    base_attempts:int
    seed_order:tuple
    conditions:dict

    def to_dict(self):
        from .match_types import input_dict
        return input_dict(self)

    @classmethod
    def from_dict(cls,data):
        teams=tuple(MatchTeam(t['agency_id'],tuple(MatchPlayer(p['id'],p['agency_id'],p['name'],p['health'],tuple(p['skills']),p.get('franchise',False)) for p in t['players']),t['leader_id'],t['representative_id']) for t in data['teams'])
        return cls(data['round_id'],data['content_id'],data['required'],tuple(data['main_skills']),teams,
                   data['probabilities'],data['leader_attempts'],data['base_attempts'],tuple(data['seed_order']),data['conditions'])


@dataclass(frozen=True)
class ContestResult:
    round_id:str
    teams:tuple
    players:tuple
    events:tuple
    teamwork:tuple=()

    def summary(self):return {'round_id':self.round_id,'teams':self.teams,'players':self.players,'teamwork':self.teamwork}


def validate_contest(contest):
    if contest.base_attempts not in (30,60) or len(contest.teams) not in (4,5):raise MatchError('특별전 판정 구성 오류입니다.')
    if (len(contest.teams),contest.base_attempts) not in ((5,30),(4,60)):raise MatchError('그룹은 5개 기획사 30회, 후속은 4개 기획사 60회 판정입니다.')
    main=contest.main_skills
    if len(main) not in (2,3) or len(set(main))!=len(main) or any(s not in SKILLS for s in main):raise MatchError('특별전 주요 능력치 오류입니다.')
    if contest.base_attempts==30 and len(main)!=3:raise MatchError('5자 대결은 주요 능력치 3종이 필요합니다.')
    agencies=[t.agency_id for t in contest.teams]
    if len(set(agencies))!=len(agencies) or set(agencies)!=set(contest.seed_order):raise MatchError('특별전 기획사 중복 또는 순위 정보 오류입니다.')
    if not 1<=contest.required<=(10 if contest.base_attempts==30 else 5):raise MatchError('특별전 출전 인원 오류입니다.')
    seen=set()
    for team in contest.teams:
        if len(team.players)>contest.required:raise MatchError('특별전 출전 정원을 초과했습니다.')
        for p in team.players:
            if p.id in seen or p.agency_id!=team.agency_id or len(p.skills)!=8 or any(type(v) is not int or not 0<=v<=100 for v in p.skills):raise MatchError('특별전 출전자 정보 오류입니다.')
            seen.add(p.id)
            if contest.leader_attempts.get(p.id,0) not in (0,1,2):raise MatchError('리더 추가 판정 오류입니다.')
            for skill in SKILLS:
                chance=contest.probabilities.get(p.id,{}).get(skill)
                if not isinstance(chance,(float,int)) or not math.isfinite(chance) or not 0<=chance<=1:raise MatchError('특별전 확률 오류입니다.')
        if team.players and team.representative_id not in {p.id for p in team.players}:raise MatchError('실제 출전자 대표가 필요합니다.')


def calculate_contest(contest,rng,*,max_tiebreak_rounds=1000):
    validate_contest(contest)
    return calculate_ranked_contest(contest,rng,max_tiebreak_rounds=max_tiebreak_rounds)


def calculate_ranked_contest(contest,rng,*,max_tiebreak_rounds=1000,support_pool=None):
    """Shared trials/rank resolution; callers validate their contest format."""
    events=[];teams=contest.teams
    teamwork=[]
    scores=basic_trials(teams,contest.main_skills,contest.probabilities,rng,events,contest.base_attempts,support_pool=support_pool,teamwork=teamwork)
    for team in teams:
        for player in team.players:
            for attempt in range(1,contest.leader_attempts.get(player.id,0)+1):
                scores[team.agency_id]+=judge(events,contest.probabilities,rng,player,'leader','leadership',contest.base_attempts,0,attempt)
    dm={t.agency_id:0 for t in teams};round_number=0
    representatives={t.agency_id:next((p for p in t.players if p.id==t.representative_id),None) for t in teams}

    def resolve(tied):
        nonlocal round_number
        if len(tied)<=1:return tied
        # A round is local to this tied rank block. Teams separated by an
        # earlier block cannot leapfrog one another with later trial totals.
        values={a:[] for a in tied}
        for a in tied:
            values[a]=[contest.probabilities[representatives[a].id][s] for s in contest.main_skills]
        flat=[v for row in values.values() for v in row]
        if len(set(flat))==1 and flat[0] in (0,1):raise UnresolvedMatch('동률 대표들이 항상 같은 결과를 냅니다. 임의 순위를 만들지 않았습니다.')
        for _ in range(max_tiebreak_rounds):
            round_number+=1;local={a:0 for a in tied}
            for attempt in range(1,11):
                for agency in tied:
                    p=representatives[agency];skill=rng.choice(contest.main_skills)
                    success=judge(events,contest.probabilities,rng,p,'deathmatch',skill,attempt,round_number,attempt)
                    local[agency]+=success;dm[agency]+=success
            buckets={}
            for a in tied:buckets.setdefault(local[a],[]).append(a)
            if len(buckets)>1:
                return [a for score in sorted(buckets,reverse=True) for a in resolve(buckets[score])]
        raise UnresolvedMatch('특별전 동률 추가 판정 반복 한도에 도달했습니다. 결과는 확정되지 않았습니다.')

    buckets={}
    for t in teams:
        if t.players:buckets.setdefault(scores[t.agency_id],[]).append(t.agency_id)
    order=[a for score in sorted(buckets,reverse=True) for a in resolve(buckets[score])]
    # No fake representatives or trials for forfeiting agencies.
    order.extend(a for a in contest.seed_order if representatives[a] is None)
    team_stats=tuple(dict(agency_id=a,rank=i+1,base_score=scores[a],tiebreak_score=dm[a],forfeit=representatives[a] is None,teamwork_score=sum(b['success'] for b in teamwork if b['agency_id']==a)) for i,a in enumerate(order))
    players=[]
    for team in teams:
        for p in team.players:
            own=[e for e in events if e.person_id==p.id]
            basic=[e for e in own if e.phase in ('main','support')];leaders=[e for e in own if e.phase=='leader'];tie=[e for e in own if e.phase=='deathmatch']
            success=sum(e.success for e in basic);bonus=sum(e.success for e in leaders)
            players.append(dict(person_id=p.id,agency_id=team.agency_id,content_id=contest.content_id,
                base_attempts=len(basic),base_successes=success,base_failures=len(basic)-success,
                main_attempts=contest.base_attempts//2,support_attempts=contest.base_attempts//2,
                leader_attempts=len(leaders),leader_successes=bonus,deathmatch_attempts=len(tie),deathmatch_successes=sum(e.success for e in tie),
                success_rate=(success+bonus)/(len(basic)+len(leaders))))
    return ContestResult(contest.round_id,team_stats,tuple(players),tuple(events),tuple(teamwork))


def stage_points(stage,teams,groups):
    result={}
    for team in teams:
        a,rank=team['agency_id'],team['rank'];delta=0
        if stage=='upper':delta={1:2,2:1}.get(rank,0)
        elif stage=='lower' and rank==5:delta=-2
        elif stage=='final':
            if rank==1 and a in groups['lower']:delta=2
            elif rank==4 and a in groups['upper']:delta=-2
        if team['forfeit'] and delta>0:delta=0
        result[a]=delta
    return result
