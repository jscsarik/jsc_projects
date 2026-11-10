from contextlib import closing
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.config import ROOT, SKILLS, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.migrations import SCHEMA_VERSION, V4_STATEMENTS
from idol_manager.squad_policy import CoverageSquadPolicy
from idol_manager.squads import SquadError, SquadService
from idol_manager.squad_types import SquadMember


class SquadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.class_temp = tempfile.TemporaryDirectory(prefix="idol_squad_template_")
        cls.addClassCleanup(cls.class_temp.cleanup)
        cls.pending_path = Path(cls.class_temp.name)/"pending.sqlite3"
        cls.formed_path = Path(cls.class_temp.name)/"formed.sqlite3"
        database = Database(cls.pending_path)
        people = tuple(Person(f"p-{i}",f"가상 인물{i:03}",f"가상 인물{i:03}",f"assets/idols/{i}.png") for i in range(310))
        database.create_game(people,load_settings(),random.Random(55))
        from tests.game_fixtures import legacy_save
        legacy_save(database)
        engine = DraftEngine(database)
        session = DraftSession(engine)
        session.select_agency("ador")
        engine.start(rng=random.Random(6))
        identities = [person.id for person in engine.available_candidates()[:160]]
        for number,identity in enumerate(identities,1):
            turn = engine.state().next_turn
            engine.pick(turn.agency_id,identity,expected_pick_number=number)
        with closing(database.connect()) as connection,connection:
            connection.execute("UPDATE game_clock SET absolute_day=0")
        cls.copy_db(cls.pending_path,cls.formed_path)
        formed = SquadService(Database(cls.formed_path))
        formed.confirm_initial(tuple(member.id for member in formed.snapshot().members[:5]))

    @staticmethod
    def copy_db(source,target):
        with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(target)) as dst:
            src.backup(dst)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="idol_squad_test_")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"한글 세이브.sqlite3"
        self.copy_db(self.pending_path,self.path)
        self.database = Database(self.path)
        self.squads = SquadService(self.database)

    def formed(self):
        self.copy_db(self.formed_path,self.path)
        return self.squads.snapshot()

    def dump(self):
        with closing(self.database.connect()) as connection:
            return list(connection.iterdump())

    def protected(self):
        with closing(self.database.connect()) as connection:
            return {table:sorted(tuple(r) for r in connection.execute(f"SELECT * FROM {table}")) for table in
                    ("people","idols","abilities","agencies","game","draft_state","draft_turns","draft_picks",
                     "initial_draft_candidates","draft_age_corrections","player_settings")}

    def test_initial_exact_five_remaining_eleven_all_ten_agencies_and_saved_values(self):
        before = self.protected()
        snapshot = self.squads.snapshot()
        identities = tuple(member.id for member in snapshot.members[:5])
        self.squads.confirm_initial(identities,expected_agency_id="ador")
        self.assertEqual(before,self.protected())
        after = self.squads.snapshot()
        self.assertTrue(after.initialized)
        self.assertEqual({m.id for m in after.members if m.squad=="first_team"},set(identities))
        self.assertEqual(sum(m.squad=="second_team" for m in after.members),11)
        self.assertEqual(after.leaders,())
        for agency in self.database.agencies():
            members = self.squads.roster(agency.id)
            self.assertEqual(sum(m.squad=="first_team" for m in members),5)
            self.assertEqual(sum(m.squad=="second_team" for m in members),11)
            self.assertEqual(len({m.id for m in members}),16)
            self.assertEqual(agency.funds_krw,1_000_000_000)
            if agency.id!="ador":
                with closing(self.database.connect()) as connection:
                    leaders = dict(connection.execute("SELECT squad,person_id FROM squad_leaders WHERE agency_id=?",(agency.id,)).fetchall())
                for squad in ("first_team","second_team"):
                    team = [m for m in members if m.squad==squad]
                    chosen = next(m for m in team if m.id==leaders[squad])
                    self.assertEqual(chosen.leadership,max(m.leadership for m in team))

    def test_initial_rejects_wrong_count_duplicates_foreign_and_reconfirmation(self):
        own = tuple(m.id for m in self.squads.snapshot().members)
        foreign = self.squads.roster("sm")[0].id
        for identities in ((),own[:4],own[:6],(own[0],)*5,(*own[:4],foreign)):
            before = self.dump()
            with self.assertRaises(SquadError):
                self.squads.confirm_initial(identities)
            self.assertEqual(before,self.dump())
        self.formed()
        before = self.dump()
        with self.assertRaises(SquadError):
            self.squads.confirm_initial(own[:5])
        self.assertEqual(before,self.dump())

    def test_unfinished_draft_blocks_public_stats_and_formation(self):
        identities = tuple(m.id for m in self.squads.snapshot().members[:5])
        with closing(self.database.connect()) as connection,connection:
            connection.execute("DELETE FROM draft_state")
        statements=[]
        original=self.database.connect
        def traced():
            connection=original(); connection.set_trace_callback(statements.append); return connection
        with patch.object(self.database,"connect",side_effect=traced):
            snapshot=self.squads.snapshot()
            self.assertFalse(snapshot.ready)
            self.assertEqual(snapshot.members,())
            with self.assertRaises(SquadError):
                self.squads.confirm_initial(identities)
            with self.assertRaises(SquadError):
                self.squads.roster("ador")
        self.assertNotIn("join abilities"," ".join(statements).lower())

    def test_monday_swap_and_both_leaders_cleared_when_they_leave(self):
        snapshot = self.formed()
        first = next(m.id for m in snapshot.members if m.squad=="first_team")
        second = next(m.id for m in snapshot.members if m.squad=="second_team")
        self.squads.set_leader("first_team",first,expected_revision=snapshot.revision)
        self.squads.set_leader("second_team",second,expected_revision=self.squads.snapshot().revision)
        self.assertEqual(dict(self.squads.snapshot().leaders),{"first_team":first,"second_team":second})
        before = self.protected()
        self.squads.swap(first,second,expected_revision=self.squads.snapshot().revision)
        after = self.squads.snapshot()
        self.assertEqual(after.leaders,())
        self.assertEqual(next(m.squad for m in after.members if m.id==first),"second_team")
        self.assertEqual(next(m.squad for m in after.members if m.id==second),"first_team")
        self.assertEqual(sum(m.squad=="first_team" for m in after.members),5)
        self.assertEqual(sum(m.squad=="second_team" for m in after.members),11)
        self.assertEqual(before,self.protected())
        self.squads.set_leader("first_team",second,expected_revision=after.revision)
        self.assertEqual(dict(self.squads.snapshot().leaders)["first_team"],second)

    def test_tuesday_blocks_swap_move_and_both_leader_changes_without_writes(self):
        snapshot = self.formed()
        first = next(m.id for m in snapshot.members if m.squad=="first_team")
        second = next(m.id for m in snapshot.members if m.squad=="second_team")
        with closing(self.database.connect()) as connection,connection:
            connection.execute("UPDATE game_clock SET absolute_day=1")
        operations = (lambda:self.squads.swap(first,second,expected_revision=snapshot.revision),
                      lambda:self.squads.move(second,"first_team",expected_revision=snapshot.revision),
                      lambda:self.squads.set_leader("first_team",first,expected_revision=snapshot.revision),
                      lambda:self.squads.set_leader("second_team",second,expected_revision=snapshot.revision))
        for operation in operations:
            before = self.dump()
            with self.assertRaisesRegex(SquadError,"월요일"):
                operation()
            self.assertEqual(before,self.dump())

    def test_leader_must_belong_to_same_team_and_agency(self):
        snapshot = self.formed()
        first = next(m.id for m in snapshot.members if m.squad=="first_team")
        second = next(m.id for m in snapshot.members if m.squad=="second_team")
        foreign = self.squads.roster("sm")[0].id
        for squad,identity in (("first_team",second),("second_team",first),("first_team",foreign),("trainee",first)):
            with self.assertRaises(SquadError):
                self.squads.set_leader(squad,identity,expected_revision=snapshot.revision)
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("INSERT INTO squad_leaders VALUES ('ador','first_team',?)",(second,))
        self.squads.set_leader("first_team",first,expected_revision=snapshot.revision)
        self.squads.set_leader("first_team",None,expected_revision=self.squads.snapshot().revision)
        self.assertEqual(self.squads.snapshot().leaders,())

    def test_database_capacities_unique_membership_and_unlimited_separate_trainees(self):
        snapshot = self.formed()
        first = next(m.id for m in snapshot.members if m.squad=="first_team")
        second = next(m.id for m in snapshot.members if m.squad=="second_team")
        with closing(self.database.connect()) as connection:
            outside = [r[0] for r in connection.execute("SELECT person_id FROM roster_memberships WHERE career_status='unassigned' LIMIT 30")]
        for identity,target in ((second,"first_team"),(first,"second_team"),(outside[0],"pro_pending")):
            with closing(self.database.connect()) as connection:
                with self.assertRaises(sqlite3.IntegrityError),connection:
                    connection.execute("UPDATE roster_memberships SET agency_id='ador',career_status=? WHERE person_id=?",(target,identity))
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("INSERT INTO roster_memberships VALUES (?,'sm','trainee')",(first,))
        with closing(self.database.connect()) as connection,connection:
            connection.executemany("UPDATE roster_memberships SET agency_id='ador',career_status='trainee' WHERE person_id=?",[(p,) for p in outside])
        members=self.squads.snapshot().members
        self.assertEqual(sum(m.squad=="trainee" for m in members),30)
        self.assertEqual(sum(m.squad in ("first_team","second_team") for m in members),16)

    def test_professionals_cannot_return_to_trainee_even_through_fa(self):
        snapshot=self.formed()
        identity=snapshot.members[0].id
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("UPDATE roster_memberships SET career_status='trainee' WHERE person_id=?",(identity,))
        # Test fixture for a later release system; no release API/UI is implemented.
        with closing(self.database.connect()) as connection,connection:
            connection.execute("UPDATE roster_memberships SET career_status='fa',agency_id=NULL WHERE person_id=?",(identity,))
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("UPDATE roster_memberships SET career_status='trainee',agency_id='ador' WHERE person_id=?",(identity,))

    def test_under_five_supported_and_single_promote_demote_respects_available_slots(self):
        snapshot=self.formed()
        first=next(m.id for m in snapshot.members if m.squad=="first_team")
        second=next(m.id for m in snapshot.members if m.squad=="second_team")
        with self.assertRaisesRegex(SquadError,"맞교환"):
            self.squads.move(second,"first_team",expected_revision=snapshot.revision)
        with self.assertRaises(SquadError):
            self.squads.move(first,"trainee",expected_revision=snapshot.revision)
        # A future roster vacancy is modeled directly, without adding release gameplay.
        with closing(self.database.connect()) as connection,connection:
            connection.execute("UPDATE roster_memberships SET career_status='fa',agency_id=NULL WHERE person_id=?",(first,))
        self.assertEqual(sum(m.squad=="first_team" for m in self.squads.snapshot().members),4)
        self.squads.move(second,"first_team",expected_revision=snapshot.revision)
        current=self.squads.snapshot()
        self.assertEqual(sum(m.squad=="first_team" for m in current.members),5)
        with self.assertRaises(SquadError):self.squads.move(second,"second_team",expected_revision=current.revision)
        with closing(self.database.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=7')
        self.squads.move(second,"second_team",expected_revision=current.revision)
        self.assertEqual(sum(m.squad=="first_team" for m in self.squads.snapshot().members),4)

    def test_ai_public_payload_sql_privacy_and_idempotent_initialization(self):
        statements=[]; seen=[]
        class InspectPolicy:
            def plan(self,members):
                seen.extend(members)
                return CoverageSquadPolicy().plan(members)
        self.squads.policy=InspectPolicy()
        original=self.database.connect
        def traced():
            connection=original(); connection.set_trace_callback(statements.append); return connection
        identities=tuple(m.id for m in self.squads.snapshot().members[:5])
        with patch.object(self.database,"connect",side_effect=traced):
            self.squads.confirm_initial(identities)
        self.assertEqual(len(seen),9*16)
        self.assertEqual(len({m.id for m in seen}),9*16)
        for member in seen:
            self.assertNotIn("potential",vars(member))
            self.assertNotIn("archetype",vars(member))
            self.assertNotIn("promising",vars(member))
        for forbidden in ("potential","archetype","promising"):
            self.assertNotIn(forbidden," ".join(statements).lower())
        before=self.dump()
        self.squads.initialize_ai_agencies()
        self.assertEqual(before,self.dump())

    def test_ai_coverage_can_prefer_specialists_over_top_five_means(self):
        members=[]
        for i in range(16):
            values=[70]*8 if i<5 else [40]*8
            if i>=5:
                values[(i-5)*2%8]=100
                values[((i-5)*2+1)%8]=100
            members.append(SquadMember(str(i),f"AI{i}","",20,"pro_pending",sum(values)/8,90,*values))
        plan=CoverageSquadPolicy().plan(members)
        self.assertEqual(len(set(plan.first_team_ids)),5)
        self.assertNotEqual(set(plan.first_team_ids),{str(i) for i in range(5)})
        first=[m for m in members if m.id in plan.first_team_ids]
        second=[m for m in members if m.id not in plan.first_team_ids]
        self.assertEqual(next(m.leadership for m in first if m.id==plan.first_leader_id),max(m.leadership for m in first))
        self.assertEqual(next(m.leadership for m in second if m.id==plan.second_leader_id),max(m.leadership for m in second))

    def test_ai_failure_rolls_back_player_and_preceding_ai_formations(self):
        class FailingPolicy:
            calls=0
            def plan(self,members):
                self.calls+=1
                if self.calls==2:
                    raise SquadError("AI 계획 실패")
                return CoverageSquadPolicy().plan(members)
        self.squads.policy=FailingPolicy()
        before=self.dump()
        with self.assertRaises(SquadError):
            self.squads.confirm_initial(tuple(m.id for m in self.squads.snapshot().members[:5]))
        self.assertEqual(before,self.dump())

    def test_stale_revision_and_storage_failure_leave_both_teams_unchanged(self):
        snapshot=self.formed()
        first=next(m.id for m in snapshot.members if m.squad=="first_team")
        second=next(m.id for m in snapshot.members if m.squad=="second_team")
        self.squads.set_leader("first_team",first,expected_revision=snapshot.revision)
        before=self.dump()
        with self.assertRaisesRegex(SquadError,"다른 창"):
            self.squads.swap(first,second,expected_revision=snapshot.revision)
        self.assertEqual(before,self.dump())
        with closing(self.database.connect()) as connection,connection:
            connection.execute("""CREATE TRIGGER fail_swap BEFORE UPDATE ON roster_memberships
                WHEN NEW.career_status='second_team' BEGIN SELECT RAISE(ABORT,'fixture failure'); END""")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            self.squads.swap(first,second,expected_revision=self.squads.snapshot().revision)
        self.assertEqual(before,self.dump())

    def test_restart_in_separate_process_preserves_formations_leaders_and_clock(self):
        snapshot=self.formed()
        first=next(m.id for m in snapshot.members if m.squad=="first_team")
        self.squads.set_leader("first_team",first,expected_revision=snapshot.revision)
        before=self.dump()
        code="""
from pathlib import Path
import sys
from idol_manager.database import Database
from idol_manager.squads import SquadService
s=SquadService(Database(Path(sys.argv[1]))).snapshot()
assert s.initialized and len(s.members)==16
assert sum(m.squad=='first_team' for m in s.members)==5
assert dict(s.leaders)['first_team']==sys.argv[2]
assert s.management_date.absolute_day==0
"""
        result=subprocess.run([sys.executable,"-c",code,str(self.path),first],cwd=ROOT,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(before,self.dump())

    def test_existing_new_game_action_resets_squad_metadata_only_after_success(self):
        snapshot=self.formed()
        first=next(m.id for m in snapshot.members if m.squad=="first_team")
        self.squads.set_leader("first_team",first,expected_revision=snapshot.revision)
        people=tuple(Person(f"p-{i}",f"가상 인물{i:03}",f"가상 인물{i:03}",f"assets/idols/{i}.png") for i in range(310))
        before=self.dump()
        from tests.migration_fixtures import fail_new_game
        with self.assertRaises(sqlite3.IntegrityError),fail_new_game(self.database):
            self.database.create_game(people,load_settings(),random.Random(8))
        self.assertEqual(before,self.dump())
        self.database.create_game(people,load_settings(),random.Random(8))
        with closing(self.database.connect()) as connection:
            for table in ("squad_formations","squad_leaders","professional_history","player_settings"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],0)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(),[])
        self.assertFalse(self.squads.snapshot().ready)

    def test_v3_to_v4_backup_migration_rollback_and_old_rows_preserved(self):
        with closing(self.database.connect()) as connection,connection:
            from tests.migration_fixtures import drop_finance
            drop_finance(connection)
            old_triggers={"draft_pick_guard","draft_pick_membership","player_agency_insert_guard","player_agency_update_guard","player_agency_delete_guard"}
            names=[r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")]
            for name in names:
                if name not in old_triggers:
                    connection.execute(f"DROP TRIGGER {name}")
            for view in ("special_standings","idol_special_career_stats","regular_standings","idol_regular_career_stats","idol_content_stats","idol_ability_stats"):
                connection.execute(f"DROP VIEW {view}")
            for table in ("development_trials","development_results","development_days","development_settlements","development_runtime","final_contests","final_series","season_honors","season_finals","calendar_v9_archive","draft_estimates","special_points","special_judgments","special_ability_stats","special_player_stats","special_team_results","special_rounds","special_sessions",
                          "condition_events","appearance_days","player_conditions","condition_day_runs","condition_runtime",
                          "match_events","match_ability_stats","match_player_stats","match_team_stats","match_results","match_runs",
                          "match_participants","scheduled_matches","special_events","season_schedules","legacy_game_clock",
                          "squad_leaders","squad_formations","professional_history","game_clock"):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("PRAGMA user_version=3")
        before=self.protected()
        with patch("idol_manager.migrations.V4_STATEMENTS",V4_STATEMENTS+("INVALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):
                Database(self.path)
        self.assertEqual(before,self.protected())
        with closing(self.database.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],3)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='game_clock'").fetchone())
        upgraded=Database(self.path)
        self.assertIsNotNone(upgraded.last_backup_path)
        self.assertEqual(before,self.protected())
        with closing(upgraded.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM professional_history").fetchone()[0],160)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM squad_formations").fetchone()[0],0)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(),[])
        self.assertEqual(self.squads.snapshot().management_date.weekday(),0)


if __name__=="__main__":
    unittest.main()
