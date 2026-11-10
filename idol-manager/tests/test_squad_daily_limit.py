"""Focused roster/rest changes; all mutations use disposable fixture copies."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import unittest
from idol_manager.squads import SquadService,SquadError
from idol_manager.conditions import enter_day,public_condition,forced_demotions
from idol_manager.condition_rules import required_rest_weeks,registration_multiplier
from tests import test_squads as fixture

class DailyLimitTests(unittest.TestCase):
    setUpClass=classmethod(fixture.SquadTests.setUpClass.__func__)
    copy_db=staticmethod(fixture.SquadTests.copy_db);dump=fixture.SquadTests.dump
    def setUp(self):
        fixture.SquadTests.setUp(self);self.copy_db(self.formed_path,self.path)
    def pairs(self):
        s=self.squads.snapshot();return s,[p.id for p in s.members if p.squad=='first_team'],[p.id for p in s.members if p.squad=='second_team']
    def test_rest_boundaries_and_first_team_counter_not_reset(self):
        self.assertEqual([required_rest_weeks(w) for w in range(6)],[0,0,0,1,2,2])
        self.assertEqual([registration_multiplier(w) for w in (1,2,3,4)],[1,1,10,20])
        _,first,second=self.pairs()
        with closing(self.database.connect()) as c,c:
            c.execute('UPDATE player_conditions SET registration_weeks=2,registration_week=0 WHERE person_id=?',(first[0],))
            c.execute('UPDATE player_conditions SET registration_weeks=2,squad_since=0 WHERE person_id=?',(second[0],))
            enter_day(c,7)
            self.assertEqual(public_condition(c,first[0],7).registration_weeks,3)
            self.assertEqual(public_condition(c,second[0],7).registration_weeks,0)
    def test_swap_repeat_restart_other_pair_and_next_monday(self):
        s,a,b=self.pairs();self.squads.swap(a[0],b[0],expected_revision=s.revision)
        before=self.dump();service=SquadService(self.database)
        with self.assertRaisesRegex(SquadError,'오늘 이미'):service.swap(b[0],a[0],expected_revision=service.snapshot().revision)
        with self.assertRaisesRegex(SquadError,'오늘 이미'):service.swap(b[0],b[1],expected_revision=service.snapshot().revision)
        self.assertEqual(before,self.dump())
        service.swap(a[1],b[1],expected_revision=service.snapshot().revision)
        with closing(self.database.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=7')
        service.swap(b[0],a[0],expected_revision=service.snapshot().revision)
        with closing(self.database.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=8')
        with self.assertRaises(SquadError):service.swap(a[0],b[0],expected_revision=service.snapshot().revision)
    def test_single_move_cannot_reverse_same_day(self):
        _,a,b=self.pairs()
        with closing(self.database.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(b[-1],))
        self.squads.move(a[0],'second_team',expected_revision=self.squads.snapshot().revision)
        before=self.dump()
        with self.assertRaisesRegex(SquadError,'오늘 이미'):self.squads.move(a[0],'first_team',expected_revision=self.squads.snapshot().revision)
        self.assertEqual(before,self.dump())
        self.squads.move(b[0],'first_team',expected_revision=self.squads.snapshot().revision)
    def test_injury_swap_bypasses_manual_limit_and_does_not_consume_another(self):
        s,a,b=self.pairs();self.squads.swap(a[0],b[0],expected_revision=s.revision)
        with closing(self.database.connect()) as c,c:
            c.execute('UPDATE player_conditions SET injured=1,recovery_day=8 WHERE person_id=?',(b[0],))
            forced_demotions(c,0)
            self.assertEqual(c.execute('SELECT career_status FROM roster_memberships WHERE person_id=?',(b[0],)).fetchone()[0],'second_team')
        self.assertEqual(self.squads.normal_changes_today(),{a[0],b[0]})
        s,a2,b2=self.pairs();clean_a=next(p for p in a2 if p not in (a[0],b[0]));clean_b=next(p for p in b2 if p not in (a[0],b[0]))
        self.squads.swap(clean_a,clean_b,expected_revision=s.revision)
    def test_concurrent_same_pick_commits_once(self):
        s,a,b=self.pairs()
        def run(_):
            try:self.squads.swap(a[0],b[0],expected_revision=s.revision);return True
            except SquadError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(run,range(2))),1)
        self.assertEqual(self.squads.normal_changes_today(),{a[0],b[0]})
    def test_initial_and_special_friday_not_counted(self):
        self.assertFalse(self.squads.normal_changes_today())
        s,a,b=self.pairs();self.squads.swap(a[0],b[0],expected_revision=s.revision)
        with closing(self.database.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=4')
            self.squads._guard_normal_change(c,(a[0],b[0]))
        self.assertFalse(self.squads.normal_changes_today())

    def test_three_weeks_need_one_rest_four_weeks_need_two(self):
        _,_,second=self.pairs()
        with closing(self.database.connect()) as c,c:
            for person,weeks in zip(second,(3,4,6)):
                c.execute('UPDATE player_conditions SET registration_weeks=?,squad_since=0 WHERE person_id=?',(weeks,person))
            enter_day(c,7)
            self.assertEqual([public_condition(c,p,7).registration_weeks for p in second[:3]],[0,4,6])
            enter_day(c,14)
            self.assertEqual([public_condition(c,p,14).registration_weeks for p in second[:3]],[0,0,0])

    def test_partial_second_team_week_does_not_reset_three_week_risk(self):
        _,_,second=self.pairs()
        with closing(self.database.connect()) as c,c:
            c.execute('UPDATE player_conditions SET registration_weeks=3,squad_since=1 WHERE person_id=?',(second[0],))
            enter_day(c,7)
            self.assertEqual(public_condition(c,second[0],7).registration_weeks,3)
