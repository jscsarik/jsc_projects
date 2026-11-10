from contextlib import closing
from pathlib import Path
from collections import Counter
import json,random,sqlite3,time,unittest
from unittest.mock import patch
from idol_manager.service import GameService
from idol_manager.profile_service import ProfileService
from idol_manager.config import SKILLS
from idol_manager.condition_rules import injury_probability,fatigue_penalty
from idol_manager.conditions import public_condition
from tests import test_match_ui as fixture


class ProfileServiceTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MatchUITests.setUpClass.__func__)
    def setUp(self):
        fixture.MatchUITests.setUp(self)
        self.service=GameService(self.base,database_path=self.path);self.db=self.service.database;self.profiles=self.service.profiles
        with closing(self.db.connect()) as c:
            self.person=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' LIMIT 1").fetchone()[0]
            self.hidden=c.execute('SELECT d.person_id FROM initial_draft_candidates d JOIN roster_memberships r ON r.person_id=d.person_id WHERE r.agency_id IS NULL AND d.person_id NOT IN (SELECT person_id FROM draft_picks) LIMIT 1').fetchone()[0]

    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())

    def test_own_other_first_second_and_trainee_have_exact_ca_without_pa(self):
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE roster_memberships SET agency_id='jyp',career_status='trainee' WHERE person_id=?",(self.hidden,))
            people=[r[0] for r in c.execute("SELECT person_id FROM roster_memberships WHERE agency_id IS NOT NULL")]
        original=self.db.connect
        def guarded():
            c=original();c.set_authorizer(lambda action,table,col,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and ((table,col)==('abilities','potential') or (table,col)==('idols','archetype')) else sqlite3.SQLITE_OK);return c
        for person in (self.person,self.hidden,*people[16:19]):
            with patch.object(self.db,'connect',side_effect=guarded):p=self.profiles.get(person)
            self.assertTrue(p['exact']);self.assertEqual(p['average'][0],sum(a for a,b in p['bounds'])/8)
            self.assertTrue(all(a==b for a,b in p['bounds']));self.assertIsNotNone(p['health'])
            text=json.dumps(p);self.assertNotIn('potential',text);self.assertNotIn('archetype',text)

    def test_candidate_query_denies_exact_ca_pa_health_and_immutable_estimates(self):
        original=self.db.connect
        def connect():
            c=original();c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and ((t=='abilities' and col in ('value','potential')) or (t=='idols' and col in ('health','average','archetype'))) else sqlite3.SQLITE_OK);return c
        with patch.object(self.db,'connect',side_effect=connect):p=self.profiles.get(self.hidden)
        self.assertFalse(p['exact']);self.assertIsNone(p['health']);self.assertIsNone(p['condition'])
        with closing(original()) as c:
            estimates={r[0]:(r[1],r[2]) for r in c.execute('SELECT skill,low,high FROM draft_estimates WHERE person_id=?',(self.hidden,))}
            actual=dict(c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(self.hidden,)))
        self.assertEqual(p['bounds'],tuple(estimates[s] for s in SKILLS))
        for skill,(a,b) in zip(SKILLS,p['bounds']):self.assertEqual(b-a,4);self.assertTrue(a<=actual[skill]<=b)
        self.assertEqual(p,self.profiles.get(self.hidden));self.assertEqual(p,ProfileService(self.db).get(self.hidden))

    def test_past_professional_fa_keeps_exact_disclosure(self):
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(self.person,))
        p=self.profiles.get(self.person);self.assertTrue(p['exact']);self.assertIsNone(p['identity']['agency_id'])
        self.assertTrue(p['draft']);self.assertIsNone(p['contract']['salary']);self.assertIsNone(p['contract']['end'])

    def test_drafted_before_squad_formation_is_exact(self):
        fixture.copy_db(self.pending,self.path)
        service=GameService(self.base,database_path=self.path)
        self.assertTrue(service.profiles.get(self.person)['exact'])

    def test_live_current_values_change_without_rewriting_estimates(self):
        before=self.profiles.get(self.person)
        with closing(self.db.connect()) as c,c:c.execute("UPDATE abilities SET value=value-1 WHERE person_id=? AND skill='vocal' AND value>0",(self.person,))
        after=self.profiles.get(self.person);self.assertEqual(after['bounds'][0][0],before['bounds'][0][0]-1)

    def test_fatigue_1_to_5_days_doubleheader_and_rest_match_engine(self):
        for streak in range(1,6):
            with closing(self.db.connect()) as c,c:
                c.execute('UPDATE game_clock SET absolute_day=10')
                c.execute('UPDATE player_conditions SET last_appearance_day=10,consecutive_days=? WHERE person_id=?',(streak,self.person))
                c.execute('INSERT OR IGNORE INTO appearance_days VALUES (?,10)',(self.person,))
                c.execute('INSERT OR IGNORE INTO appearance_days VALUES (?,10)',(self.person,))
            p=self.profiles.get(self.person)['condition'];self.assertEqual(p['current_penalty'],fatigue_penalty(streak));self.assertEqual(p['appearance_dates'].count(10),1)
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=12')
        p=self.profiles.get(self.person)['condition'];self.assertTrue(p['reset']);self.assertEqual(p['streak'],0);self.assertEqual(p['preview_penalty'],0)

    def test_registration_risk_weeks_3_4_and_probabilities_match_engine(self):
        for weeks,multiplier in ((1,1),(2,1),(3,10),(4,20),(5,30)):
            with closing(self.db.connect()) as c,c:
                c.execute('UPDATE game_clock SET absolute_day=24')
                c.execute('UPDATE player_conditions SET registration_weeks=?,registration_week=3 WHERE person_id=?',(weeks,self.person))
            p=self.profiles.get(self.person);condition=p['condition'];self.assertEqual(condition['registration_weeks'],weeks);self.assertEqual(condition['multiplier'],multiplier)
            for kind in ('match','first_rest','second'):self.assertEqual(condition['probabilities'][kind],injury_probability(p['health'],weeks,kind))

    def test_rest_and_injury_recovery_values_from_storage(self):
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=29')
            c.execute("UPDATE player_conditions SET squad='second_team',squad_since=28,registration_weeks=4,complete_rest_weeks=1,injured=1,injury_day=27,recovery_day=36,return_not_before=42 WHERE person_id=?",(self.person,))
        p=self.profiles.get(self.person)['condition'];self.assertEqual(p['required_rest_weeks'],2);self.assertFalse(p['rest_complete']);self.assertEqual(p['rest_weeks'],1)
        self.assertTrue(p['injured']);self.assertEqual(p['recovery_day'],36);self.assertEqual(p['return_not_before'],42)

    def test_regular_statistics_exact_event_counts_and_rng_unchanged(self):
        fixture_=next(f for f in self.service.matches.fixtures() if f.player_participates)
        self.service.matches.seed_factory=lambda:55;result=self.service.matches.play(fixture_.id)
        person=result.players[0]['person_id'];before=self.dump();random.seed(55);state=random.getstate()
        p=self.profiles.get(person);self.assertEqual(p['statistics']['appearances']['regular'],1)
        expected=Counter((e.phase,e.skill) for e in result.events if e.person_id==person)
        actual={(r['phase'],r['skill']):r['attempts'] for r in p['statistics']['abilities']};self.assertEqual(dict(expected),actual)
        self.assertEqual(sum(r['attempts'] for r in p['statistics']['abilities'] if r['phase'] in ('main','support')),60)
        self.assertEqual(state,random.getstate());self.assertEqual(before,self.dump())

    def test_search_uses_only_public_midpoints_and_hides_unseen(self):
        rows=self.profiles.search();self.assertEqual(len(rows),200)
        self.assertTrue(any(not p['exact'] for p in rows));candidate=next(p for p in rows if p['id']==self.hidden)
        self.assertEqual(candidate['average'],sum((a+b)/2 for a,b in candidate['bounds'])/8)
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE abilities SET potential=100,value=CASE WHEN value>0 THEN value-1 ELSE 1 END WHERE person_id=?',(self.hidden,))
        self.assertEqual(candidate,next(p for p in self.profiles.search() if p['id']==self.hidden))

    def test_no_duplicate_person_names_used_as_identifier(self):
        with closing(self.db.connect()) as c,c:c.execute("UPDATE people SET name='동명이인' WHERE id IN (?,?)",(self.person,self.hidden))
        first=self.profiles.get(self.person);second=self.profiles.get(self.hidden)
        self.assertEqual(first['identity']['name'],second['identity']['name']);self.assertNotEqual(first['exact'],second['exact'])

    def test_unknown_id_and_read_only_guard_and_repeat_performance(self):
        with self.assertRaises(ValueError):self.profiles.get('missing')
        with self.profiles.read() as c:
            with self.assertRaises(sqlite3.OperationalError):c.execute('UPDATE idols SET age=19')
        before=self.dump();start=time.perf_counter()
        for _ in range(30):self.profiles.get(self.person)
        self.assertLess(time.perf_counter()-start,5);self.assertEqual(before,self.dump())

    def test_weekly_growth_aging_changes_and_public_trial_projection(self):
        fixture_=next(f for f in self.service.matches.fixtures() if f.player_participates)
        result=self.service.matches.play(fixture_.id);self.person=result.players[0]['person_id']
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=7')
            c.execute('UPDATE idols SET age=30 WHERE person_id=?',(self.person,))
            for day in range(7):
                c.execute('''INSERT OR REPLACE INTO development_days(game_id,absolute_day,person_id,agency_id,role,leader)
                    SELECT 1,?,person_id,agency_id,career_status,0 FROM roster_memberships WHERE agency_id IS NOT NULL''',(day,))
        self.service.development.settle_current();before=self.dump();p=self.profiles.get(self.person)
        self.assertEqual({r['kind'] for r in p['growth']},{'growth','aging'})
        self.assertTrue(any(c['kind']=='aging' and c['applied']<0 for r in p['growth'] for c in r['changes']))
        self.assertTrue(all(set(c)=={'kind','skill','applied'} for r in p['growth'] for c in r['changes']))
        self.assertTrue(all(c['applied']!=0 for r in p['growth'] for c in r['changes']))
        self.assertEqual(sum(r['growth_attempts'] for r in p['statistics']['abilities']),60)
        self.assertEqual(sum(r['pending_growth_attempts'] for r in p['statistics']['abilities']),0)
        for forbidden in ('probability','potential','roll','seed'):self.assertNotIn(forbidden,json.dumps(p))
        self.assertEqual(before,self.dump())

    def test_tiebreak_and_postseason_logs_distinguished_growth_excludes_extra_phases(self):
        with closing(self.db.connect()) as c,c:
            agency=c.execute('SELECT agency_id FROM roster_memberships WHERE person_id=?',(self.person,)).fetchone()[0]
            events=[dict(person_id=self.person,phase=p,skill=s,success=True) for p,s in [('main','vocal'),('support','dance'),('leader','leadership'),('deathmatch','vocal')]]
            c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (1,'seeded','{}','[]')")
            for identity,kind,day in [('post','post',170),('tie','tie',168)]:
                summary=dict(players=[dict(person_id=self.person,agency_id=agency,outcome='win')],order=[agency])
                c.execute('''INSERT INTO final_contests(id,season,kind,round_number,game_number,absolute_day,agencies_json,content_json,required,status,events_json,result_json)
                    VALUES (?,1,?,99,1,?,'[]','{"name":"기록 시험"}',1,'completed',?,?)''',(identity,kind,day,json.dumps(events),json.dumps(summary)))
        p=self.profiles.get(self.person);self.assertEqual(p['statistics']['appearances'],{'postseason':1,'tiebreak':1})
        rows=p['statistics']['abilities'];self.assertEqual(sum(r['growth_attempts'] for r in rows),0)
        self.assertEqual(sum(r['pending_growth_attempts'] for r in rows),2)
        self.assertEqual(sum(r['growth_attempts'] for r in rows if r['phase'] in ('leader','deathmatch')),0)
