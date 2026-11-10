from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,random,tempfile,unittest,sqlite3,subprocess,sys

from idol_manager.config import SKILLS,load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.development_rules import Development,gap_chance,primary_role
from idol_manager.development_service import DevelopmentService,capture_day,activity
from idol_manager.calendar_service import CalendarService
from idol_manager.match_service import MatchService
from tests.game_fixtures import complete_initial_setup


class Fixed:
    def random(self):return 0.0
    def sample(self,values,n):return list(values)[:n]
    def choice(self,values):return list(values)[0]
    def shuffle(self,values):pass


class DevelopmentRuleTests(unittest.TestCase):
    def model(self,ca=50,pa=100):return Development([ca]*8,[pa]*8,Fixed())

    def test_first_week_main_and_least_used_exclusion(self):
        m=self.model();m.first([20,19,0,0,0,0,0,0],[40,35,0,1,10,10,10,10],appeared=True)
        self.assertEqual(m.values,[51,51,49,49,50,50,50,50])
        m=self.model();m.first([20,19,0,0,0,0,0,0],[40,35,0,1,10,10,10,10],appeared=True,excluded=True)
        self.assertEqual(m.values,[50,50,49,49,50,50,50,50])

    def test_confirmed_main_and_random_successes_rank_top_two_once_and_keep_rates(self):
        # A complete 30+30 history: random vocal successes also count toward
        # vocal, while rap overtakes both content-main skills on total success.
        main=[('vocal',i<3) for i in range(15)]+[('dance',i<2) for i in range(15)]
        other=[('vocal',True)]*5+[('rap',True)]*9+[('entertainment',False)]*6+[('appearance',False)]*5+[('physique',False)]*5
        events=main+other
        attempts=[sum(skill==s for skill,success in events) for s in SKILLS]
        successes=[sum(skill==s and success for skill,success in events) for s in SKILLS]
        self.assertEqual((len(main),len(other),sum(attempts)),(30,30,60))
        self.assertEqual(successes,[8,2,9,0,0,0,0,0]);self.assertEqual(sum(successes),19)
        model=self.model(ca=80);model.first(successes,attempts,appeared=True)
        rises=[(t['skill'],t['probability']) for t in model.trials if t['kind']=='first_up' and 'probability' in t]
        self.assertEqual(rises,[('rap',.6),('vocal',.4)])
        falls=[t['skill'] for t in model.trials if t['kind']=='first_down' and 'probability' in t]
        self.assertEqual(falls,['intelligence','leadership'])
        blocked=self.model(ca=80);blocked.first(successes,attempts,appeared=True,excluded=True)
        self.assertFalse(any(t['kind']=='first_up' for t in blocked.trials))
        self.assertEqual(blocked.values,[80,80,80,80,80,80,79,79])
        for value,expected in ((0,1),(100,0)):
            edge=self.model(ca=value);edge.first(successes,attempts,appeared=True)
            probabilities=[t['probability'] for t in edge.trials if t['kind']=='first_up' and 'probability' in t]
            self.assertEqual(probabilities,[expected,expected])

    def test_no_appearance_and_postseason_waiting(self):
        m=self.model();m.first([0]*8,[0]*8,appeared=False);self.assertEqual(m.values[:2],[49,49])
        m=self.model();m.first([0]*8,[0]*8,appeared=False,waiting=True);self.assertEqual(m.values,[50]*8)

    def test_second_independent_both_success_cancel_and_trainee_four(self):
        m=self.model();m.second();self.assertEqual(m.values,[50]*8)
        self.assertEqual(len([t for t in m.trials if t['kind']=='second_up']),3)
        self.assertEqual(len([t for t in m.trials if t['kind']=='second_down']),3)
        m=self.model();m.trainee();self.assertEqual(m.values,[51]*4+[50]*4)

    def test_eight_individual_caps_zero_floor_no_pa_changes(self):
        caps=tuple(range(50,58));m=Development([50]*8,caps,Fixed())
        for i in range(8):m.change(i,20,'test')
        self.assertEqual(m.values,list(caps));self.assertEqual(m.potentials,caps)
        m=Development([0]*8,[0]*8,Fixed());m.trainee();m.additional();m.aging(30)
        self.assertEqual(m.values,[0]*8)

    def test_gap_boundaries_and_independent_same_skill_repeat(self):
        for gap,chance in ((0,0),(10,.1),(20,.4),(30,.5)):
            self.assertEqual(gap_chance([0]*8,[gap]*8),chance)
        self.assertEqual(gap_chance([0]*8,[11]+[10]*7),.25)
        m=self.model();m.additional();self.assertEqual(m.values,[52]+[50]*7)
        m=Development([50]*8,[51]+[50]*7,Fixed());m.additional();self.assertEqual(m.values,[51]+[50]*7)

    def test_role_majority_switch_and_tie_priority(self):
        self.assertEqual(primary_role(dict(second_team=4,first_team=3)),'second_team')
        self.assertEqual(primary_role(dict(second_team=3,first_team=4)),'first_team')
        self.assertEqual(primary_role(dict(first_team=3,second_team=3,trainee=1)),'first_team')
        self.assertEqual(primary_role(dict(second_team=3,trainee=3)),'second_team')

    def test_aging_27_28_30_distinct_skills(self):
        for age,count in ((27,0),(28,1),(29,1),(30,2)):
            m=self.model();m.aging(age);self.assertEqual(m.values.count(49),count)


class DevelopmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'game.sqlite3'
        self.db=Database(self.path);self.db.create_game(tuple(Person(str(i),f'인물{i}',f'인물{i}',f'missing/{i}.png') for i in range(310)),load_settings(),random.Random(2))
        complete_initial_setup(self.db);self.calendar=CalendarService(self.db,rng=random.Random(4));self.calendar.ensure_current_schedule()
        self.development=DevelopmentService(self.db)

    def rows(self,sql,args=()):
        with closing(self.db.connect()) as c:return [tuple(r) for r in c.execute(sql,args)]

    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())

    def seed_days(self,day=7):
        with closing(self.db.connect()) as c,c:
            for d in range(day-7,day):capture_day(c,d)
            c.execute('UPDATE game_clock SET absolute_day=?',(day,))

    def test_sunday_included_real_matches_dates_and_weekly_idempotence(self):
        matches=MatchService(self.db,seed_factory=lambda:8)
        for d in range(7):
            for fixture in matches.fixtures():matches.play(fixture.id)
            self.calendar.advance_day(expected_absolute_day=d)
        history=self.development.history();self.assertTrue(history)
        growth=self.rows("SELECT id FROM development_settlements WHERE kind='growth'")[0][0]
        records=self.development.history(growth)
        self.assertEqual(sum(r['role'] in ('first_team','second_team') for r in records),160)
        expected=self.rows("SELECT COUNT(*) FROM roster_memberships WHERE career_status IN ('first_team','second_team','trainee')")[0][0]
        self.assertEqual(len(records),expected)
        self.assertTrue(all(json.loads(r['facts_json'])['covered_days']==7 for r in records))
        self.assertTrue(any(6 in json.loads(r['facts_json'])['appearance_dates'] for r in records))
        original=self.dump();self.development.settle_current();self.assertEqual(original,self.dump())
        self.assertEqual(original,list_dump(Database(self.path)))
        self.assertFalse(self.rows('SELECT 1 FROM abilities WHERE value>potential OR value<0'))

    def test_majority_role_single_basic_and_trainee(self):
        first=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='first_team' LIMIT 1")[0][0]
        second=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='second_team' LIMIT 1")[0][0]
        trainee=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='unassigned' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE roster_memberships SET agency_id='ador',career_status='trainee' WHERE person_id=?",(trainee,))
            for d in range(7):capture_day(c,d)
            c.execute("UPDATE development_days SET role='second_team' WHERE person_id=? AND absolute_day<4",(first,))
            c.execute("UPDATE development_days SET role='first_team' WHERE person_id=? AND absolute_day>=3",(second,))
            c.execute('UPDATE game_clock SET absolute_day=7')
        self.development.settle_current();growth=self.rows("SELECT id FROM development_settlements WHERE kind='growth'")[0][0]
        records={r['person_id']:r for r in self.development.history(growth)}
        self.assertEqual(records[first]['role'],'second_team');self.assertEqual(records[second]['role'],'first_team')
        self.assertEqual(records[trainee]['role'],'trainee')
        self.assertEqual(self.rows("SELECT COUNT(*) FROM development_results WHERE settlement_id=? AND person_id=?",(growth,first)),[(1,)])

    def test_injury_fatigue_facts_do_not_reset_and_doubleheader_dates(self):
        person=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='first_team' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:
            c.executemany('INSERT OR IGNORE INTO appearance_days VALUES (?,?)',[(person,d) for d in (2,3,4)])
            c.execute("INSERT INTO condition_events(event_key,person_id,absolute_day,kind,occurred,details_json) VALUES ('test-injury',?,6,'match',1,'{}')",(person,))
            f=activity(c,0,6)[person];self.assertTrue(f['fatigue']);self.assertTrue(f['injured'])
        self.seed_days();before=self.rows('SELECT * FROM appearance_days')
        self.development.settle_current();self.assertEqual(before,self.rows('SELECT * FROM appearance_days'))
        with closing(self.db.connect()) as c,c:
            c.execute('DELETE FROM development_results WHERE 0')
        self.assertTrue(any('injury' in json.loads(r['reasons_json']) for r in self.development.history() if r['person_id']==person))

    def test_transaction_failure_full_rollback_then_concurrent_retry(self):
        self.seed_days();before=self.dump()
        from idol_manager import development_service as module
        original=module._store;calls=[]
        def store(*args,**kwargs):
            calls.append(1);original(*args,**kwargs)
            if len(calls)==3:raise RuntimeError('injected crash')
        with patch.object(module,'_store',side_effect=store):
            with self.assertRaises(RuntimeError):self.development.settle_current()
        self.assertEqual(before,self.dump())
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:DevelopmentService(Database(self.path)).settle_current(),range(2)))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM development_settlements WHERE kind='growth'"),[(1,)])

    def test_continuous_aging_offseason_skip_and_birthday_once(self):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=28')
        original=self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')
        for day in (7,21,77,161,189,203,217):
            with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=?',(day,))
            self.development.settle_current()
        self.assertEqual(self.rows("SELECT absolute_day FROM development_settlements WHERE kind='aging' ORDER BY absolute_day"),[(7,),(21,),(77,),(161,),(217,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM development_settlements WHERE kind='birthday'"),[(2,)])
        self.assertEqual(self.rows('SELECT DISTINCT age FROM idols'),[(30,)])
        self.assertEqual(original,self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill'))

    def test_public_history_does_not_query_pa_or_private_trials(self):
        self.seed_days();self.development.settle_current();original=self.db.connect
        def connect():
            c=original();c.set_authorizer(lambda action,table,column,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table=='development_trials' or (table,column)==('abilities','potential')) else sqlite3.SQLITE_OK);return c
        with patch.object(self.db,'connect',side_effect=connect):
            self.assertTrue(self.development.history());self.assertTrue(self.development.periods())

    def test_real_doubleheader_two_games_one_day_and_basic_trials_only(self):
        row=self.rows('''SELECT week,weekday FROM scheduled_matches GROUP BY week,weekday HAVING COUNT(*)=10 ORDER BY week,weekday LIMIT 1''')[0]
        day=(row[0]-1)*7+row[1]
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=?',(day,))
        self.calendar.ensure_current_schedule();matches=MatchService(self.db,seed_factory=lambda:22)
        own=[f for f in matches.fixtures() if f.player_participates]
        fixed=sorted(p.player.id for p in matches.selection(own[0].id).options)
        for f in matches.fixtures():
            matches.play(f.id,lineups={'ador':tuple(fixed[:f.required])} if f.player_participates else None)
        with closing(self.db.connect()) as c:
            f=activity(c,day,day)[fixed[0]]
            self.assertEqual(len(f['games']),2);self.assertEqual(f['dates'],{day})
            self.assertEqual(sum(f['attempts']),120)

    def test_postseason_waiting_no_automatic_decline_and_history_survives_growth(self):
        self.seed_days(175)
        before=self.rows("SELECT a.person_id,a.skill,a.value FROM abilities a JOIN roster_memberships r ON r.person_id=a.person_id WHERE r.career_status='first_team' ORDER BY a.person_id,a.skill")
        with patch.object(Development,'additional',return_value=None):self.development.settle_current()
        self.assertEqual(before,self.rows("SELECT a.person_id,a.skill,a.value FROM abilities a JOIN roster_memberships r ON r.person_id=a.person_id WHERE r.career_status='first_team' ORDER BY a.person_id,a.skill"))
        self.assertTrue(any('postseason_waiting' in json.loads(r['reasons_json']) for r in self.development.history()))

    def test_internal_birthday_does_not_reveal_unseen_or_unpicked_ca(self):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=77')
        self.development.settle_current()
        birthday=self.rows("SELECT id FROM development_settlements WHERE kind='birthday'")[0][0]
        self.assertEqual(self.rows('SELECT COUNT(*) FROM development_results WHERE settlement_id=?',(birthday,)),[(310,)])
        public=self.development.history(birthday)
        self.assertEqual(len(public),160);self.assertTrue(all(r['agency_id'] is not None for r in public))

    def test_process_exit_mid_settlement_recovers_without_partial_changes(self):
        from idol_manager.config import ROOT
        self.seed_days();before=self.dump()
        code='''import sys,os
from pathlib import Path
from unittest.mock import patch
from idol_manager.database import Database
import idol_manager.development_service as m
original=m._store
def crash(*a,**k):
    original(*a,**k)
    os._exit(17)
with patch.object(m,'_store',side_effect=crash):
    m.DevelopmentService(Database(Path(sys.argv[1]))).settle_current()
'''
        result=subprocess.run([sys.executable,'-c',code,str(self.path)],cwd=ROOT,timeout=20)
        self.assertEqual(result.returncode,17);self.assertEqual(before,self.dump())
        self.development.settle_current();self.assertTrue(self.development.periods())


def list_dump(db):
    with closing(db.connect()) as c:return list(c.iterdump())
