from collections import Counter
from contextlib import closing
from pathlib import Path
import copy
import random
import sqlite3
import statistics
import tempfile
import unittest

from idol_manager.catalog import scan_idols
from idol_manager.config import ROOT, SKILLS, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person, generate_attributes, generate_skill_distribution
from idol_manager.service import GameService
from idol_manager.migrations import initialize_rosters


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="idol_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "한글 프로젝트"
        self.photos = self.root / "assets" / "idols"
        self.photos.mkdir(parents=True)
        self.database = Database(self.root / "data" / "game.sqlite3")
        self.settings = load_settings()

    def people(self, count):
        return tuple(Person(f"id-{i}", f"가상 인물 {i}", f"가상 인물 {i}", f"assets/idols/{i}.png") for i in range(count))

    def test_unicode_extensions_stable_ids_and_deduplication(self):
        for name in ("한글 이름.PNG", "한글 이름.jpg", "다른 이름.JPEG", "세 번째.WEBP", "ignore.gif"):
            (self.photos / name).write_bytes(b"test")
        before = {p.name: p.read_bytes() for p in self.photos.iterdir()}
        scan = scan_idols(self.root)
        self.assertEqual((scan.image_count, len(scan.people), len(scan.duplicates)), (4, 3, 1))
        self.assertEqual(scan.people, scan_idols(self.root).people)
        self.database.register(scan.people)
        self.database.register(scan.people)
        with closing(self.database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM people").fetchone()[0], 3)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.photos.iterdir()})

    def test_800_people_persistence_private_projection_and_integrity(self):
        people = self.people(850)
        self.database.create_game(people, self.settings, random.Random(55))
        self.assertEqual(self.database.counts(), (850, 200))
        reopened = Database(self.database.path)
        self.assertTrue(reopened.has_game())
        roster = reopened.public_roster()
        self.assertEqual(len(roster), 200)
        self.assertEqual(set(vars(roster[0])), {"id", "name", "photo_path", "age", "status"})
        with closing(reopened.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM idols WHERE status='candidate' AND age BETWEEN 17 AND 26").fetchone()[0], 200)
            snapshot = [tuple(r) for r in connection.execute("SELECT * FROM abilities ORDER BY person_id,skill")]
            self.assertEqual(len(snapshot), 850 * 8)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            rows = connection.execute("""
                SELECT i.person_id, i.average, AVG(a.value), COUNT(a.skill), MIN(a.potential-a.value),
                MIN(a.value), MAX(a.potential) FROM idols i JOIN abilities a ON a.person_id=i.person_id
                GROUP BY i.person_id
            """).fetchall()
            for row in rows:
                self.assertEqual(row[1], row[2])
                self.assertEqual(row[3], 8)
                self.assertGreaterEqual(row[4], 0)
                self.assertGreaterEqual(row[5], 0)
                self.assertLessEqual(row[6], 100)
        self.database.register(people)
        with closing(self.database.connect()) as connection:
            self.assertEqual(snapshot, [tuple(r) for r in connection.execute("SELECT * FROM abilities ORDER BY person_id,skill")])

    def test_failed_new_game_rolls_back_and_valid_replacement_has_no_duplicates(self):
        people = self.people(210)
        self.database.create_game(people, self.settings, random.Random(1))
        before = self.database.public_roster()
        # Health is deliberately capped by the current generator. Inject a
        # real storage failure to test atomic replacement instead.
        with closing(self.database.connect()) as c,c:
            c.execute("CREATE TRIGGER qa_new_game_failure BEFORE INSERT ON idols BEGIN SELECT RAISE(ABORT,'injected');END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.create_game(people, self.settings, random.Random(2))
        self.assertEqual(self.database.public_roster(), before)
        with closing(self.database.connect()) as c,c:c.execute('DROP TRIGGER qa_new_game_failure')
        self.database.create_game(people, self.settings, random.Random(3))
        self.assertEqual(self.database.counts(), (210, 200))
        self.assertNotEqual(self.database.public_roster(), before)

    def test_small_missing_empty_and_newly_added_assets(self):
        service = GameService(self.root)
        self.assertEqual(service.scan.image_count, 0)
        with self.assertRaises(ValueError):
            service.new_game()
        for name in ("가원.png", "아이돌.png"):
            (self.photos / name).write_bytes(b"not decodable but registered by filename")
        service.new_game()
        self.assertEqual(service.database.counts(), (2, 2))
        before = service.database.public_roster()
        (self.photos / "새 인물.webp").write_bytes(b"new")
        (self.photos / "가원.png").unlink()
        reopened = GameService(self.root)
        self.assertEqual(reopened.database.public_roster(), before)
        # New photos enter the next new game; missing portraits do not erase saved people.
        reopened.new_game()
        self.assertEqual(reopened.database.counts(), (2, 2))

    def test_weighted_generation_and_ranges(self):
        rng = random.Random(2026)
        counts = Counter()
        for _ in range(10000):
            values = generate_attributes(rng, self.settings)
            counts[values["archetype"]] += 1
            self.assertEqual(set(values["skills"]), set(SKILLS))
            self.assertTrue(17 <= values["age"] <= 26)
            self.assertTrue(0 <= values["health"] <= 100)
            for skill in SKILLS:
                self.assertTrue(0 <= values["skills"][skill] <= values["potentials"][skill] <= 100)
        for name, expected in (("specialist", .5), ("balanced", .3), ("extreme", .2)):
            self.assertAlmostEqual(counts[name] / 10000, expected, delta=.025)

    def test_same_average_all_types_distinct_shapes_and_specialty_counts(self):
        rng = random.Random(101)
        kinds = {kind["name"]: kind for kind in self.settings["archetypes"]}
        for overall in (40, 55, 70):
            deviations = {}
            for name, kind in kinds.items():
                observed_counts = set()
                spreads = []
                for _ in range(300):
                    skills = generate_skill_distribution(rng, overall, kind)
                    values = list(skills.values())
                    self.assertEqual(sum(values), overall * 8)
                    self.assertTrue(all(0 <= value <= 100 for value in values))
                    specialties = [value for value in values if value > overall]
                    observed_counts.add(len(specialties))
                    self.assertTrue(1 <= len(specialties) <= 3)
                    min_boost, max_boost = kind["specialty_boost"]
                    self.assertTrue(all(overall + min_boost <= value <= min(100, overall + max_boost) for value in specialties))
                    spreads.append(statistics.pstdev(values))
                self.assertEqual(observed_counts, {1, 2, 3})
                deviations[name] = statistics.mean(spreads)
            self.assertLess(deviations["balanced"], deviations["specialist"])
            self.assertLess(deviations["specialist"], deviations["extreme"])

    def test_overall_level_is_independent_of_type(self):
        rng = random.Random(2027)
        averages = {kind["name"]: [] for kind in self.settings["archetypes"]}
        for _ in range(12000):
            result = generate_attributes(rng, self.settings)
            self.assertEqual(result["average"], sum(result["skills"].values()) / 8)
            self.assertTrue(40 <= result["average"] <= 70)
            averages[result["archetype"]].append(result["average"])
        means = [statistics.mean(values) for values in averages.values()]
        self.assertLess(max(means) - min(means), 1.0)
        for values in averages.values():
            self.assertEqual(set(values), set(range(40, 71)))
        # Even boundary configurations keep the fixed budget and 0..100 bounds.
        for overall in (0, 1, 99, 100):
            for kind in self.settings["archetypes"]:
                skills = generate_skill_distribution(rng, overall, kind)
                self.assertEqual(sum(skills.values()), overall * 8)
                self.assertTrue(all(0 <= value <= 100 for value in skills.values()))

    def test_age_context_is_separate_from_future_rules(self):
        settings = copy.deepcopy(self.settings)
        settings["age_rules"]["future_test_only"] = [30, 30]
        rng = random.Random(333)
        ages = {generate_attributes(rng, settings)["age"] for _ in range(500)}
        self.assertEqual(ages, set(range(17, 27)))
        self.assertEqual(generate_attributes(rng, settings, age_context="future_test_only")["age"], 30)

    def test_legacy_save_age_and_abilities_preserved_on_service_reopen(self):
        # A legacy save may contain age 16 and the old extreme type's low mean.
        for name in ("기존 후보", "기존 미등장"):
            (self.photos / f"{name}.png").write_bytes(b"fixture")
        people = scan_idols(self.root).people
        self.database.register(people)
        with closing(self.database.connect()) as connection, connection:
            connection.execute("INSERT INTO game(id) VALUES (1)")
            for index, person in enumerate(people):
                connection.execute("INSERT INTO idols VALUES (?,16,77,'extreme',20,?)",
                                   (person.id, "candidate" if index == 0 else "unseen"))
                connection.executemany("INSERT INTO abilities VALUES (?,?,20,90)",
                                       [(person.id, skill) for skill in SKILLS])
            initialize_rosters(connection)
        with closing(self.database.connect()) as connection:
            before = list(connection.iterdump())
        for _ in range(2):
            service = GameService(self.root, self.database.path)
            self.assertTrue(service.database.has_game())
            self.assertEqual(service.database.public_roster()[0].age, 16)
            self.assertEqual(len(service.database.public_roster()), 1)
        with closing(self.database.connect()) as connection:
            self.assertEqual(before, list(connection.iterdump()))

    def test_existing_project_save_preserved_using_read_only_copy(self):
        source = ROOT / "data" / "idol_manager.sqlite3"
        if not source.is_file():
            self.skipTest("No existing project save")
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(self.database.path)) as destination:
                original.backup(destination)
        def saved_game_rows(database):
            with closing(database.connect()) as connection:
                return {
                    table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
                    for table in ("game", "idols", "abilities")
                }
        before = saved_game_rows(self.database)
        service = GameService(ROOT, self.database.path)
        self.assertEqual(saved_game_rows(service.database), before)
        self.assertTrue(all(person.status == "candidate" for person in service.database.public_roster()))

    def test_real_asset_registration(self):
        scan = scan_idols(ROOT)
        self.assertGreaterEqual(scan.image_count, 310)
        self.assertEqual(len(scan.people), len({p.id for p in scan.people}))
        self.database.create_game(scan.people, self.settings, random.Random(12))
        self.assertEqual(self.database.counts(), (len(scan.people), 200))


if __name__ == "__main__":
    unittest.main()
