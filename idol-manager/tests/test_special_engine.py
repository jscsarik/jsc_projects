from collections import Counter
from dataclasses import replace
import random
import unittest

from idol_manager.config import SKILLS
from idol_manager.match_types import MatchPlayer,MatchTeam,UnresolvedMatch,MatchError
from idol_manager.special_engine import ContestInput,SPECIAL_MAIN,calculate_contest,stage_points


def contest(*,final=False,players=2):
    teams=[];probabilities={};leaders={}
    for agency in range(4 if final else 5):
        identity=f'a{agency}'
        people=tuple(MatchPlayer(f'{identity}-p{i}',identity,f'선수{i}',80,(60,)*8) for i in range(players))
        for p in people:probabilities[p.id]={s:.6 for s in SKILLS}
        if people:
            leaders[people[0].id]=2
            if len(people)>1:leaders[people[1].id]=1
        teams.append(MatchTeam(identity,people,people[0].id if people else None,people[0].id if people else None))
    return ContestInput('test','content',min(5,players) if final else 10,('vocal','dance','rap'),tuple(teams),probabilities,leaders,60 if final else 30,tuple(t.agency_id for t in teams),{})


class SpecialEngineTests(unittest.TestCase):
    def test_three_confirmed_types(self):
        self.assertEqual(SPECIAL_MAIN,{'대학축제':('entertainment','appearance','physique'),
            'K-POP 페스티벌':('vocal','dance','rap'),'아이돌 체육대회':('leadership','entertainment','physique')})

    def test_group_thirty_fifteen_main_fifteen_support_and_both_leaders(self):
        data=contest();result=calculate_contest(data,random.Random(7))
        for p in result.players:
            self.assertEqual((p['base_attempts'],p['main_attempts'],p['support_attempts']),(30,15,15))
            main=Counter(e.skill for e in result.events if e.person_id==p['person_id'] and e.phase=='main')
            self.assertEqual(main,{'vocal':5,'dance':5,'rap':5})
            self.assertEqual(p['leader_attempts'],2 if p['person_id'].endswith('p0') else 1)
            self.assertTrue(all(e.skill not in data.main_skills for e in result.events if e.person_id==p['person_id'] and e.phase=='support'))
        self.assertEqual({t['rank'] for t in result.teams},set(range(1,6)))

    def test_final_sixty_two_and_three_main_distributions(self):
        for main in (('vocal','dance'),('vocal','dance','rap')):
            data=replace(contest(final=True),main_skills=main)
            result=calculate_contest(data,random.Random(8))
            for p in result.players:
                self.assertEqual((p['base_attempts'],p['main_attempts'],p['support_attempts']),(60,30,30))
                counts=Counter(e.skill for e in result.events if e.person_id==p['person_id'] and e.phase=='main')
                self.assertEqual(counts,{s:30//len(main) for s in main})
        self.assertEqual({t['rank'] for t in result.teams},{1,2,3,4})

    def test_absent_leaders_no_bonus(self):
        data=replace(contest(),leader_attempts={})
        result=calculate_contest(data,random.Random(2))
        self.assertFalse(any(e.phase=='leader' for e in result.events))

    def test_tied_agencies_only_repeat_ten_actual_representative_attempts(self):
        data=replace(contest(players=1),leader_attempts={})
        data=replace(data,probabilities={p:{s:.5 for s in SKILLS} for p in data.probabilities})
        rolls=[.9]*150
        for attempt in range(1,11):
            for success in (8,8,6,3,1):rolls.append(.1 if attempt<=success else .9)
        for attempt in range(1,11):
            for success in (7,2):rolls.append(.1 if attempt<=success else .9)
        class Scripted:
            def random(self):return next(self.rolls)
            def choice(self,items):return items[0]
        rng=Scripted();rng.rolls=iter(rolls)
        result=calculate_contest(data,rng)
        self.assertEqual([t['agency_id'] for t in result.teams],['a0','a1','a2','a3','a4'])
        dm=[e for e in result.events if e.phase=='deathmatch']
        self.assertEqual(len(dm),70)
        self.assertEqual({e.agency_id for e in dm if e.round_number==2},{'a0','a1'})
        self.assertTrue(all(p['base_attempts']==30 for p in result.players))

    def test_unresolvable_tie_is_not_fabricated(self):
        data=contest(players=1)
        data=replace(data,leader_attempts={},probabilities={p:{s:0 for s in SKILLS} for p in data.probabilities})
        with self.assertRaises(UnresolvedMatch):calculate_contest(data,random.Random(0))
        data=replace(data,probabilities={p:{s:.5 for s in SKILLS} for p in data.probabilities})
        class Same:
            def random(self):return .5
            def choice(self,items):return items[0]
        with self.assertRaises(UnresolvedMatch):calculate_contest(data,Same(),max_tiebreak_rounds=3)

    def test_probability_zero_and_one_and_deterministic_replay(self):
        data=contest(players=1)
        values=(0,1,.3,.5,.7)
        data=replace(data,probabilities={p.id:{s:values[i] for s in SKILLS} for i,t in enumerate(data.teams) for p in t.players})
        result=calculate_contest(data,random.Random(4))
        self.assertTrue(all(not e.success for e in result.events if e.probability==0))
        self.assertTrue(all(e.success for e in result.events if e.probability==1))
        self.assertEqual(result,calculate_contest(ContestInput.from_dict(data.to_dict()),random.Random(4)))

    def test_multiple_forfeits_below_actual_participants_no_fake_trials(self):
        data=contest(players=1)
        teams=tuple(replace(t,players=(),representative_id=None) if i in (0,2) else t for i,t in enumerate(data.teams))
        result=calculate_contest(replace(data,teams=teams),random.Random(6))
        self.assertEqual([t['agency_id'] for t in result.teams[-2:]],['a0','a2'])
        self.assertTrue(all(t['forfeit'] for t in result.teams[-2:]))
        self.assertFalse(any(e.agency_id in ('a0','a2') for e in result.events))
        empty=calculate_contest(contest(players=0),random.Random(3))
        self.assertFalse(empty.players);self.assertFalse(empty.events)
        self.assertEqual(stage_points('upper',empty.teams,{}),{f'a{i}':0 for i in range(5)})

    def test_all_stage_points_and_final_origins(self):
        teams=tuple(dict(agency_id=f'a{i}',rank=i+1,forfeit=False) for i in range(5))
        groups={'upper':['a0','a1','a2','a3','a4'],'lower':['a5','a6','a7','a8','a9']}
        self.assertEqual(list(stage_points('upper',teams,groups).values()),[2,1,0,0,0])
        self.assertEqual(list(stage_points('lower',teams,groups).values()),[0,0,0,0,-2])
        final=tuple(dict(agency_id=a,rank=i+1,forfeit=False) for i,a in enumerate(('a5','a3','a6','a4')))
        self.assertEqual(stage_points('final',final,groups),{'a5':2,'a3':0,'a6':0,'a4':-2})

    def test_validation_rejects_duplicate_players(self):
        data=contest()
        with self.assertRaises(MatchError):calculate_contest(replace(data,teams=(data.teams[0],)*5),random.Random(1))
