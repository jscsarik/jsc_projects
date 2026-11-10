"""Small deterministic beam search over this week's public fixtures only."""
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

from .config import SKILLS
from .condition_rules import projected_streak,fatigue_penalty


@dataclass(frozen=True)
class PublicFixture:
    absolute_day: int
    main_skills: tuple[str,...]
    participants: int


class WeeklyRosterPlanner(Protocol):
    """Future Monday optimizer interface; no implementation added in this stage."""
    def plan(self,public_members,public_schedule):...


def expected_success(player,main_skills,penalty,leader_id):
    others=tuple(s for s in SKILLS if s not in main_skills)
    base=30*sum(player.value(s) for s in main_skills)/len(main_skills)
    base+=30*sum(player.value(s) for s in others)/len(others)
    if player.id==leader_id:base+=2*player.value('leadership')
    return base/100*(1-penalty)


class ScheduleAwareLineup:
    beam_width=32

    def select(self,players,required,main_skills,leader_id):
        return tuple(sorted(players,key=lambda p:(-expected_success(p,main_skills,0,leader_id),-p.health,p.id))[:required])

    def select_for_match(self,players,required,main_skills,leader_id,conditions,day,future):
        players=tuple(sorted(players,key=lambda p:p.id))
        if not players:return ()
        last=tuple(conditions[p.id].last_day for p in players)
        streak=tuple(conditions[p.id].streak for p in players)
        # score,last_days,streaks,first_selection. No RNG, PA or opponent lineup.
        beam=[(0.0,last,streak,())]
        fixtures=(PublicFixture(day,main_skills,required),*future)
        for step,fixture in enumerate(fixtures):
            count=min(fixture.participants,len(players));choices=tuple(combinations(range(len(players)),count))
            candidates={}
            for total,last_days,streaks,first in beam:
                for selected in choices:
                    days=list(last_days);runs=list(streaks);score=total
                    for i in selected:
                        run=projected_streak(last_days[i],streaks[i],fixture.absolute_day)
                        score+=expected_success(players[i],fixture.main_skills,fatigue_penalty(run),leader_id)
                        days[i]=fixture.absolute_day;runs[i]=run
                    chosen=selected if step==0 else first
                    item=(score,tuple(days),tuple(runs),chosen)
                    key=(item[1],item[2])
                    old=candidates.get(key)
                    if old is None or self._rank(item,players)>self._rank(old,players):candidates[key]=item
            beam=sorted(candidates.values(),key=lambda x:self._rank(x,players),reverse=True)[:self.beam_width]
        return tuple(players[i] for i in beam[0][3])

    @staticmethod
    def _rank(item,players):
        return (round(item[0],10),sum(players[i].health for i in item[3]),tuple(-i for i in item[3]))
