from contextlib import closing
from pathlib import Path
from collections import Counter
import json,tempfile,unittest
from idol_manager.database import Database
from idol_manager.special_service import SpecialService
from idol_manager.development_service import activity,DevelopmentService
from tests import test_special_service as fixture


class DevelopmentActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.SpecialServiceTests.setUpClass.__func__(cls)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'activity.sqlite3'
        fixture.fixture.copy_db(self.template,self.path);self.db=Database(self.path)

    def test_real_special_first_team_only_main_support_counts_and_no_recalculation(self):
        special=SpecialService(self.db,seed_factory=lambda:1827);event=special.events()[0]['id'];special.start(event)
        for stage in ('upper','lower','final'):special.play(next(r['id'] for r in special.state(event)['rounds'] if r['stage']==stage))
        expected=Counter();main=Counter();second_ids=set()
        with closing(self.db.connect()) as c:
            for r in c.execute('SELECT r.id,r.input_json FROM special_rounds r WHERE event_id=?',(event,)):
                roles=json.loads(r['input_json'])['conditions']['squads']
                for p,role in roles.items():
                    if role=='second_team':second_ids.add(p)
                for e in c.execute("SELECT person_id,skill,phase,success FROM special_judgments WHERE round_id=? AND phase IN('main','support')",(r['id'],)):
                    if roles[e['person_id']]=='first_team':
                        expected[e['person_id']]+=1;main[e['person_id']]+=int(e['phase']=='main' and e['success'])
            facts=activity(c,27,27)
            for person,n in expected.items():
                regular=c.execute('''SELECT COUNT(*) FROM match_events e JOIN scheduled_matches m ON m.id=e.match_id
                    WHERE e.person_id=? AND m.week=4 AND m.weekday=6 AND e.phase IN('main','support')''',(person,)).fetchone()[0]
                self.assertEqual(sum(facts[person]['attempts']),n+regular)
            self.assertTrue(second_ids)
            self.assertTrue(all(not facts[p]['games'] for p in second_ids if p not in expected))
            saved=[tuple(r) for r in c.execute('SELECT * FROM special_judgments ORDER BY round_id,sequence')]
            c.execute('UPDATE game_clock SET absolute_day=28');c.commit()
        DevelopmentService(self.db).settle_current()
        with closing(self.db.connect()) as c:self.assertEqual(saved,[tuple(r) for r in c.execute('SELECT * FROM special_judgments ORDER BY round_id,sequence')])

    def test_postseason_basic_events_included_tie_deathmatch_and_leader_excluded(self):
        with closing(self.db.connect()) as c,c:
            person=c.execute("SELECT person_id FROM roster_memberships WHERE career_status='first_team' LIMIT 1").fetchone()[0]
            events=[dict(person_id=person,phase=p,skill=s,success=True) for p,s in (
                ('main','vocal'),('support','dance'),('leader','leadership'),('deathmatch','vocal'))]
            c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (1,'seeded','{}','[]')")
            for identity,kind,day in (('post','post',170),('tie','tie',168)):
                c.execute('''INSERT INTO final_contests(id,season,kind,round_number,game_number,absolute_day,agencies_json,content_json,required,status,events_json)
                    VALUES (?,1,?,99,1,?,'[]','{}',1,'completed',?)''',(identity,kind,day,json.dumps(events)))
            facts=activity(c,168,174)[person]
            self.assertEqual(sum(facts['attempts']),2);self.assertEqual(sum(facts['main_successes']),1)
            self.assertEqual(facts['dates'],{170});self.assertEqual(len(facts['games']),1)
