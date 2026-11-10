from contextlib import closing
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.agencies import AGENCY_SEEDS, INITIAL_FUNDS_KRW
from idol_manager.config import SKILLS, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.migrations import SCHEMA_VERSION, V1_STATEMENTS, V2_STATEMENTS


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="idol_phase2_")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "한글 DB.sqlite3"
        self.make_legacy_save()

    def make_legacy_save(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            for statement in V1_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version=1")
            connection.execute("INSERT INTO game VALUES (1,'2026-01-01 12:00:00')")
            for number in range(310):
                person = f"legacy-{number}"
                name = f"기존 인물 {number:03}"
                connection.execute("INSERT INTO people VALUES (?,?,?,?)", (person, name, name, f"assets/idols/{name}.png"))
                connection.execute("INSERT INTO idols VALUES (?,16,77,'balanced',50,?)",
                                   (person, "candidate" if number < 200 else "unseen"))
                connection.executemany("INSERT INTO abilities VALUES (?,?,50,90)", [(person, skill) for skill in SKILLS])

    def legacy_rows(self, path=None):
        with closing(sqlite3.connect(path or self.path)) as connection:
            return {table: connection.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
                    for table in ("people", "game", "idols", "abilities")}

    def test_v1_migration_backup_preserves_all_values_and_candidate_identity(self):
        before = self.legacy_rows()
        database = Database(self.path)
        self.assertEqual(before, self.legacy_rows())
        self.assertIsNotNone(database.last_backup_path)
        self.assertEqual(before, self.legacy_rows(database.last_backup_path))
        with closing(sqlite3.connect(database.last_backup_path)) as backup:
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(len(database.agencies()), 10)
        self.assertTrue(all(a.funds_krw == INITIAL_FUNDS_KRW for a in database.agencies()))
        self.assertEqual({a.id for a in database.agencies()}, {row[0] for row in AGENCY_SEEDS})
        self.assertEqual({p.id for p in database.initial_draft_candidates()}, {f"legacy-{i}" for i in range(200)})
        self.assertEqual(database.public_roster(), database.initial_draft_candidates())
        with closing(database.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id IS NULL AND career_status='unassigned'").fetchone()[0], 310)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM initial_draft_candidates").fetchone()[0], 200)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_memberships_statuses_roster_queries_and_repeat_open(self):
        database = Database(self.path)
        assignments = [("ador", "first_team", "legacy-0"), ("ador", "second_team", "legacy-1"),
                       ("ador", "trainee", "legacy-2"), ("sm", "first_team", "legacy-3"),
                       (None, "fa", "legacy-4"), (None, "retired", "legacy-5")]
        with closing(database.connect()) as connection, connection:
            connection.executemany("UPDATE roster_memberships SET agency_id=?,career_status=? WHERE person_id=?", assignments)
            connection.execute("UPDATE agencies SET funds_krw=123456789 WHERE id='ador'")
        for _ in range(2):
            reopened = Database(self.path)
            self.assertIsNone(reopened.last_backup_path)
            ador = reopened.agency_roster("ador")
            self.assertEqual({p.id for p in ador}, {"legacy-0", "legacy-1", "legacy-2"})
            self.assertEqual({p.status for p in ador}, {"first_team", "second_team", "trainee"})
            self.assertEqual([p.id for p in reopened.agency_roster("sm")], ["legacy-3"])
            self.assertEqual(reopened.agency_roster("yg"), [])
            self.assertEqual(next(a.funds_krw for a in reopened.agencies() if a.id == "ador"), 123456789)
            self.assertEqual(len(reopened.initial_draft_candidates()), 194)
            for person in ador + reopened.initial_draft_candidates():
                self.assertEqual(set(vars(person)), {"id", "name", "photo_path", "age", "status"})
            with closing(reopened.connect()) as connection:
                self.assertEqual(connection.execute("SELECT career_status FROM roster_memberships WHERE person_id='legacy-4'").fetchone()[0], "fa")
                self.assertEqual(connection.execute("SELECT career_status FROM roster_memberships WHERE person_id='legacy-5'").fetchone()[0], "retired")
        with self.assertRaises(ValueError):
            database.agency_roster("unknown")
        self.assertEqual(len(list((self.path.parent / "backups").glob("*.sqlite3"))), 1)

    def test_status_fund_and_reference_constraints(self):
        database = Database(self.path)
        invalid_updates = (
            ("first_team", None), ("second_team", None), ("trainee", None),
            ("fa", "ador"), ("retired", "ador"), ("unassigned", "ador"),
            ("invalid", None), ("first_team", "nonexistent"),
        )
        for status, agency in invalid_updates:
            with self.subTest(status=status, agency=agency), closing(database.connect()) as connection:
                with self.assertRaises(sqlite3.IntegrityError), connection:
                    connection.execute("UPDATE roster_memberships SET career_status=?,agency_id=? WHERE person_id='legacy-0'", (status, agency))
        for funds in (-1, 1.5):
            with self.subTest(funds=funds), closing(database.connect()) as connection:
                with self.assertRaises(sqlite3.IntegrityError), connection:
                    connection.execute("UPDATE agencies SET funds_krw=? WHERE id='ador'", (funds,))
        with closing(database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError), connection:
                connection.execute("INSERT INTO roster_memberships VALUES ('legacy-0',NULL,'fa')")
            with self.assertRaises(sqlite3.IntegrityError), connection:
                connection.execute("INSERT INTO initial_draft_candidates VALUES ('missing-person')")

    def test_failed_migration_rolls_back_schema_and_save(self):
        before = self.legacy_rows()
        with patch("idol_manager.migrations.V2_STATEMENTS", V2_STATEMENTS + ("NOT VALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):
                Database(self.path)
        self.assertEqual(before, self.legacy_rows())
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='agencies'").fetchone())
        self.assertEqual(len(list((self.path.parent / "backups").glob("*.sqlite3"))), 1)

    def test_backup_failure_prevents_migration_and_future_version_is_refused(self):
        before = self.legacy_rows()
        with patch("idol_manager.migrations.backup_database", side_effect=OSError("backup unavailable")):
            with self.assertRaises(OSError):
                Database(self.path)
        self.assertEqual(before, self.legacy_rows())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
        with self.assertRaises(RuntimeError):
            Database(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION + 1)
        self.assertEqual(before, self.legacy_rows())

    def test_explicit_new_game_resets_rosters_funds_and_pool_atomically(self):
        database = Database(self.path)
        with closing(database.connect()) as connection, connection:
            connection.execute("UPDATE agencies SET funds_krw=42 WHERE id='ador'")
            connection.execute("UPDATE roster_memberships SET career_status='first_team',agency_id='ador' WHERE person_id='legacy-0'")
        before = self.legacy_rows()
        people = tuple(Person(f"new-{i}", f"새 인물{i}", f"새 인물{i}", f"assets/idols/{i}.png") for i in range(250))
        settings = load_settings()
        from tests.migration_fixtures import fail_new_game
        with self.assertRaises(sqlite3.IntegrityError),fail_new_game(database):
            database.create_game(people, settings, random.Random(12))
        self.assertEqual(self.legacy_rows(), before)
        self.assertEqual(next(a.funds_krw for a in database.agencies() if a.id == "ador"), 42)
        self.assertEqual(len(database.agency_roster("ador")), 1)
        database.create_game(people, settings, random.Random(12))
        self.assertEqual(database.counts(), (250,200))
        self.assertEqual(len(database.initial_draft_candidates()), 200)
        self.assertTrue(all(a.funds_krw == INITIAL_FUNDS_KRW for a in database.agencies()))
        self.assertTrue(all(database.agency_roster(a.id) == [] for a in database.agencies()))
        with closing(database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM roster_memberships").fetchone()[0], 250)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
