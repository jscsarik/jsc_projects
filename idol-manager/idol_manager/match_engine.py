"""Pure regular-match calculation; the supplied RNG makes every event replayable."""
import math
from .config import SKILLS
from .match_types import Judgment, MatchError, MatchResult, UnresolvedMatch
from .match_policy import choose_award
from .judgments import judge as shared_judge,basic_trials

LEGACY_ENGINE_VERSION = 'regular-1'
ENGINE_VERSION = 'regular-2-all8'
SUPPORTED_ENGINE_VERSIONS = (LEGACY_ENGINE_VERSION,ENGINE_VERSION)
MAX_DEATHMATCH_ROUNDS = 1000


def validate_input(match):
    if len(match.main_skills) not in (2, 3) or len(set(match.main_skills)) != len(match.main_skills) or any(s not in SKILLS for s in match.main_skills):
        raise MatchError('콘텐츠 주요 능력치가 올바르지 않습니다.')
    if len(match.teams) != 2 or len({t.agency_id for t in match.teams}) != 2 or not 1 <= match.required <= 5:
        raise MatchError('경기 참가 기획사 또는 출전 인원이 올바르지 않습니다.')
    identities = set()
    for team in match.teams:
        if len(team.players) > match.required:
            raise MatchError('필요 출전 인원을 초과했습니다.')
        for player in team.players:
            if player.id in identities or player.agency_id != team.agency_id or len(player.skills) != 8 or any(type(v) is not int or not 0 <= v <= 100 for v in player.skills):
                raise MatchError('중복 출전자 또는 올바르지 않은 공개 능력치입니다.')
            identities.add(player.id)
            for skill in SKILLS:
                chance = match.probabilities.get(player.id, {}).get(skill)
                if not isinstance(chance, (int, float)) or not math.isfinite(chance) or not 0 <= chance <= 1:
                    raise MatchError('판정 성공 확률은 0~1이어야 합니다.')
        if team.representative_id is not None and team.representative_id not in {p.id for p in team.players}:
            raise MatchError('데스매치 대표는 실제 출전자여야 합니다.')


def calculate_match(match, rng, *, max_deathmatch_rounds=MAX_DEATHMATCH_ROUNDS,include_main_in_random=True):
    validate_input(match)
    events = []
    teamwork=[]
    teams = match.teams
    scores = {t.agency_id: 0 for t in teams}
    dm_scores = dict(scores)
    empty = [not t.players for t in teams]
    resolution = 'normal'
    winner = loser = None

    def judge(player, phase, skill, tick, round_number, attempt):
        return shared_judge(events,match.probabilities,rng,player,phase,skill,tick,round_number,attempt)

    if any(empty):
        # No contest took place: no invented trials or player appearances.
        resolution = 'double_forfeit' if all(empty) else 'forfeit'
        if not all(empty):
            winner, loser = teams[int(empty[0])].agency_id, teams[int(not empty[0])].agency_id
    else:
        scores=basic_trials(teams,match.main_skills,match.probabilities,rng,events,60,
                            support_pool=SKILLS if include_main_in_random else None,teamwork=teamwork)
        for team in teams:
            for player in team.players:
                if player.id == team.leader_id:
                    for attempt in (1, 2):
                        scores[team.agency_id] += judge(player, 'leader', 'leadership', 60, 0, attempt)
        if len(set(scores.values())) == 1:
            resolution = 'deathmatch'
            reps = [next((p for p in t.players if p.id == t.representative_id), None) for t in teams]
            if any(p is None for p in reps):
                raise UnresolvedMatch('동점 경기의 실제 출전자 대표가 없습니다. 결과를 확정하지 않았습니다.')
            probabilities = [[match.probabilities[p.id][s] for s in match.main_skills] for p in reps]
            if all(all(v == probabilities[0][0] for v in values) for values in probabilities) and probabilities[0][0] in (0, 1):
                raise UnresolvedMatch('양측 대표가 항상 같은 결과를 내므로 데스매치 승자를 결정할 수 없습니다.')
            for number in range(1, max_deathmatch_rounds + 1):
                for attempt in range(1, 11):
                    for player in reps:
                        skill = rng.choice(match.main_skills)
                        dm_scores[player.agency_id] += judge(player, 'deathmatch', skill, attempt, number, attempt)
                if len(set(dm_scores.values())) != 1:
                    break
            else:
                raise UnresolvedMatch(f'데스매치 {max_deathmatch_rounds}회 반복 후에도 동점입니다. 임의 승자를 만들지 않았습니다.')
        winner = max(scores, key=lambda a: scores[a] + dm_scores[a])
        loser = next(a for a in scores if a != winner)

    stats = []
    for team in teams:
        for player in team.players if not any(empty) else ():
            own = [e for e in events if e.person_id == player.id]
            basic = [e for e in own if e.phase in ('main', 'support')]
            leader = [e for e in own if e.phase == 'leader']
            dm = [e for e in own if e.phase == 'deathmatch']
            successes = sum(e.success for e in basic)
            leader_success = sum(e.success for e in leader)
            stats.append(dict(person_id=player.id, agency_id=team.agency_id, content_id=match.content_id,
                              base_attempts=len(basic), base_successes=successes, base_failures=len(basic)-successes,
                              main_attempts=30, support_attempts=30, leader_attempts=len(leader), leader_successes=leader_success,
                              deathmatch_attempts=len(dm), deathmatch_successes=sum(e.success for e in dm),
                              success_rate=(successes+leader_success)/(len(basic)+len(leader)),
                              base_success_rate=successes/len(basic), outcome='win' if team.agency_id == winner else 'loss',
                              winning_idol=False, losing_idol=False))
    for agency, field, metric in ((winner, 'winning_idol', 'base_successes'), (loser, 'losing_idol', 'base_failures')):
        candidates = [p for p in stats if p['agency_id'] == agency]
        best = max((p[metric] for p in candidates), default=None)
        chosen = choose_award([p['person_id'] for p in candidates if p[metric] == best], rng)
        for player in candidates:
            player[field] = player['person_id'] == chosen
    team_stats = tuple(dict(agency_id=t.agency_id, base_score=scores[t.agency_id], deathmatch_score=dm_scores[t.agency_id],
                           total_score=scores[t.agency_id]+dm_scores[t.agency_id], outcome='win' if t.agency_id == winner else 'loss',
                           points=int(t.agency_id == winner), forfeit=empty[i],teamwork_score=sum(b['success'] for b in teamwork if b['agency_id']==t.agency_id)) for i, t in enumerate(teams))
    return MatchResult(match.match_id, resolution, winner, loser, team_stats, tuple(stats), tuple(events),tuple(teamwork))
