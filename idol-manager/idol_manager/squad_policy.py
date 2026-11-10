"""Replaceable current-ability team composition policy, with no DB access."""
from itertools import combinations
from typing import Protocol, Sequence

from .squad_types import SquadMember, SquadPlan


class SquadPolicy(Protocol):
    def plan(self, members: Sequence[SquadMember]) -> SquadPlan: ...


class CoverageSquadPolicy:
    """Score quality + eight-skill coverage + health, evaluating all 16C5 teams."""
    def plan(self, members: Sequence[SquadMember]) -> SquadPlan:
        if not 5<=len(members)<=16 or len({member.id for member in members})!=len(members):
            raise ValueError("AI 최초 편성에는 중복 없는 프로 선수 5~16명이 필요합니다.")
        ordered = sorted(members,key=lambda member:member.id)

        def score(team):
            quality = sum(member.average for member in team) / 5
            coverage = sum(max(values) for values in zip(*(member.skill_values for member in team))) / 8
            health = sum(member.health for member in team) / 5
            age = sum(member.age for member in team) / 5
            return (0.60*quality + 0.35*coverage + 0.05*health,health,-age)

        first = max(combinations(ordered,5),key=score)
        ids = tuple(member.id for member in first)
        second = [member for member in ordered if member.id not in ids]
        def leader(team):
            return max(team,key=lambda member:(member.leadership,member.health,-member.age,member.id)).id if team else None
        return SquadPlan(ids,leader(first),leader(second))
