"""Eight bounded checks. No match/season simulation and no live-save writes."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import json,random,sqlite3,unittest
from idol_manager.config import SKILLS,load_settings
from idol_manager.domain import generate_attributes
from idol_manager.database import Database
from idol_manager.development_service import settle_birthday
from idol_manager.condition_rules import injury_probability,registration_multiplier,required_rest_weeks
from idol_manager.profile_service import ProfileService
from idol_manager.match_service import MatchService
from idol_manager.squads import SquadService
from tests import test_development as fixture


class Health90Tests(unittest.TestCase):
    setUp=fixture.DevelopmentServiceTests.setUp
    rows=fixture.DevelopmentServiceTests.rows
    dump=fixture.DevelopmentServiceTests.dump

    def birthday(self,day=77):
        with closing(self.db.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');c.execute('UPDATE game_clock SET absolute_day=?',(day,))
            runtime=c.execute('SELECT * FROM development_runtime').fetchone()
            settle_birthday(c,day,runtime,json.loads(runtime['rules_json']))

    def test_01_new_generation_keeps_distribution_rng_age_and_cap(self):
        settings=load_settings()
        for seed in range(80):
            with patch('idol_manager.domain.cap_health',side_effect=lambda n:n):raw=generate_attributes(random.Random(seed),settings)
            actual=generate_attributes(random.Random(seed),settings)
            raw['health']=min(90,raw['health']);self.assertEqual(actual,raw)
            self.assertTrue(0<=actual['health']<=90)
        self.assertFalse(self.rows('SELECT 1 FROM idols WHERE health>90 OR health<0'))

    def test_02_backup_migration_clamps_only_health_and_runs_once(self):
        # Reconstruct v14 only in a disposable DB, preserving actual award rows.
        with closing(self.db.connect()) as c,c:
            from tests.migration_fixtures import drop_founding
            drop_founding(c)
            c.execute('DROP TRIGGER health_range_insert');c.execute('DROP TRIGGER health_range_update')
            for table in ('annual_turns','annual_pool','annual_sessions','annual_secrets','annual_entries','annual_intakes','annual_runtime','annual_assets','award_outcomes'):c.execute('DROP TABLE IF EXISTS '+table)
            c.execute("UPDATE idols SET health=100 WHERE person_id='0'")
            c.execute('PRAGMA user_version=14')
            agency=c.execute('SELECT id FROM agencies LIMIT 1').fetchone()[0]
            c.execute("INSERT INTO season_awards VALUES (1,1,'fixed',184,?,?, '[]',CURRENT_TIMESTAMP)",(agency,agency))
        before=self.dump();old_health=self.rows("SELECT health FROM idols WHERE person_id='0'")
        upgraded=Database(self.path);self.assertTrue(upgraded.last_backup_path.is_file())
        with closing(sqlite3.connect(upgraded.last_backup_path)) as old:
            self.assertEqual(old.execute("SELECT health FROM idols WHERE person_id='0'").fetchall(),old_health)
        self.assertEqual(self.rows("SELECT health FROM idols WHERE person_id='0'"),[(90,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM season_awards'),[(1,)])
        snapshot=self.dump();self.assertIsNone(Database(self.path).last_backup_path);self.assertEqual(snapshot,self.dump())
        with closing(self.db.connect()) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
        for value in (91,-1):
            with self.assertRaises(sqlite3.IntegrityError):
                with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET health=? WHERE person_id=\'0\'',(value,))

    def test_03_actual_age_plus_one_health_minus_one_and_audit(self):
        before={r[0]:(r[1],r[2]) for r in self.rows('SELECT person_id,age,health FROM idols')}
        self.birthday()
        for person,age,health in self.rows('SELECT person_id,age,health FROM idols'):
            self.assertEqual(age,before[person][0]+1);self.assertEqual(health,max(0,before[person][1]-1))
        facts=json.loads(self.rows("SELECT facts_json FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE s.kind='birthday' LIMIT 1")[0][0])
        self.assertEqual(facts['health_after'],facts['health_before']-1)

    def test_04_same_season_concurrent_repeat_and_legacy_no_backfill(self):
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:self.birthday(),range(2)))
        before=self.dump();self.birthday();Database(self.path);self.birthday();self.assertEqual(before,self.dump())
        # Existing old birthday marker: no retroactive extra -1 on reload.
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE idols SET health=80 WHERE person_id='0'")
            c.execute("UPDATE development_results SET facts_json='{}' WHERE person_id='0'")
        self.birthday();self.assertEqual(self.rows("SELECT health FROM idols WHERE person_id='0'"),[(80,)])

    def test_05_zero_floor_and_later_season_once(self):
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE idols SET health=0 WHERE person_id='0'");c.execute("UPDATE idols SET health=1 WHERE person_id='1'")
        self.birthday();self.assertEqual(self.rows("SELECT health FROM idols WHERE person_id IN ('0','1') ORDER BY person_id"),[(0,),(0,)])
        self.birthday(294);self.birthday(294)
        self.assertEqual(self.rows("SELECT health FROM idols WHERE person_id IN ('0','1') ORDER BY person_id"),[(0,),(0,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM development_settlements WHERE kind='birthday'"),[(2,)])

    def test_06_health_not_ca_pa_or_automatic_other_stat_changes(self):
        before=self.rows('SELECT * FROM abilities ORDER BY person_id,skill');average=self.rows('SELECT person_id,average FROM idols ORDER BY person_id')
        self.birthday();self.assertEqual(before,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertEqual(average,self.rows('SELECT person_id,average FROM idols ORDER BY person_id'));self.assertEqual(len(SKILLS),8)
        for person,avg in average[:5]:self.assertAlmostEqual(avg,sum(r[0] for r in self.rows('SELECT value FROM abilities WHERE person_id=?',(person,)))/8)

    def test_07_original_injury_formula_and_registration_rest_multiplier(self):
        self.assertEqual([registration_multiplier(w) for w in range(1,7)],[1,1,10,20,30,40])
        for health in (0,50,89,90):
            for weeks in (1,2,3,4,6):
                for kind,base in (('match',.0001),('first_rest',.00005),('second',.0001/3)):
                    self.assertAlmostEqual(injury_probability(health,weeks,kind),min(1,(100-health)*base*registration_multiplier(weeks)))
        self.assertEqual([required_rest_weeks(w) for w in (2,3,4,6)],[0,1,2,2])
        # Resetting registration risk affects the probability, not stored health.
        agency=self.rows('SELECT agency_id FROM player_settings')[0][0]
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team' LIMIT 1",(agency,))[0][0]
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET health=80 WHERE person_id=?',(person,))
        self.assertAlmostEqual(injury_probability(80,1,'match'),.002);self.assertAlmostEqual(injury_probability(80,4,'match'),.04)
        self.assertEqual(self.rows('SELECT health FROM idols WHERE person_id=?',(person,)),[(80,)])

    def test_08_profile_search_comparison_and_engine_use_same_db_health(self):
        agency=self.rows('SELECT agency_id FROM player_settings')[0][0]
        with closing(self.db.connect()) as c:players=MatchService._public_first_team(c,agency)
        profile=ProfileService(self.db);squad=SquadService(self.db).snapshot()
        self.assertTrue(players)
        for p in players:
            actual=self.rows('SELECT health FROM idols WHERE person_id=?',(p.id,))[0][0]
            self.assertEqual(p.health,actual);self.assertEqual(profile.get(p.id)['health'],actual)
            self.assertEqual(next(r for r in profile.search() if r['id']==p.id)['health'],actual)
            self.assertEqual(next(m for m in squad.members if m.id==p.id).health,actual)
            self.assertLessEqual(actual,90)
