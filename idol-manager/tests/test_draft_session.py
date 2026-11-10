from contextlib import closing
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.agencies import AGENCY_SEEDS, INITIAL_FUNDS_KRW
from idol_manager.ai_policy import RandomBlindPolicy
from idol_manager.config import SKILLS, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import DraftEngine, DraftError
from idol_manager.draft_session import DraftSession
from idol_manager.migrations import SCHEMA_VERSION, V1_STATEMENTS, V2_STATEMENTS, V3_STATEMENTS, V3_PLAYER_STATEMENTS, initialize_rosters


class DraftSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="idol_session_")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "저장.sqlite3"
        self.database = Database(self.path)
        self.people = tuple(Person(f"p-{i}",f"인물{i:03}",f"인물{i:03}",f"assets/idols/{i}.png") for i in range(310))
        self.database.create_game(self.people,load_settings(),random.Random(9))
        from tests.game_fixtures import legacy_save
        legacy_save(self.database)
        self.engine = DraftEngine(self.database)
        self.session = DraftSession(self.engine,RandomBlindPolicy(random.Random(42)))

    def test_selection_persists_locks_in_database_and_resets_only_for_new_game(self):
        self.assertIsNone(self.session.player_agency())
        with self.assertRaises(DraftError):
            self.session.start()
        self.session.select_agency("ador")
        self.session.select_agency("sm")
        reopened = DraftSession(DraftEngine(Database(self.path)))
        self.assertEqual(reopened.player_agency(),"sm")
        self.session.start()
        self.session.select_agency("sm")
        with self.assertRaises(DraftError):
            reopened.select_agency("ador")
        for sql in ("UPDATE player_settings SET agency_id='ador'", "DELETE FROM player_settings",
                    "INSERT OR REPLACE INTO player_settings(game_id,agency_id) VALUES (1,'ador')"):
            with closing(self.database.connect()) as connection:
                with self.assertRaises(sqlite3.IntegrityError),connection:
                    connection.execute(sql)
        self.database.create_game(self.people,load_settings(),random.Random(10))
        self.assertIsNone(self.session.player_agency())
        self.session.select_agency("ador")
        self.assertTrue(all(a.funds_krw==INITIAL_FUNDS_KRW for a in self.database.agencies()))

    def test_ai_policy_sees_public_candidates_and_shared_pick_api(self):
        self.session.select_agency("ador")
        self.session.start()
        turn = self.engine.state().next_turn
        if turn.agency_id=="ador":
            self.session.pick_player(self.engine.available_candidates()[0].id,expected_pick_number=turn.pick_number)
        seen = []
        class InspectPolicy:
            def choose(self,candidates):
                seen.extend(candidates)
                return candidates[0].id
        self.session.policy = InspectPolicy()
        statements = []
        original = self.database.connect
        def traced():
            connection=original(); connection.set_trace_callback(statements.append); return connection
        with patch.object(self.database,"connect",side_effect=traced),patch.object(self.engine,"pick",wraps=self.engine.pick) as pick:
            result = self.session.pick_ai_turn()
            self.assertIsNotNone(result)
            self.assertEqual(pick.call_count,1)
        self.assertTrue(seen)
        self.assertEqual(set(vars(seen[0])),{"id","name","photo_path","age","estimates","agency_id","pick_number"})
        for forbidden in ("abilities","potential","health","average","archetype","market_value"):
            self.assertNotIn(forbidden," ".join(statements).lower())

    def test_full_shared_player_ai_progress_resumes_and_stops_on_player_turn(self):
        self.session.select_agency("ador")
        self.session.start()
        original_order = self.engine.turn_order()
        player_picks=ai_picks=0
        while self.engine.state().status=="in_progress":
            turn=self.engine.state().next_turn
            if turn.agency_id=="ador":
                before=self.engine.state()
                self.assertIsNone(self.session.pick_ai_turn())
                self.assertEqual(before,self.engine.state())
                self.session.pick_player(self.engine.available_candidates()[0].id,expected_pick_number=turn.pick_number)
                player_picks+=1
            else:
                self.assertIsNotNone(self.session.pick_ai_turn()); ai_picks+=1
            if self.engine.state().picks_made==71:
                self.database=Database(self.path)
                self.engine=DraftEngine(self.database)
                self.session=DraftSession(self.engine,RandomBlindPolicy(random.Random(7)))
        self.assertEqual((player_picks,ai_picks),(16,144))
        self.assertEqual(original_order,self.engine.turn_order())
        self.session.validate_completion()
        self.assertEqual(len(self.engine.undrafted_candidates()),40)
        self.assertIsNone(self.session.pick_ai_turn())
        self.assertEqual(self.session.start().status,"completed")
        self.assertTrue(all(len(self.database.agency_roster(a.id))==16 for a in self.database.agencies()))

    def test_legacy_v3_ui_extension_backed_up_without_version_or_data_changes(self):
        path = Path(self.temp.name)/"legacy-v3.sqlite3"
        with closing(sqlite3.connect(path)) as connection,connection:
            connection.execute("PRAGMA foreign_keys=ON")
            for sql in V1_STATEMENTS+V2_STATEMENTS+V3_STATEMENTS:
                connection.execute(sql)
            connection.executemany("INSERT INTO agencies VALUES (?,?,?,?)",[(*a,INITIAL_FUNDS_KRW) for a in AGENCY_SEEDS])
            connection.execute("INSERT INTO game(id) VALUES (1)")
            connection.execute("INSERT INTO people VALUES ('old','기존','기존','assets/idols/기존.png')")
            connection.execute("INSERT INTO idols VALUES ('old',16,77,'extreme',50,'candidate')")
            connection.executemany("INSERT INTO abilities VALUES ('old',?,50,90)",[(s,) for s in SKILLS])
            initialize_rosters(connection)
            connection.execute("PRAGMA user_version=3")
        def rows():
            with closing(sqlite3.connect(path)) as connection:
                return {t:connection.execute(f"SELECT * FROM {t}").fetchall() for t in
                        ("people","idols","abilities","game","agencies","roster_memberships","initial_draft_candidates")}
        before=rows()
        with patch("idol_manager.migrations.V3_PLAYER_STATEMENTS",V3_PLAYER_STATEMENTS+("INVALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):
                Database(path)
        self.assertEqual(before,rows())
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],3)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='player_settings'").fetchone())
        database=Database(path)
        self.assertIsNotNone(database.last_backup_path)
        self.assertEqual(before,rows())
        with closing(database.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM player_settings").fetchone()[0],0)
        self.assertIsNone(Database(path).last_backup_path)
        self.assertEqual(DraftEngine(database).age_issues()[0].age,16)
