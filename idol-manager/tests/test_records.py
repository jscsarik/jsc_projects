"""Two small fixed seasons. No engine simulation and no live-save writes."""
from contextlib import closing
from pathlib import Path
import json,os,random,sqlite3,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.config import load_settings,SKILLS
from idol_manager.service import GameService
from idol_manager.records_service import RecordsService


class RecordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.folder=tempfile.TemporaryDirectory(prefix='idol_records24_');cls.addClassCleanup(cls.folder.cleanup)
        cls.root=Path(cls.folder.name);cls.base=cls.root/'fixed.sqlite3'
        db=Database(cls.base);db.create_game(tuple(Person(f'p{i}',f'고정 선수 {i}',f'fixed{i}',f'missing/{i}.png') for i in range(8)),load_settings(),random.Random(4))
        from tests.game_fixtures import legacy_save
        legacy_save(db,schedule=True)
        service=GameService(cls.root,cls.base);cls.order=[a.id for a in service.agencies()];cls.a,cls.b=cls.order[:2]
        with closing(db.connect()) as c,c:
            c.execute("UPDATE roster_memberships SET agency_id=?,career_status='first_team' WHERE person_id='p0'",(cls.a,))
            c.execute("UPDATE roster_memberships SET agency_id=?,career_status='second_team' WHERE person_id='p1'",(cls.b,))
            # p2 is a private, unpicked candidate. Its stored ranges must be used.
            c.execute("UPDATE idols SET status='candidate' WHERE person_id='p2'")
            c.execute("UPDATE game_clock SET absolute_day=300")
            c.execute("INSERT INTO season_schedules(season,rules_digest,rules_json,regular_count,special_count) VALUES (2,'fixed','{}',585,6)")
            content=service.records.content_catalog()[0];cls.content=content['id']
            first=c.execute('SELECT * FROM scheduled_matches LIMIT 1').fetchone();cls.first=first['id'];cls.first_content=first['content_id']
            for season,count in ((1,1),(2,9)):
                for i in range(count):
                    identity=first['id'] if season==1 else f'fixed-{season}-{i}'
                    if season==2:c.execute('''INSERT INTO scheduled_matches(id,season,week,weekday,day_order,match_order,content_id,content_name,main_abilities_json,participants_min,participants_max,status)
                        VALUES (?,2,?,?,?,?,?,?,?,1,1,'completed')''',(identity,1+i//5,2 if i==1 else 2+i%5,1 if i!=1 else 2,i+1,cls.content,content['name'],json.dumps(['vocal','dance'])))
                    else:c.execute("UPDATE scheduled_matches SET status='completed' WHERE id=?",(identity,))
                    winner=cls.a if i<6 else cls.b;loser=cls.b if winner==cls.a else cls.a
                    c.execute("INSERT INTO match_results(match_id,resolution,winner_id,loser_id,summary_json) VALUES (?,'normal',?,?,'{}')",(identity,winner,loser))
                    for agency in (cls.a,cls.b):c.execute('INSERT INTO match_team_stats VALUES (?,?,40,0,40,?,?,0)',(identity,agency,'win' if agency==winner else 'loss',int(agency==winner)))
                    # p0 transfers to B in season 2; historical A facts remain.
                    agency=cls.a if season==1 else cls.b;success=54 if season==1 else 42
                    outcome='win' if agency==winner else 'loss';winning=int(outcome=='win');losing=1-winning
                    c.execute('INSERT INTO match_player_stats VALUES (?,?,?,?,60,?,?,30,30,2,1,10,5,?,?,?, ?,?)',
                        (identity,'p0',agency,first['content_id'] if season==1 else cls.content,success,60-success,(success+1)/62,success/60,outcome,winning,losing))
                    for attempt in range(72):
                        phase='main' if attempt<30 else 'support' if attempt<60 else 'leader' if attempt<62 else 'deathmatch'
                        skill='vocal' if attempt<30 or phase=='deathmatch' else 'leadership' if phase=='leader' else SKILLS[(attempt-30)%8]
                        succeeded=int(attempt<success) if attempt<60 else int(attempt%2==0)
                        c.execute('INSERT INTO match_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(identity,attempt+1,agency,'p0',phase,skill,min(attempt+1,60),0 if attempt<62 else 1,attempt+1,.5,.1 if succeeded else .9,succeeded))
                ranks=cls.order if season==1 else list(reversed(cls.order))
                frozen=[dict(agency_id=a,played=count if a in (cls.a,cls.b) else 0,wins=(1 if season==1 else 6) if a==cls.a else (0 if season==1 else 3) if a==cls.b else 0,
                    losses=(0 if season==1 else 3) if a==cls.a else (1 if season==1 else 6) if a==cls.b else 0,
                    regular_points=(1 if season==1 else 6) if a==cls.a else (0 if season==1 else 3) if a==cls.b else 0,special_points=2 if a==cls.a else 0,
                    points=(1 if season==1 else 6) if a==cls.a else (0 if season==1 else 3) if a==cls.b else 0) for a in ranks]
                c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json,final_order_json,champion_id) VALUES (?,'completed','{}',?,?,?)",(season,json.dumps(frozen),json.dumps(ranks),cls.b))
                c.execute("INSERT INTO season_awards(season,seed,finalized_day,regular_first,champion,records_json) VALUES (?,'fixed',?,?,?,'{}')",(season,season*217-1,ranks[0],cls.b))
                stats=dict(id='p0',name='고정 선수 0',photo_path='',agency=agency,debut=1,appearances=count,wins=1,losses=0,winning_idol=1,losing_idol=0,leader_attempts=2,leader_successes=1,skills={k:dict(attempts=30,successes=20) for k in SKILLS})
                for award in ('mvp','vocal'):c.execute("INSERT INTO individual_awards VALUES (?,?,?,?,?,1,?,'[]','[]')",(season,award,'p0',agency,agency,json.dumps(stats)))
            c.execute("INSERT INTO market_history(id,person_id,from_agency,to_agency,absolute_day,kind) VALUES ('transfer24','p0',?,?,220,'trade')",(cls.a,cls.b))
            c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='retired' WHERE person_id='p0'")
            # One special round, one PS game and one tiebreak: separate facts.
            e=c.execute('SELECT id FROM special_events LIMIT 1').fetchone()[0]
            c.execute("INSERT INTO special_sessions VALUES (?,'fixed','1','[]','[]')",(e,))
            c.execute("INSERT INTO special_rounds VALUES ('special24',?,'upper','special-x','고정 특별전','[\"vocal\",\"dance\"]',1,30,'[]','1','completed','{}','{}','')",(e,))
            c.execute("INSERT INTO special_team_results VALUES ('special24',?,1,20,0,0)",(cls.a,))
            c.execute("INSERT INTO special_player_stats VALUES ('special24','p0',?,'special-x',30,20,10,15,15,0,0,0,0,?)",(cls.a,20/30))
            for n in range(30):c.execute("INSERT INTO special_judgments VALUES ('special24',? ,?,'p0',?,'vocal',1,0,1,.5,.1,?)",(n+1,cls.a,'main' if n<15 else 'support',int(n<20)))
            c.execute("INSERT INTO special_points VALUES (?,?, 'upper','special24',2)",(e,cls.a))
            for kind,identity,day in (('post','post24',170),('tie','tie24',168)):
                player=dict(person_id='p0',agency_id=cls.a,content_id=cls.content,base_attempts=60,base_successes=50,outcome='win')
                events=[dict(person_id='p0',agency_id=cls.a,phase='main' if n<30 else 'support',skill='vocal',success=n<50) for n in range(60)]
                c.execute("INSERT INTO final_contests(id,season,kind,round_number,game_number,absolute_day,agencies_json,content_json,required,status,result_json,events_json) VALUES (?,1,?,1,1,?,'[]',?,1,'completed',?,?)",(identity,kind,day,json.dumps(dict(id=cls.content,name=content['name'])),json.dumps(dict(players=[player],teams=[dict(agency_id=cls.a,outcome='win',total_score=50)],order=[cls.a,cls.b])),json.dumps(events)))
            c.execute('INSERT INTO final_series VALUES (1,1,?,?,?)',(cls.a,cls.b,cls.a))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'game.sqlite3'
        with closing(sqlite3.connect(self.base)) as src,closing(sqlite3.connect(self.path)) as dst:src.backup(dst)
        self.db=Database(self.path);self.api=RecordsService(self.db)
    def player(self,**kw):return next(r for r in self.api.players(**kw) if r['id']=='p0')
    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())
    def test_01_ten_official_ranks_and_frozen_points(self):
        rows=self.api.league(1);self.assertEqual([r['rank'] for r in rows],list(range(1,11)))
        a=next(r for r in rows if r['agency_id']==self.a);self.assertEqual((a['regular_points'],a['special_points'],a['penalty'],a['points']),(1,2,-2,1))
    def test_02_regular_first_differs_from_champion(self):
        rows=self.api.league(1);self.assertEqual(rows[0]['agency_id'],self.a);self.assertFalse(rows[0]['champion']);self.assertTrue(next(r for r in rows if r['agency_id']==self.b)['champion'])
    def test_03_cumulative_champions_no_duplicate_honors(self):
        self.assertEqual(next(r for r in self.api.agencies() if r['id']==self.b)['champions'],2)
        self.assertEqual([r['cumulative'] for r in self.api.champions()],[1,2])
    def test_04_ten_actual_appearances_not_judgment_count(self):
        self.assertEqual(self.player()['appearances'],10);self.assertEqual(self.player(season=2)['appearances'],9)
        self.assertEqual(next(r for r in self.api.players() if r['id']=='p1')['appearances'],0)
        with closing(self.db.connect()) as c:
            self.assertEqual(c.execute("SELECT COUNT(DISTINCT m.id),COUNT(DISTINCT (m.season-1)*217+(m.week-1)*7+m.weekday) FROM scheduled_matches m JOIN match_player_stats p ON p.match_id=m.id WHERE p.person_id='p0' AND m.id IN('fixed-2-0','fixed-2-1')").fetchone()[:],(2,1))
    def test_05_winning_losing_idol_and_selection_ledger_not_double(self):
        p=self.player();self.assertEqual(p['winning_idol']+p['losing_idol'],10)
        with closing(self.db.connect()) as c,c:c.execute("INSERT INTO award_match_selections VALUES (?,'winning_idol','p0','fixed')",(self.first,))
        self.assertEqual(self.player()['winning_idol'],p['winning_idol'])
    def test_06_actual_skill_main_random_leader_and_dm_separate(self):
        p=self.player();self.assertEqual(p['attempts'],600);self.assertEqual(p['successes'],432)
        self.assertEqual(sum(v['attempts'] for v in p['skills'].values()),600)
        self.assertGreater(p['skills']['vocal']['attempts'],300)
        self.assertEqual((p['leader_attempts'],p['deathmatch_attempts']),(20,100))
    def test_07_weighted_success_rate_not_average(self):
        self.assertAlmostEqual(self.player()['rate'],.72);self.assertAlmostEqual(self.player(season=1)['rate'],.9);self.assertAlmostEqual(self.player(season=2)['rate'],.7)
    def test_08_special_post_tie_never_regular(self):
        self.assertEqual(self.player(kind='special')['appearances'],1);self.assertEqual(self.player(kind='postseason')['appearances'],1);self.assertEqual(self.player(kind='tiebreak')['appearances'],1)
        self.assertEqual(self.player(kind=None)['appearances'],13)
        self.assertTrue(all(r['kind']=='regular' for r in self.api.contents()))
    def test_09_transfer_preserves_old_agency_and_total(self):
        h=self.api.player_history('p0');reg=[r for r in h['seasons'] if r['kind']=='regular'];self.assertEqual(sum(r['appearances'] for r in reg),10)
        self.assertEqual(self.player(agency=self.a)['appearances'],1);self.assertEqual(self.player(agency=self.b)['appearances'],9);self.assertEqual(len(h['moves']),1)
        # Two affiliations in the SAME season must remain separate and total 9.
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE match_player_stats SET agency_id=?,outcome='win',winning_idol=1,losing_idol=0 WHERE match_id='fixed-2-0' AND person_id='p0'",(self.a,))
            c.execute("UPDATE match_events SET agency_id=? WHERE match_id='fixed-2-0' AND person_id='p0'",(self.a,))
        rows=[r for r in self.api.player_history('p0')['seasons'] if r['season']==2 and r['kind']=='regular']
        self.assertEqual(sorted(r['appearances'] for r in rows),[1,8]);self.assertEqual(sum(r['appearances'] for r in rows),9)
    def test_10_retired_player_profile_and_history(self):
        from idol_manager.profile_service import ProfileService
        self.assertEqual(self.player()['career_status'],'retired');self.assertTrue(ProfileService(self.db).get('p0')['matches'])
    def test_11_awards_same_person_multiple_types_old_agency(self):
        h=self.api.player_history('p0');self.assertEqual(len(h['awards']),4);self.assertEqual(self.player()['awards'],4);self.assertEqual(h['awards'][0]['awarded_agency_id'],self.a)
    def test_12_both_comparisons_current_and_history_distinct(self):
        a,b=self.api.compare_players('p0','p2');self.assertTrue(a['exact']);self.assertFalse(b['exact']);self.assertIsNone(b['health']);self.assertIsNone(b['salary'])
        self.assertTrue(all(high-low==4 for low,high in b['bounds']))
        a,b=self.api.compare_agencies(self.a,self.b);self.assertIsNone(a['current_pro_ca']);self.assertEqual(b['current_pro_count'],1)
    def test_13_no_pa_or_secrets_read_private_ca_not_queried(self):
        original=self.db.connect
        def connection():
            c=original();c.set_authorizer(lambda action,table,col,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table=='annual_secrets' or col in ('potential','archetype')) else sqlite3.SQLITE_OK);return c
        from unittest.mock import patch
        with patch.object(self.db,'connect',side_effect=connection):
            a,b=self.api.compare_players('p0','p2');self.api.players();self.api.leaders()
        self.assertNotIn('potential',str((a,b)));self.assertNotIn('special',b)
    def test_14_reads_leave_all_game_rows_unchanged(self):
        before=self.dump();rng=random.getstate();self.api.players();self.api.league(1);self.api.champions();self.api.agencies();self.api.contents(kind=None);self.api.player_history('p0');self.api.agency_history(self.a,1);self.api.compare_players('p0','p2');self.api.leaders()
        self.assertEqual(before,self.dump());self.assertEqual(rng,random.getstate())
    def test_15_integrity_missing_snapshots_and_profile_content_agreement(self):
        h=self.api.agency_history(self.a,1);self.assertIsNone(h['finances']['end']);self.assertIsNone(h['finances']['end_debt'])
        from idol_manager.profile_service import ProfileService
        self.assertEqual(ProfileService(self.db).content_statistics('p0',season=1,kind='regular'),self.api.content_players(person='p0',season=1,kind='regular'))
        self.assertEqual(len(self.api.content_catalog()),30)
        with closing(self.db.connect()) as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
        # Legacy aggregate fallback is exclusive: never add to saved events.
        with closing(self.db.connect()) as c,c:
            c.execute('INSERT INTO match_ability_stats SELECT match_id,person_id,phase,skill,COUNT(*),SUM(success),COUNT(*)-SUM(success) FROM match_events WHERE match_id=? AND phase IN(\'main\',\'support\') GROUP BY match_id,person_id,phase,skill',(self.first,))
        self.assertEqual(self.player()['attempts'],600)
        with closing(self.db.connect()) as c,c:
            c.execute('DELETE FROM match_events WHERE match_id=?',(self.first,))
        p=self.player();self.assertEqual(p['attempts'],600);self.assertEqual(sum(r['attempts'] for r in p['skills'].values()),600)
        self.assertEqual((p['leader_attempts'],p['deathmatch_attempts']),(20,100))
