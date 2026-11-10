from contextlib import closing
import json,unittest
from idol_manager.conditions import enter_day,public_condition
from idol_manager.condition_rules import injury_probability
from tests import test_profiles as fixture


class IntegratedConditionTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ProfileServiceTests.setUpClass.__func__)
    setUp=fixture.ProfileServiceTests.setUp
    dump=fixture.ProfileServiceTests.dump

    def state(self,day=7,streak=3,weeks=4):
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=?',(day,))
            c.execute('UPDATE idols SET health=80 WHERE person_id=?',(self.person,))
            c.execute('UPDATE player_conditions SET last_appearance_day=?,consecutive_days=?,registration_weeks=?,registration_week=? WHERE person_id=?',(day-1,streak,weeks,day//7,self.person))
            for d in range(day-streak,day):c.execute('INSERT OR IGNORE INTO appearance_days VALUES (?,?)',(self.person,d))

    def test_conditional_next_schedule_rest_gap_current_effective_values_and_calendar(self):
        self.state();before=self.dump();p=self.profiles.get(self.person);c=p['condition']
        self.assertEqual(c['current_penalty'],.1);self.assertEqual(c['preview_penalty'],.2)
        self.assertGreaterEqual(c['next_match']['day'],9);self.assertEqual(c['next_match']['penalty'],0)
        self.assertEqual(len(c['recent_calendar']),7);self.assertEqual(sum(r['played'] for r in c['recent_calendar']),3)
        for original,effective in zip(p['bounds'],c['today_effective_values']):self.assertAlmostEqual(effective,original[0]*.8)
        self.assertEqual(before,self.dump())

    def test_unknown_schedule_does_not_invent_future_penalty(self):
        self.state()
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET career_status='fa',agency_id=NULL WHERE person_id=?",(self.person,))
        self.assertIsNone(self.profiles.get(self.person)['condition']['next_match'])

    def test_health80_week4_match4percent_rest2percent_and_engine_second_formula(self):
        self.state();c=self.profiles.get(self.person)['condition']
        self.assertAlmostEqual(c['base_probabilities']['match'],.002);self.assertAlmostEqual(c['probabilities']['match'],.04)
        self.assertAlmostEqual(c['base_probabilities']['first_rest'],.001);self.assertAlmostEqual(c['probabilities']['first_rest'],.02)
        self.assertEqual(c['probabilities']['second'],injury_probability(80,4,'second'))
        self.assertEqual(c['multiplier'],20)
        with closing(self.db.connect()) as db,db:db.execute('UPDATE player_conditions SET registration_weeks=6 WHERE person_id=?',(self.person,))
        self.assertEqual(self.profiles.get(self.person)['condition']['multiplier'],40)

    def test_weekly_fatigue_and_injury_restriction_is_read_only_and_offseason_excluded(self):
        self.state(day=5,streak=3)
        with closing(self.db.connect()) as c,c:
            c.execute('''INSERT INTO condition_events(event_key,person_id,absolute_day,kind,occurred,details_json)
                VALUES ('profile-injury',?,5,'first_rest',1,'{}')''',(self.person,))
        before=self.dump();p=self.profiles.get(self.person);facts=p['condition']['weekly_growth']
        self.assertTrue(facts['three_consecutive_days']);self.assertTrue(facts['injury_occurred']);self.assertTrue(facts['rise_restricted'])
        self.assertEqual(p['condition']['injuries'][0]['squad'],'first_team');self.assertEqual(before,self.dump())
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=190')
        self.assertFalse(self.profiles.get(self.person)['condition']['weekly_growth']['active'])

    def second(self,weeks):
        with closing(self.db.connect()) as c,c:
            person=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' LIMIT 1").fetchone()[0]
            c.execute('UPDATE game_clock SET absolute_day=35')
            c.execute("UPDATE player_conditions SET squad='second_team',squad_since=28,registration_weeks=?,registration_week=3,complete_rest_weeks=0 WHERE person_id=?",(weeks,person))
            enter_day(c,35)
        return person

    def test_one_or_two_complete_rest_weeks_and_early_return_keeps_engine_stage(self):
        person=self.second(3);state=self.profiles.get(person)['condition']
        self.assertEqual(state['registration_weeks'],0);self.assertEqual(state['remaining_rest_weeks'],0)
        person=self.second(4);state=self.profiles.get(person)['condition']
        self.assertEqual(state['registration_weeks'],4);self.assertEqual(state['remaining_rest_weeks'],1)
        self.assertTrue(state['can_return_now'])
        snapshot=self.service.squads.snapshot();first=next(p.id for p in snapshot.members if p.squad=='first_team')
        self.service.squads.swap(first,person,expected_revision=snapshot.revision)
        with closing(self.db.connect()) as c:expected=public_condition(c,person,35)
        self.assertEqual(self.profiles.get(person)['condition']['registration_weeks'],expected.registration_weeks)
        self.assertGreater(expected.registration_weeks,0)

    def test_two_week_rest_reset_recovery_and_return_lock_remain_separate(self):
        person=self.second(4)
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=42');enter_day(c,42)
            c.execute('UPDATE player_conditions SET injured=1,injury_day=40,recovery_day=43,return_not_before=49 WHERE person_id=?',(person,))
        state=self.profiles.get(person)['condition'];self.assertEqual(state['registration_weeks'],0)
        self.assertEqual(state['recovery_day'],43);self.assertEqual(state['return_not_before'],49);self.assertFalse(state['can_return_now'])
