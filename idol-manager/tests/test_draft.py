from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.agencies import AGENCY_SEEDS, INITIAL_FUNDS_KRW
from idol_manager.config import ROOT, SKILLS, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import AgeApprovalRequired, DraftEngine, DraftError
from idol_manager.migrations import V1_STATEMENTS, V2_STATEMENTS, V3_STATEMENTS, initialize_rosters


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="idol_draft_")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "한글 세이브.sqlite3"
        self.database = Database(self.path)
        self.people = tuple(Person(f"id-{i}", f"가상 인물{i:03}", f"가상 인물{i:03}", f"assets/idols/{i}.png") for i in range(310))
        self.database.create_game(self.people, load_settings(), random.Random(2026))
        from tests.game_fixtures import legacy_save
        legacy_save(self.database)
        self.engine = DraftEngine(self.database)

    def rows(self, table):
        with closing(self.database.connect()) as connection:
            return sorted(tuple(row) for row in connection.execute(f"SELECT * FROM {table}"))

    def snapshot(self):
        with closing(self.database.connect()) as connection:
            return list(connection.iterdump())

    def pick_next(self, engine=None):
        engine = engine or self.engine
        turn = engine.state().next_turn
        return engine.pick(turn.agency_id, engine.available_candidates()[0].id,
                           expected_pick_number=turn.pick_number)

    def set_age_16(self, count=12):
        ids = tuple(person.id for person in self.engine.available_candidates()[:count])
        with closing(self.database.connect()) as connection, connection:
            connection.executemany("UPDATE idols SET age=16 WHERE person_id=?", [(person_id,) for person_id in ids])
        return ids

    def test_snake_order_all_rounds_idempotent_start_and_restart(self):
        before = {table: self.rows(table) for table in ("people", "idols", "abilities", "agencies")}
        started = self.engine.start(rng=random.Random(91))
        self.assertEqual((started.status, started.picks_made), ("in_progress", 0))
        order = self.engine.turn_order()
        self.assertEqual(len(order), 160)
        first = [turn.agency_id for turn in order[:10]]
        expected = sorted(agency.id for agency in self.database.agencies())
        random.Random(91).shuffle(expected)
        self.assertEqual(first, expected)
        for round_number in range(1, 17):
            group = order[(round_number-1)*10:round_number*10]
            self.assertEqual([turn.agency_id for turn in group], first if round_number % 2 else first[::-1])
            self.assertEqual([turn.position for turn in group], list(range(1,11)))
            self.assertEqual({turn.round_number for turn in group}, {round_number})
        reopened = DraftEngine(Database(self.path))
        self.assertEqual(started, reopened.start(rng=random.Random(999)))
        self.assertEqual(order, reopened.turn_order())
        for table, rows in before.items():
            self.assertEqual(rows, self.rows(table))

    def test_complete_160_picks_exact_rosters_final_40_and_no_stat_changes(self):
        protected = {table: self.rows(table) for table in ("people", "idols", "abilities", "agencies", "initial_draft_candidates")}
        initial = {person.id for person in self.engine.available_candidates()}
        self.engine.start(rng=random.Random(7))
        picks = [self.pick_next() for _ in range(160)]
        self.assertEqual(len({pick.person_id for pick in picks}), 160)
        self.assertEqual(self.engine.state().status, "completed")
        self.assertIsNone(self.engine.state().next_turn)
        for agency in self.database.agencies():
            roster = self.database.agency_roster(agency.id)
            self.assertEqual(len(roster), 16)
            self.assertEqual({person.status for person in roster}, {"pro_pending"})
        undrafted = self.engine.undrafted_candidates()
        self.assertEqual(len(undrafted), 40)
        self.assertEqual({person.id for person in undrafted}, initial - {pick.person_id for pick in picks})
        self.assertEqual(len(self.database.public_roster()), 40)
        for table, rows in protected.items():
            self.assertEqual(rows, self.rows(table))
        with closing(self.database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM roster_memberships WHERE career_status='unassigned'").fetchone()[0], 150)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM roster_memberships WHERE career_status IN ('first_team','second_team','fa')").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM initial_draft_undrafted").fetchone()[0], 40)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        before = self.snapshot()
        with self.assertRaises(DraftError):
            self.engine.pick(picks[-1].agency_id, undrafted[0].id, expected_pick_number=161)
        self.assertEqual(before, self.snapshot())

    def test_invalid_duplicate_wrong_turn_and_stale_snake_boundary(self):
        person = self.engine.available_candidates()[0]
        with self.assertRaises(DraftError):
            self.engine.pick("ador", person.id, expected_pick_number=1)
        with self.assertRaises(DraftError):
            self.engine.undrafted_candidates()
        self.engine.start(rng=random.Random(4))
        turn = self.engine.state().next_turn
        wrong_agency = next(a.id for a in self.database.agencies() if a.id != turn.agency_id)
        unlisted = next(p.id for p in self.people if p.id not in {c.id for c in self.engine.available_candidates()})
        for agency, identity, expected in ((wrong_agency, person.id, 1), (turn.agency_id, person.id, 2),
                                           (turn.agency_id, "missing", 1), (turn.agency_id, unlisted, 1),
                                           (turn.agency_id, person.id, True)):
            before = self.snapshot()
            with self.assertRaises(DraftError):
                self.engine.pick(agency, identity, expected_pick_number=expected)
            self.assertEqual(before, self.snapshot())
        picked = self.pick_next()
        next_turn = self.engine.state().next_turn
        before = self.snapshot()
        with self.assertRaises(DraftError):
            self.engine.pick(next_turn.agency_id, picked.person_id, expected_pick_number=2)
        self.assertEqual(before, self.snapshot())
        while self.engine.state().picks_made < 10:
            tenth = self.pick_next()
        self.assertEqual(tenth.agency_id, self.engine.state().next_turn.agency_id)
        with self.assertRaises(DraftError):
            self.engine.pick(tenth.agency_id, self.engine.available_candidates()[0].id, expected_pick_number=10)
        self.assertEqual(self.engine.state().picks_made, 10)
        self.pick_next()

    def test_interrupted_resume_across_separate_process_and_two_engine_instances(self):
        self.engine.start(rng=random.Random(9))
        for _ in range(23):
            self.pick_next()
        expected_state, expected_order, expected_picks = self.engine.state(), self.engine.turn_order(), self.engine.picks()
        code = """
import sys
from pathlib import Path
from idol_manager.database import Database
from idol_manager.draft import DraftEngine
engine=DraftEngine(Database(Path(sys.argv[1])))
assert engine.state().picks_made==23
turn=engine.state().next_turn
engine.pick(turn.agency_id,engine.available_candidates()[0].id,expected_pick_number=turn.pick_number)
"""
        result = subprocess.run([sys.executable,"-c",code,str(self.path)],cwd=ROOT,capture_output=True,timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        reopened = DraftEngine(Database(self.path))
        self.assertEqual(reopened.state().picks_made, expected_state.picks_made + 1)
        self.assertEqual(reopened.turn_order(), expected_order)
        self.assertEqual(reopened.picks()[:23], expected_picks)
        self.assertEqual(reopened.state(), self.engine.state())
        self.pick_next(reopened)
        self.assertEqual(self.engine.state().picks_made, 25)

    def test_concurrent_same_turn_requests_only_one_commits(self):
        self.engine.start(rng=random.Random(3))
        turn = self.engine.state().next_turn
        identities = [p.id for p in self.engine.available_candidates()[:2]]
        def submit(identity):
            try:
                DraftEngine(Database(self.path)).pick(turn.agency_id,identity,expected_pick_number=1)
                return "saved"
            except DraftError:
                return "rejected"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, identities))
        self.assertEqual(sorted(results), ["rejected","saved"])
        self.assertEqual(self.engine.state().picks_made, 1)
        self.assertEqual(len(self.database.agency_roster(turn.agency_id)), 1)

    def test_storage_failure_rolls_back_pick_and_trigger_membership(self):
        self.engine.start()
        with closing(self.database.connect()) as connection, connection:
            connection.execute("""CREATE TRIGGER fail_draft_membership BEFORE UPDATE ON roster_memberships
                                  WHEN NEW.career_status='pro_pending' BEGIN SELECT RAISE(ABORT,'failure'); END""")
        before = self.snapshot()
        with self.assertRaises(DraftError):
            self.pick_next()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.engine.state().picks_made, 0)

    def test_final_roster_validation_failure_rolls_back_last_pick_and_completion(self):
        self.engine.start()
        for _ in range(159):
            self.pick_next()
        pool_ids = {row[0] for row in self.rows("initial_draft_candidates")}
        outside_id = next(person.id for person in self.people if person.id not in pool_ids)
        agency_id = "unexpected-agency"
        with closing(self.database.connect()) as connection, connection:
            connection.execute("INSERT INTO agencies VALUES (?,'Unexpected','',1000000000)",(agency_id,))
            connection.execute("UPDATE roster_memberships SET agency_id=?,career_status='pro_pending' WHERE person_id=?", (agency_id,outside_id))
        before = self.snapshot()
        with self.assertRaisesRegex(DraftError,"완료 인원"):
            self.pick_next()
        self.assertEqual(before,self.snapshot())
        self.assertEqual(self.engine.state().status,"in_progress")
        self.assertEqual(self.engine.state().picks_made,159)

    def test_age_correction_storage_error_rolls_back_all_selected_ages(self):
        identities = self.set_age_16(2)
        with closing(self.database.connect()) as connection, connection:
            connection.execute(f"""CREATE TRIGGER fail_age_audit BEFORE INSERT ON draft_age_corrections
                WHEN NEW.person_id='{identities[1]}' BEGIN SELECT RAISE(ABORT,'audit failure'); END""")
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.engine.correct_legacy_ages(approved=True,person_ids=identities)
        self.assertEqual(before,self.snapshot())
        self.assertEqual(len(self.engine.age_issues()),2)

    def test_concurrent_start_uses_one_persisted_order(self):
        def start(seed):
            engine=DraftEngine(Database(self.path))
            engine.start(rng=random.Random(seed))
            return engine.turn_order()
        with ThreadPoolExecutor(max_workers=2) as pool:
            orders=list(pool.map(start,(11,22)))
        self.assertEqual(orders[0],orders[1])
        self.assertEqual(len(orders[0]),160)

    def test_raw_sql_out_of_order_and_duplicate_pick_constraints(self):
        self.engine.start()
        identity = self.engine.available_candidates()[0].id
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError), connection:
                connection.execute("INSERT INTO draft_picks(pick_number,person_id) VALUES (2,?)", (identity,))
        self.pick_next()
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError), connection:
                connection.execute("INSERT INTO draft_picks(pick_number,person_id) VALUES (2,?)", (identity,))
        self.assertEqual(self.engine.state().picks_made, 1)

    def test_blind_human_ai_shared_payload_does_not_read_hidden_attributes(self):
        statements = []
        original_connect = self.database.connect
        def traced_connection():
            connection = original_connect()
            connection.set_trace_callback(statements.append)
            return connection
        with patch.object(self.database, "connect", side_effect=traced_connection):
            self.engine.start(rng=random.Random(11))
            for _ in range(2):  # Same interface for manual choice and a future simple AI choice.
                candidates = self.engine.available_candidates()
                self.assertEqual(set(vars(candidates[0])), {"id","name","photo_path","age"})
                turn = self.engine.state().next_turn
                self.engine.pick(turn.agency_id,candidates[0].id,expected_pick_number=turn.pick_number)
        executed = " ".join(statements).lower()
        for private in ("abilities", "potential", "average", "health", "archetype"):
            self.assertNotIn(private, executed)

    def test_legacy_age_gate_requires_explicit_approval_and_only_selected_ages_change(self):
        ids = self.set_age_16()
        before = self.snapshot()
        with self.assertRaisesRegex(DraftError,"16세는 12명"):
            self.engine.start()
        with self.assertRaises(AgeApprovalRequired):
            self.engine.correct_legacy_ages(person_ids=ids)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.engine.state().status, "not_started")
        protected = {table: self.rows(table) for table in ("abilities","people","agencies","initial_draft_candidates","roster_memberships")}
        result = self.engine.correct_legacy_ages(approved=True, person_ids=ids[:3])
        self.assertTrue(result.backup_path.exists())
        with closing(sqlite3.connect(result.backup_path)) as backup:
            self.assertEqual(backup.execute("SELECT COUNT(*) FROM idols WHERE age=16").fetchone()[0], 12)
        self.assertEqual(len(self.engine.age_issues()), 9)
        with self.assertRaises(DraftError):
            self.engine.start()
        self.engine.correct_legacy_ages(approved=True, person_ids=ids[3:])
        self.assertEqual(self.engine.age_issues(), [])
        for table, rows in protected.items():
            self.assertEqual(rows, self.rows(table))
        self.assertEqual(len(self.rows("draft_age_corrections")), 12)
        after = {row[0]:row for row in self.rows("idols")}
        with closing(sqlite3.connect(result.backup_path)) as backup:
            for row in backup.execute("SELECT * FROM idols"):
                self.assertEqual(after[row[0]], (row[0],17,*row[2:]) if row[0] in ids else row)
        self.engine.start()

    def test_invalid_age_approvals_backup_failure_and_non_16_issue_do_not_mutate(self):
        ids = self.set_age_16(1)
        before = self.snapshot()
        for parameters in ({"approved":True}, {"approved":True,"person_ids":("missing",)},
                           {"approved":True,"person_ids":(ids[0],ids[0])}):
            with self.assertRaises(DraftError):
                self.engine.correct_legacy_ages(**parameters)
            self.assertEqual(before, self.snapshot())
        with patch("idol_manager.draft.backup_database",side_effect=OSError("no backup")):
            with self.assertRaises(OSError):
                self.engine.correct_legacy_ages(approved=True,person_ids=ids)
        self.assertEqual(before, self.snapshot())
        with closing(self.database.connect()) as connection, connection:
            connection.execute("UPDATE idols SET age=27 WHERE person_id=?", (ids[0],))
        with self.assertRaises(DraftError):
            self.engine.correct_legacy_ages(approved=True,person_ids=ids)
        with self.assertRaisesRegex(DraftError,"17~26"):
            self.engine.start()

    def test_start_rejects_incomplete_pool_assigned_roster_and_approval_after_start(self):
        with closing(self.database.connect()) as connection, connection:
            connection.execute("UPDATE roster_memberships SET career_status='fa' WHERE person_id=?", (self.people[0].id,))
        with self.assertRaises(DraftError):
            self.engine.start()
        with closing(self.database.connect()) as connection, connection:
            connection.execute("UPDATE roster_memberships SET career_status='unassigned'")
            connection.execute("DELETE FROM initial_draft_candidates WHERE person_id=(SELECT person_id FROM initial_draft_candidates LIMIT 1)")
        with self.assertRaisesRegex(DraftError,"200"):
            self.engine.start()
        self.database.create_game(self.people,load_settings(),random.Random(2026))
        self.engine.start()
        with self.assertRaises(DraftError):
            self.engine.correct_legacy_ages(approved=True,person_ids=(self.people[0].id,))

    def test_explicit_new_game_clears_draft_and_failed_reset_preserves_it(self):
        self.engine.start()
        self.pick_next()
        before = self.snapshot()
        with closing(self.database.connect()) as c,c:c.execute("CREATE TRIGGER qa_reset_failure BEFORE INSERT ON idols BEGIN SELECT RAISE(ABORT,'injected');END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.create_game(self.people,load_settings(),random.Random(1))
        with closing(self.database.connect()) as c,c:c.execute('DROP TRIGGER qa_reset_failure')
        self.assertEqual(before, self.snapshot())
        self.database.create_game(self.people,load_settings(),random.Random(2))
        self.assertEqual(self.engine.state().status,"not_started")
        self.assertEqual(self.engine.turn_order(),[])
        self.assertEqual(self.engine.picks(),[])
        self.assertEqual(len(self.engine.available_candidates()),200)


class DraftMigrationTests(unittest.TestCase):
    def test_real_v2_shape_upgrades_transactionally_preserving_all_rows_and_ages(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "v2.sqlite3"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("PRAGMA foreign_keys=ON")
                for statement in V1_STATEMENTS + V2_STATEMENTS:
                    connection.execute(statement)
                connection.executemany("INSERT INTO agencies VALUES (?,?,?,?)", [(*a,INITIAL_FUNDS_KRW) for a in AGENCY_SEEDS])
                connection.execute("INSERT INTO people VALUES ('old','기존','기존','assets/idols/기존.png')")
                connection.execute("INSERT INTO idols VALUES ('old',16,77,'extreme',50,'candidate')")
                connection.executemany("INSERT INTO abilities VALUES ('old',?,50,95)",[(s,) for s in SKILLS])
                connection.execute("INSERT INTO game(id) VALUES (1)")
                initialize_rosters(connection)
                connection.execute("PRAGMA user_version=2")
            def rows():
                with closing(sqlite3.connect(path)) as connection:
                    return {t:connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
                            for t in ("people","game","idols","abilities","agencies","roster_memberships","initial_draft_candidates")}
            before = rows()
            with patch("idol_manager.migrations.V3_STATEMENTS",V3_STATEMENTS+("INVALID SQL",)):
                with self.assertRaises(sqlite3.OperationalError):
                    Database(path)
            self.assertEqual(rows(),before)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],2)
                self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='draft_state'").fetchone())
            database = Database(path)
            self.assertEqual(rows(),before)
            self.assertIsNotNone(database.last_backup_path)
            with closing(sqlite3.connect(database.last_backup_path)) as backup:
                self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0],2)
            self.assertEqual(DraftEngine(database).age_issues()[0].age,16)
            self.assertEqual(DraftEngine(database).state().status,"not_started")
            self.assertIsNone(Database(path).last_backup_path)


if __name__ == "__main__":
    unittest.main()
