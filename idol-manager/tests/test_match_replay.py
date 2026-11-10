from collections import Counter
from dataclasses import replace
import random
import unittest

from idol_manager.match_engine import calculate_match
from idol_manager.match_replay import replay_frames
from tests.test_match_engine import match_input,ScriptedRandom


class MatchReplayTests(unittest.TestCase):
    def test_exact_sixty_frames_and_leader_bonus_at_tick_sixty(self):
        result=calculate_match(match_input(100,0),random.Random(4))
        frames=replay_frames(result)
        self.assertEqual(len(frames),60)
        self.assertEqual(len(frames)*500,30000)
        self.assertEqual([f.tick for f in frames],list(range(1,61)))
        self.assertEqual(tuple(e for frame in frames for e in frame.events),result.events)
        self.assertEqual(sum(e.phase=='leader' for e in frames[-1].events),4)
        self.assertTrue(all(e.phase!='leader' for f in frames[:-1] for e in f.events))

    def test_repeated_deathmatch_stays_separate_in_five_second_blocks(self):
        result=calculate_match(match_input(leaders=False),ScriptedRandom([.9]*140+[0,.9]*10))
        frames=replay_frames(result)
        self.assertEqual(len(frames),80)
        self.assertEqual(Counter((f.phase,f.round_number) for f in frames),{('regular',0):60,('deathmatch',1):10,('deathmatch',2):10})
        self.assertEqual(tuple(e for f in frames for e in f.events),result.events)
        self.assertTrue(all(e.phase=='deathmatch' for f in frames[60:] for e in f.events))

    def test_forfeits_do_not_invent_playback_events(self):
        source=match_input()
        empty=replace(source,teams=tuple(replace(t,players=(),representative_id=None) for t in source.teams))
        result=calculate_match(empty,random.Random(3))
        self.assertEqual(result.resolution,'double_forfeit')
        self.assertEqual(replay_frames(result),())


if __name__=='__main__':unittest.main()
