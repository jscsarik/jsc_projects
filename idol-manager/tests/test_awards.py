"""Twelve fixed-example award checks. No season simulation, no live-save writes."""
from contextlib import closing
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json,random,sqlite3,unittest,hashlib
from unittest.mock import patch
from idol_manager.awards import decide,aggregate,capture_regular_rosters,finalize,AwardError,AWARDS
from idol_manager.config import SKILLS
from idol_manager.database import Database
from tests import test_market as fixture

def record(identity,agency='ador',wins=1,debut=1):
    return dict(id=identity,name=identity,photo_path='',agency=agency,debut=debut,appearances=10,wins=5,losses=5,
        winning_idol=wins,losing_idol=0,leader_games=5,leader_attempts=10,leader_successes=7,
        skills={s:dict(attempts=100,successes=50) for s in SKILLS},contributions={})

class AwardsTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    day=fixture.MarketTests.day;rows=fixture.MarketTests.rows;dump=fixture.MarketTests.dump
    def setUp(self):
        fixture.MarketTests.setUp(self);self.order=[a.id for a in self.service.agencies()]
        self.a,self.b=self.order[:2]

    def select(self,rows,season=1):return decide(rows,self.order,season,random.Random(1))

    def complete_fixture(self):
        """Fixed metadata: 584 double forfeits + one 1v1, not engine simulation."""
        with closing(self.db.connect()) as c,c:
            matches=c.execute('SELECT * FROM scheduled_matches ORDER BY week,weekday,day_order,match_order').fetchall()
            c.execute("UPDATE scheduled_matches SET status='completed'")
            c.execute('UPDATE game_clock SET absolute_day=184')
            c.execute('INSERT INTO season_finals(season,status,frozen_json,standings_json,final_order_json,champion_id) VALUES (1,\'completed\',\'{}\',\'[]\',?,?)',(json.dumps(self.order),self.b))
            for m in matches:
                agencies=[r[0] for r in c.execute('SELECT agency_id FROM match_participants WHERE match_id=? ORDER BY agency_id',(m['id'],))]
                normal=m['id']==matches[0]['id']
                c.execute('INSERT INTO match_results(match_id,resolution,winner_id,loser_id,summary_json) VALUES (?,?,?,?,?)',(m['id'],'normal' if normal else 'double_forfeit',agencies[0] if normal else None,agencies[1] if normal else None,'{}'))
                for j,agency in enumerate(agencies):
                    score=42 if j==0 else 31
                    c.execute('INSERT INTO match_team_stats VALUES (?,?,?,?,?,?,?,?)',(m['id'],agency,score if normal else 0,0,score if normal else 0,'win' if normal and j==0 else 'loss',int(normal and j==0),int(not normal)))
            m=matches[0];agencies=[r[0] for r in c.execute('SELECT agency_id FROM match_participants WHERE match_id=? ORDER BY agency_id',(m['id'],))]
            people=[];sequence=0
            for team,agency in enumerate(agencies):
                person=c.execute('SELECT person_id FROM roster_memberships WHERE agency_id=? LIMIT 1',(agency,)).fetchone()[0];people.append(person)
                successes=40 if team==0 else 30;leader=2 if team==0 else 1
                c.execute('''INSERT INTO match_player_stats VALUES (?,?,?,?,60,?,?,30,30,2,?,0,0,?,?,?, ?,?)''',
                    (m['id'],person,agency,m['content_id'],successes,60-successes,leader,(successes+leader)/62,successes/60,'win' if team==0 else 'loss',int(team==0),int(team==1)))
                for attempt in range(62):
                    sequence+=1;phase='main' if attempt<30 else 'support' if attempt<60 else 'leader'
                    skill='vocal' if attempt<30 else SKILLS[(attempt-30)%8] if attempt<60 else 'leadership'
                    success=int(attempt<successes if attempt<60 else attempt-60<leader)
                    c.execute('INSERT INTO match_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(m['id'],sequence,agency,person,phase,skill,min(attempt+1,60),0,attempt+1,.5,.1 if success else .9,success))
            # End-of-regular registrations make later transfers irrelevant.
            for p in people:
                agency=c.execute('SELECT agency_id FROM roster_memberships WHERE person_id=?',(p,)).fetchone()[0]
                c.execute('INSERT OR REPLACE INTO development_days VALUES (1,167,?,?,?,0)',(p,agency,'first_team'))
            # Excluded data is intentionally huge; aggregators must not read it.
            c.execute("UPDATE special_events SET status='completed'")
        return m['id'],people

    def test_01_mvp_only_winning_idol_and_transfer_totals(self):
        a,b=record('a',self.a,8),record('b',self.b,9);a['losing_idol']=999;b['appearances']=1
        self.assertEqual(self.select([a,b])['mvp']['winner']['id'],'b')
        a['winning_idol']=15;a['contributions']={'old':{'winning_idol':8},'new':{'winning_idol':7}}
        self.assertEqual(self.select([a,b])['mvp']['winner']['winning_idol'],15)

    def test_02_rookie_first_professional_season_only(self):
        rows=[record('veteran',self.a,90,1),record('rookie',self.b,3,2)]
        result=self.select(rows,2)
        self.assertEqual(result['rookie']['winner']['id'],'rookie');self.assertEqual(result['mvp']['winner']['id'],'veteran')
        rows[1]['appearances']=0;rows[1]['winning_idol']=0
        self.assertEqual(self.select(rows,2)['rookie']['winner']['id'],'rookie')

    def test_03_leader_only_additional_success(self):
        a,b=record('a',self.a),record('b',self.b);a['leader_successes']=1;b['leader_successes']=2
        a['skills']['leadership']['successes']=100
        self.assertEqual(self.select([a,b])['leader']['winner']['id'],'b')

    def test_04_top_five_attempts_boundary_never_six(self):
        rows=[record(str(i),self.a) for i in range(6)]
        for i,r in enumerate(rows):r['skills']['vocal']=dict(attempts=1200-i*10,successes=600)
        rows[-1]['skills']['vocal']['successes']=1150
        result=self.select(rows)['vocal'];self.assertEqual(len(result['candidates']),5)
        self.assertNotIn('5',[r['id'] for r in result['candidates']])

    def test_05_exact_fraction_rate_not_rounded(self):
        a,b=record('a',self.a),record('b',self.a)
        a['skills']['vocal']=dict(attempts=100000,successes=85000)
        b['skills']['vocal']=dict(attempts=100001,successes=85001)
        self.assertEqual(self.select([a,b])['vocal']['winner']['id'],'b')
        self.assertEqual(f'{85000/100000:.4f}',f'{85001/100001:.4f}')

    def test_06_main_and_random_actual_skill_events_sum(self):
        identity,people=self.complete_fixture()
        with closing(self.db.connect()) as c:rows,issues=aggregate(c,1)
        self.assertFalse(issues);self.assertEqual(sum(r['appearances'] for r in rows),2)
        self.assertEqual(next(r for r in rows if r['id']==people[0])['skills']['vocal']['attempts'],34)
        self.assertTrue(all(sum(s['attempts'] for s in r['skills'].values())==(60 if r['appearances'] else 0) for r in rows))

    def test_07_excluded_records_and_no_hidden_reads(self):
        identity,people=self.complete_fixture();seen=[]
        with closing(self.db.connect()) as c,c:
            n=c.execute('SELECT MAX(sequence) FROM match_events WHERE match_id=?',(identity,)).fetchone()[0]
            agency=c.execute('SELECT agency_id FROM match_player_stats WHERE person_id=? AND match_id=?',(people[0],identity)).fetchone()[0]
            c.execute('INSERT INTO match_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(identity,n+1,agency,people[0],'deathmatch','vocal',1,1,1,.5,.1,1))
        with closing(self.db.connect()) as c:
            c.set_authorizer(lambda action,table,column,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and table in ('abilities','idols','special_judgments','final_contests') else sqlite3.SQLITE_OK)
            c.set_trace_callback(seen.append);rows,issues=aggregate(c,1)
        self.assertFalse(issues);self.assertEqual(sum(sum(s['attempts'] for s in r['skills'].values()) for r in rows),120)
        self.assertEqual(sum(r['leader_attempts'] for r in rows),4)
        self.assertFalse(any('special_' in q or 'final_contests' in q or 'deathmatch' in q for q in seen))

    def test_08_rank_then_uniform_same_agency_persisted_draw(self):
        a,b=record('a',self.a),record('b',self.b)
        self.assertEqual(self.select([b,a])['mvp']['winner']['id'],'a')
        b['agency']=self.a;outcomes={decide([a,b],self.order,1,random.Random(s))['mvp']['winner']['id'] for s in range(20)}
        self.assertEqual(outcomes,{'a','b'});self.assertTrue(self.select([a,b])['mvp']['draws'])
        rows=[record(str(i),self.a) for i in range(6)];self.assertEqual(len(self.select(rows)['vocal']['candidates']),5)

    def test_09_one_person_can_win_all_eleven(self):
        result=self.select([record('a',self.a)])
        self.assertEqual(len(result),11);self.assertTrue(all(v['winner']['id']=='a' for v in result.values()))

    def test_10_finalize_idempotent_concurrent_atomic_recovery(self):
        identity,people=self.complete_fixture()
        with closing(self.db.connect()) as c,c:c.execute('UPDATE match_player_stats SET winning_idol=0 WHERE match_id=?',(identity,))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.service.awards.finalize(1),range(2)))
        self.assertEqual(sorted(results),[False,True]);self.assertEqual(self.rows('SELECT COUNT(*) FROM individual_awards'),[(11,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM award_match_selections'),[(1,)])
        before=self.dump();Database(self.path);self.service.awards.view(1);self.service.awards.finalize(1);self.assertEqual(before,self.dump())

    def test_11_transferred_retired_profile_and_agency_history_frozen(self):
        identity,people=self.complete_fixture();self.day(167)
        with closing(self.db.connect()) as c,c:
            capture_regular_rosters(c,1)
            old=[tuple(c.execute('SELECT agency_id,career_status FROM roster_memberships WHERE person_id=?',(p,)).fetchone()) for p in people]
            for p in people:
                c.execute('DELETE FROM squad_leaders WHERE person_id=?',(p,));c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(p,))
            for i,p in enumerate(people):c.execute('UPDATE roster_memberships SET agency_id=?,career_status=? WHERE person_id=?',(*old[1-i],p))
        self.day(184);self.service.awards.finalize(1);before=self.service.awards.history(people[0]);self.assertTrue(before)
        self.assertEqual(before[0]['regular_agency_id'],old[0][0]);self.assertEqual(before[0]['awarded_agency_id'],old[1][0])
        with closing(self.db.connect()) as c,c:
            c.execute('DELETE FROM squad_leaders WHERE person_id=?',(people[0],));c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='retired' WHERE person_id=?",(people[0],))
        self.assertEqual(before,self.service.awards.history(people[0]));self.assertTrue(self.service.profiles.get(people[0])['awards'])
        team=before[0]['awarded_agency_id'];self.assertTrue(self.service.awards.history(agency=team))

    def test_12_missing_records_rollback_and_real_save_copy_migration_preserved(self):
        identity,people=self.complete_fixture()
        with closing(self.db.connect()) as c,c:
            c.execute("CREATE TRIGGER fail_middle_award BEFORE INSERT ON individual_awards WHEN NEW.award_type='dance' BEGIN SELECT RAISE(ABORT,'injected'); END")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):self.service.awards.finalize(1)
        self.assertEqual(before,self.dump())
        with closing(self.db.connect()) as c,c:
            c.execute('DROP TRIGGER fail_middle_award');c.execute('DELETE FROM match_events WHERE match_id=? AND sequence=1',(identity,))
        with self.assertRaises(AwardError):self.service.awards.finalize(1)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM individual_awards'),[(0,)])
        # Use the immutable pre-development backup, never the user's live DB.
        report=json.loads((Path(__file__).resolve().parents[1]/'.test-artifacts/awards20_before.json').read_text(encoding='utf8'))
        target=Path(self.temp.name)/'migration.sqlite3'
        with closing(sqlite3.connect(Path(report['backup']).as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)
        db=Database(target);self.assertIsNotNone(db.last_backup_path)
        with closing(db.connect()) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
            for table,expected in report['tables'].items():
                if table=='idols':
                    from tests.migration_fixtures import current_rows
                    with closing(sqlite3.connect(Path(report['backup']).as_uri()+'?mode=ro',uri=True)) as old:
                        self.assertEqual(sorted(tuple(r) for r in c.execute('SELECT * FROM idols')),current_rows(table,old.execute('SELECT * FROM idols').fetchall()))
                    continue
                actual=hashlib.sha256(repr(sorted(tuple(r) for r in c.execute('SELECT * FROM "'+table+'"'))).encode()).hexdigest();self.assertEqual(actual,expected,table)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM season_awards').fetchone()[0],0)

    def test_13_final_completion_hook_and_offseason_missing_data_gate(self):
        identity,people=self.complete_fixture()
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE season_finals SET status='seeded',champion_id=NULL")
            for n,a,b,w in ((1,self.order[2],self.order[3],self.order[2]),(2,self.order[1],self.order[2],self.order[1]),(3,self.a,self.b,None)):
                c.execute('INSERT INTO final_series VALUES (?,?,?,?,?)',(1,n,a,b,w))
            for n in (1,2):
                c.execute('''INSERT INTO final_contests(id,season,kind,round_number,game_number,absolute_day,agencies_json,content_json,required,status,result_json)
                    VALUES (?,1,'post',3,?,184,?,'{}',1,'completed',?)''',(f'fixed-final-{n}',n,json.dumps([self.a,self.b]),json.dumps(dict(order=[self.b,self.a]))))
            row=c.execute("SELECT * FROM final_contests WHERE id='fixed-final-2'").fetchone()
            self.service.finals._advance_series(c,row,self.b)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM individual_awards'),[(11,)])
        self.assertEqual(self.rows('SELECT absolute_day FROM game_clock'),[(184,)])
        # Missing mandatory events must stop before offseason growth or money.
        with closing(self.db.connect()) as c,c:
            c.execute('DELETE FROM season_awards');c.execute('UPDATE game_clock SET absolute_day=188')
            c.execute('DELETE FROM match_events WHERE match_id=? AND sequence=1',(identity,))
        before=self.dump()
        with patch('idol_manager.development_service.advance_development') as growth:
            with self.assertRaises(ValueError):self.service.calendar.advance_day(expected_absolute_day=188)
            growth.assert_not_called()
        self.assertEqual(before,self.dump())

