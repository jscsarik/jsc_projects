from collections import Counter
from dataclasses import replace
import random
import unittest

from idol_manager.config import SKILLS
from idol_manager.match_engine import calculate_match
from idol_manager.match_policy import ExpectedSuccessLineup, choose_representative, choose_award
from idol_manager.match_types import MatchInput, MatchTeam, MatchPlayer, MatchError, UnresolvedMatch
from idol_manager.match_service import ABILITY_NAMES
from idol_manager.season_schedule import load_schedule_rules


def player(identity, agency, values=50, health=80):
    return MatchPlayer(identity, agency, identity, health, (values,)*8 if isinstance(values, int) else tuple(values))


def match_input(values_a=50, values_b=50, count=1, main=('vocal', 'dance'), leaders=True):
    a = tuple(player(f'a{i}', 'a', values_a) for i in range(count))
    b = tuple(player(f'b{i}', 'b', values_b) for i in range(count))
    return MatchInput('m', 'content-01', count, main,
                      (MatchTeam('a', a, a[0].id if leaders and a else None, a[0].id if a else None),
                       MatchTeam('b', b, b[0].id if leaders and b else None, b[0].id if b else None)),
                      {p.id: {s: p.value(s)/100 for s in SKILLS} for p in a+b})


class ScriptedRandom:
    def __init__(self, rolls):
        self.rolls = iter(rolls)

    def random(self):
        return next(self.rolls)

    def choice(self, values):
        return values[0]


class MatchEngineTests(unittest.TestCase):
    def test_exact_60_main_30_support_30_two_and_three_main_skills(self):
        for main in (('vocal','dance'), ('vocal','dance','rap')):
            result = calculate_match(match_input(count=5, main=main), random.Random(3))
            for stats in result.players:
                events = [e for e in result.events if e.person_id == stats['person_id']]
                basic = [e for e in events if e.phase in ('main','support')]
                self.assertEqual(len(basic), 60)
                self.assertEqual(Counter(e.skill for e in basic if e.phase == 'main'), {s:30//len(main) for s in main})
                support = [e for e in basic if e.phase == 'support']
                self.assertEqual(len(support), 30)
                self.assertTrue(set(e.skill for e in support)<=set(SKILLS))
                self.assertTrue(set(e.skill for e in support)&set(main))
                self.assertEqual({e.tick for e in basic}, set(range(1,61)))
            self.assertEqual(sum(e.phase == 'leader' for e in result.events), 4)

    def test_support_draws_are_independent_with_replacement(self):
        result = calculate_match(match_input(100, 0, leaders=False), ScriptedRandom([0.5]*120))
        support = [e for e in result.events if e.phase == 'support']
        self.assertEqual(len(support), 60)
        self.assertEqual({e.skill for e in support}, {'vocal'})

    def test_all_thirty_confirmed_contents_get_exact_main_distribution(self):
        for content in load_schedule_rules().contents:
            with self.subTest(content=content.name):
                main = tuple(ABILITY_NAMES[s] for s in content.main_abilities)
                source = match_input(100,0,count=content.participants_max,main=main)
                result = calculate_match(source,random.Random(17))
                for stats in result.players:
                    events = [e for e in result.events if e.person_id==stats['person_id'] and e.phase=='main']
                    self.assertEqual(Counter(e.skill for e in events),{s:30//len(main) for s in main})

    def test_probability_zero_and_hundred_health_does_not_add_successes(self):
        source = match_input(100, 0)
        result = calculate_match(source, random.Random(1))
        self.assertEqual(result.winner_id, 'a')
        self.assertEqual([t['total_score'] for t in result.teams], [62,0])
        self.assertTrue(all(e.success == (e.agency_id == 'a') for e in result.events))
        changed = replace(source, teams=tuple(replace(t, players=tuple(replace(p, health=0) for p in t.players)) for t in source.teams))
        self.assertEqual(result, calculate_match(changed, random.Random(1)))

    def test_leader_only_participating_leader_two_extra_separate_from_60(self):
        source = match_input(100, 0, count=2)
        source = replace(source, teams=(source.teams[0], replace(source.teams[1], leader_id='not-playing')))
        result = calculate_match(source, random.Random(4))
        extra = [e for e in result.events if e.phase == 'leader']
        self.assertEqual(len(extra), 2)
        self.assertEqual({e.person_id for e in extra}, {'a0'})
        self.assertEqual(sum(p['base_attempts'] for p in result.players), 240)
        self.assertEqual(sum(p['leader_attempts'] for p in result.players), 2)

    def test_tied_base_deathmatch_repeats_ten_each_no_leader_bonus(self):
        result = calculate_match(match_input(leaders=False), ScriptedRandom([.9]*140 + [0,.9]*10))
        self.assertEqual(result.resolution, 'deathmatch')
        self.assertEqual(result.winner_id, 'a')
        self.assertEqual(len([e for e in result.events if e.phase == 'deathmatch']), 40)
        self.assertEqual(Counter((e.person_id,e.round_number) for e in result.events if e.phase == 'deathmatch'),
                         {('a0',1):10, ('b0',1):10, ('a0',2):10, ('b0',2):10})
        self.assertTrue(all(e.skill in ('vocal','dance') for e in result.events if e.phase == 'deathmatch'))
        self.assertEqual([p['base_attempts'] for p in result.players], [60,60])

    def test_deathmatch_missing_representative_and_infinite_tie_fail_without_winner(self):
        source = match_input(leaders=False)
        missing = replace(source, teams=(replace(source.teams[0], representative_id=None),source.teams[1]))
        with self.assertRaisesRegex(UnresolvedMatch, '대표'):
            calculate_match(missing, ScriptedRandom([.9]*120))
        with self.assertRaises(UnresolvedMatch):
            calculate_match(match_input(0,0), random.Random(1))
        with self.assertRaises(UnresolvedMatch):
            calculate_match(match_input(100,100), random.Random(1))
        with self.assertRaisesRegex(UnresolvedMatch, '2회'):
            calculate_match(source, ScriptedRandom([.9]*160), max_deathmatch_rounds=2)

    def test_five_required_prefers_participating_leader_representative(self):
        people = (player('weak', 'a', 10), player('strong', 'a', 95))
        self.assertEqual(choose_representative(people, ('vocal','dance'), 5, 'weak'), 'weak')
        self.assertEqual(choose_representative(people, ('vocal','dance'), 2, 'weak'), 'strong')
        self.assertEqual(choose_representative(people, ('vocal','dance'), 5, 'absent'), 'strong')
        self.assertIsNone(choose_representative((), ('vocal','dance'), 5, None))

    def test_forfeit_and_double_forfeit_no_invented_player_appearances(self):
        source = match_input()
        for empty_sides, winner in (((0,), 'b'), ((1,), 'a'), ((0,1), None)):
            with self.subTest(empty_sides=empty_sides):
                modified = replace(source, teams=tuple(replace(t, players=(), representative_id=None) if i in empty_sides else t
                                                       for i,t in enumerate(source.teams)))
                result = calculate_match(modified, random.Random(1))
                self.assertEqual(result.winner_id, winner)
                self.assertEqual(result.resolution, 'double_forfeit' if winner is None else 'forfeit')
                self.assertEqual(sum(t['points'] for t in result.teams), int(winner is not None))
                self.assertEqual(result.events, ())
                self.assertEqual(result.players, ())

    def test_short_handed_actual_players_only_get_sixty_each(self):
        source = match_input(100,0,count=5)
        source = replace(source, teams=(replace(source.teams[0], players=source.teams[0].players[:2]), source.teams[1]))
        result = calculate_match(source, random.Random(1))
        self.assertEqual(len(result.players), 7)
        self.assertEqual(sum(p['base_attempts'] for p in result.players), 7*60)

    def test_ai_expected_score_uses_major_and_support_leader_bonus_health_tiebreak(self):
        specialist = player('s', 'a', (100,100,40,40,40,40,40,40), health=1)
        balanced = player('b', 'a', 65, health=100)
        policy = ExpectedSuccessLineup()
        self.assertEqual(policy.select((balanced,specialist),1,('vocal','dance'),None), (specialist,))
        twins = (player('x','a',50,50),player('y','a',50,80))
        self.assertEqual(policy.select(twins,1,('vocal','dance'),None)[0].id,'y')
        self.assertEqual(policy.select(twins,1,('vocal','dance'),'x')[0].id,'x')

    def test_awards_use_general_events_only_and_seeded_tie_policy(self):
        result = calculate_match(match_input(100,0,count=3), random.Random(15))
        winners = [p for p in result.players if p['winning_idol']]
        losers = [p for p in result.players if p['losing_idol']]
        self.assertEqual(len(winners),1)
        self.assertEqual(len(losers),1)
        self.assertEqual(winners[0]['base_successes'],60)
        self.assertEqual(losers[0]['base_failures'],60)
        self.assertEqual(choose_award(['z','a'],random.Random(4)), choose_award(['a','z'],random.Random(4)))
        self.assertEqual(result, calculate_match(match_input(100,0,count=3), random.Random(15)))

    def test_bad_probabilities_duplicate_players_invalid_main_rejected(self):
        source = match_input()
        for modified in (replace(source, main_skills=('vocal',)),
                         replace(source, teams=(source.teams[0], source.teams[0])),
                         replace(source, probabilities={'a0':{'vocal':float('nan')}})):
            with self.assertRaises(MatchError):
                calculate_match(modified,random.Random(1))

    def test_serialization_round_trip_has_only_public_inputs(self):
        source = match_input()
        self.assertEqual(source, MatchInput.from_dict(source.to_dict()))
        self.assertNotIn('potential', repr(source.to_dict()))
        self.assertNotIn('archetype', repr(source.to_dict()))


if __name__ == '__main__':
    unittest.main()
