"""Shared basic trials for regular 60-tick and special 30-tick contests."""
from .config import SKILLS
from .match_types import Judgment,MatchError


def judge(events,probabilities,rng,player,phase,skill,tick,round_number,attempt):
    chance=probabilities[player.id][skill];roll=rng.random()
    if not 0<=roll<1:raise MatchError('난수 값이 올바르지 않습니다.')
    event=Judgment(len(events)+1,player.agency_id,player.id,phase,skill,tick,round_number,attempt,chance,roll,roll<chance)
    events.append(event)
    return int(event.success)


def basic_trials(teams,main_skills,probabilities,rng,events,attempts,*,support_pool=None,teamwork=None):
    from .teamwork import bonus_rng,trial
    extra_rng=bonus_rng(rng) if teamwork is not None and any(len(t.players)>=3 and any(p.franchise for p in t.players) for t in teams) else None
    scores={t.agency_id:0 for t in teams};half=attempts//2
    # Default remains the historical special-event rule. Regular/finals callers
    # explicitly pass all eight; each choice is independent with replacement.
    support=tuple(s for s in SKILLS if s not in main_skills) if support_pool is None else tuple(support_pool)
    if not support or any(s not in SKILLS for s in support) or len(set(support))!=len(support):raise MatchError('무작위 판정 능력치 구성이 올바르지 않습니다.')
    for tick in range(1,attempts+1):
        for team in teams:
            successes=[]
            for player in team.players:
                phase='main' if tick<=half else 'support'
                skill=main_skills[(tick-1)%len(main_skills)] if tick<=half else rng.choice(support)
                success=judge(events,probabilities,rng,player,phase,skill,tick,0,tick if tick<=half else tick-half)
                successes.append(success);scores[team.agency_id]+=success
            if teamwork is not None:
                bonus=trial(team,successes,tick,len(events),extra_rng)
                if bonus is not None:teamwork.append(bonus);scores[team.agency_id]+=int(bonus['success'])
    return scores
