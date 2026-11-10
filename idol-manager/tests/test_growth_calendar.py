"""32-week match-to-growth regression tests, exclusively disposable saves."""
import json,unittest
from contextlib import closing
from unittest.mock import patch
from tests import test_season32 as fixture
from idol_manager.game_clock import regular_day
from idol_manager.development_service import activity,capture_day,apply_monday

class GrowthCalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day

    def play_week(self,season,week):
        self.day(regular_day(season,week,2));self.service.calendar.ensure_current_schedule()
        identity=self.rows('SELECT id FROM scheduled_matches WHERE season=? AND week=? AND weekday=2 AND day_order=1 ORDER BY match_order LIMIT 1',(season,week))[0][0]
        result=self.service.matches.play(identity)
        return result

    def test_actual_regular_appearance_uses_real_dates_across_halves_and_seasons(self):
        for season,week in ((1,1),(1,12),(1,13),(1,24),(2,1)):
            with self.subTest(season=season,week=week):
                result=self.play_week(season,week);start=regular_day(season,week)
                with closing(self.db.connect()) as c:
                    facts=activity(c,start,start+6)
                    for p in result.players:
                        own=facts[p['person_id']]
                        self.assertIn('regular:'+result.match_id,own['games'])
                        self.assertIn(start+2,own['dates'])
                        self.assertEqual(sum(own['attempts']),60)
                        self.assertEqual(sum(own['basic_successes']),p['base_successes'])
                    self.assertFalse(any('regular:'+result.match_id in f['games'] for f in activity(c,start-7,start-1).values()))

    def test_weekly_growth_does_not_label_actual_appearance_as_absent(self):
        result=self.play_week(1,1)
        with closing(self.db.connect()) as c,c:
            for d in range(7,14):capture_day(c,d)
        self.day(14);self.service.development.settle_current()
        for p in result.players:
            reason,facts,bonus=self.rows('''SELECT r.reasons_json,r.facts_json,r.bonus_applied FROM development_results r
                JOIN development_settlements s ON s.id=r.settlement_id WHERE s.kind='growth' AND s.absolute_day=14 AND r.person_id=?''',(p['person_id'],))[0]
            self.assertNotIn('no_appearance',json.loads(reason));self.assertEqual(json.loads(facts)['actual_games'],1)
            self.assertEqual(sum(json.loads(facts)['attempts']),60)
            trials=[json.loads(r[0]) for r in self.rows('''SELECT t.trial_json FROM development_trials t JOIN development_settlements s ON s.id=t.settlement_id
                WHERE s.kind='growth' AND s.absolute_day=14 AND t.person_id=?''',(p['person_id'],))]
            self.assertFalse(any(t['kind']=='first_no_appearance' for t in trials))
            if not any(r in json.loads(reason) for r in ('injury','three_consecutive_days')):
                self.assertTrue(bonus);self.assertEqual(sum(t['kind']=='first_up' and 'probability' in t for t in trials),2)
        before=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        self.service.development.settle_current();self.assertEqual(before,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))

    def test_special_first_team_counts_on_actual_special_sunday(self):
        from collections import Counter
        self.day(regular_day(1,4,6));self.service.calendar.ensure_current_schedule()
        special=self.service.specials;special.seed_factory=lambda:1827
        event=self.rows('SELECT id FROM special_events WHERE week=4')[0][0]
        original=special._event
        with patch.object(special,'_event',side_effect=lambda c,i,**kw:original(c,i)):
            special.start(event)
            for stage in ('upper','lower','final'):
                special.play(next(r['id'] for r in special.state(event)['rounds'] if r['stage']==stage))
        expected=Counter();expected_success=Counter();reserve=set()
        with closing(self.db.connect()) as c:
            for identity,raw in c.execute('SELECT id,input_json FROM special_rounds WHERE event_id=?',(event,)):
                roles=json.loads(raw)['conditions']['squads']
                reserve.update(p for p,role in roles.items() if role=='second_team')
                for p,phase,success in c.execute("SELECT person_id,phase,success FROM special_judgments WHERE round_id=? AND phase IN ('main','support')",(identity,)):
                    if roles[p]=='first_team':expected[p]+=1;expected_success[p]+=success
            facts=activity(c,regular_day(1,4),regular_day(1,4,6))
            self.assertTrue(expected)
            for p,n in expected.items():
                self.assertEqual(sum(facts[p]['attempts']),n)
                self.assertEqual(sum(facts[p]['basic_successes']),expected_success[p])
                self.assertEqual(facts[p]['dates'],{regular_day(1,4,6)})
            self.assertTrue(all(not facts[p]['games'] for p in reserve if p not in expected))

    def test_postseason_general_only_and_tiebreak_excluded(self):
        p=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='first_team' LIMIT 1")[0][0]
        events=[dict(person_id=p,phase=phase,skill=skill,success=True) for phase,skill in (
            ('main','vocal'),('support','rap'),('leader','leadership'),('deathmatch','vocal'))]
        with closing(self.db.connect()) as c,c:
            c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (1,'seeded','{}','[]')")
            for identity,kind,d in (('growth-post','post',184),('growth-tie','tie',182)):
                c.execute("INSERT INTO final_contests(id,season,kind,round_number,game_number,absolute_day,agencies_json,content_json,required,status,events_json) VALUES (?,1,?,99,1,?,'[]','{}',1,'completed',?)",(identity,kind,d,json.dumps(events)))
            f=activity(c,182,188)[p]
            self.assertEqual(sum(f['attempts']),2);self.assertEqual(sum(f['basic_successes']),2)
            self.assertEqual(f['dates'],{184});self.assertEqual(f['games'],{'post:growth-post'})

    def test_aging_cycle_distinct_losses_skip_inactive_and_no_duplicate(self):
        from idol_manager.development_service import settle_aging
        p=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='first_team' LIMIT 1")[0][0]
        potentials=self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE idols SET age=30 WHERE person_id=?',(p,))
            runtime=c.execute('SELECT * FROM development_runtime').fetchone();rules=json.loads(runtime['rules_json'])
            for d in (14,28,84,91,98,182,196,210,224,238):
                settle_aging(c,d,runtime,rules);settle_aging(c,d,runtime,rules)
            dates=[r[0] for r in c.execute("SELECT absolute_day FROM development_settlements WHERE kind='aging' ORDER BY absolute_day")]
            self.assertEqual(dates,[14,28,84,98,182,196,238])
            for raw, in c.execute("SELECT r.deltas_json FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE s.kind='aging' AND r.person_id=?",(p,)):
                deltas=json.loads(raw);self.assertEqual(deltas.count(-1),2);self.assertEqual(deltas.count(0),6)
        self.assertEqual(potentials,self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill'))

    def test_actual_appearance_with_three_consecutive_days_still_excludes_rises(self):
        result=self.play_week(1,1);p=result.players[0]['person_id']
        with closing(self.db.connect()) as c,c:
            for d in range(7,14):capture_day(c,d)
            c.executemany('INSERT OR IGNORE INTO appearance_days VALUES (?,?)',[(p,10),(p,11)])
        self.day(14);self.service.development.settle_current()
        reason,facts,bonus=self.rows("SELECT reasons_json,facts_json,bonus_applied FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE s.kind='growth' AND s.absolute_day=14 AND r.person_id=?",(p,))[0]
        self.assertIn('three_consecutive_days',json.loads(reason));self.assertNotIn('no_appearance',json.loads(reason))
        self.assertEqual(json.loads(facts)['actual_games'],1);self.assertFalse(bonus)
