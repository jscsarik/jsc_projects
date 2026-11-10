"""Small diagnostic tests. The recorded integration DB is optional and read-only."""
from pathlib import Path
from types import SimpleNamespace
import unittest,random,secrets,uuid,sqlite3,json,tempfile
from unittest.mock import patch
from tools.simulate_game import ROOT,Simulation,seeded_entropy,state,restore,public_policy,schedule_audit,quick_audit

class SimulationTests(unittest.TestCase):
    def test_live_save_output_rejected(self):
        with self.assertRaises(ValueError):Simulation(SimpleNamespace(output=ROOT/'data',seed=1,budget_seconds=10,resume=False))

    def test_time_budget_saves_resume_checkpoint(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'diagnostics') as folder:
            sim=Simulation(SimpleNamespace(output=Path(folder),seed=3,budget_seconds=10,resume=False))
            sim.deadline=0
            with self.assertRaises(TimeoutError):sim.budget()
            saved=json.loads(sim.checkpoint.read_text(encoding='utf8'))
            self.assertEqual(saved['seed'],3);self.assertIn('calendar_rng',saved)

    def test_seed_and_rng_checkpoint(self):
        a=random.Random(2);b=random.Random(3)
        with seeded_entropy(a,b):
            first=(secrets.randbits(64),str(uuid.uuid4()))
            sa,sb=state(a),state(b);expected=(secrets.randbits(64),str(uuid.uuid4()))
        restore(a,json.loads(json.dumps(sa)));restore(b,json.loads(json.dumps(sb)))
        with seeded_entropy(a,b):self.assertEqual(expected,(secrets.randbits(64),str(uuid.uuid4())))
        with seeded_entropy(random.Random(2),random.Random(3)):self.assertEqual(first,(secrets.randbits(64),str(uuid.uuid4())))

    def test_public_policy_blocks_hidden_columns(self):
        c=sqlite3.connect(':memory:');c.executescript('CREATE TABLE abilities(value,potential);INSERT INTO abilities VALUES(50,80);');db=SimpleNamespace(connect=lambda:c)
        with public_policy(db):
            self.assertEqual(db.connect().execute('SELECT value FROM abilities').fetchone()[0],50)
            with self.assertRaises(sqlite3.DatabaseError):db.connect().execute('SELECT potential FROM abilities').fetchall()
        c.close()

class RecordedIntegrationTests(unittest.TestCase):
    def setUp(self):
        p=ROOT/'diagnostics/25_seed250029/simulation.sqlite3'
        if not p.exists():self.skipTest('별도 실제 엔진 실행 기록이 없음')
        def connect():
            c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
        self.db=SimpleNamespace(connect=connect);self.c=connect();self.addCleanup(self.c.close)

    def test_two_regular_seasons_integrity(self):
        for season in (1,2):self.assertEqual(schedule_audit(self.c,season)['status'],'PASS')
        self.assertFalse(any(quick_audit(self.c).values()))

    def test_completed_replay_is_same_and_read_only(self):
        from idol_manager.match_service import MatchService
        match=self.c.execute('SELECT match_id FROM match_results LIMIT 1').fetchone()[0]
        service=MatchService(self.db)
        a=service.result(match);b=service.play(match)
        self.assertEqual(a,b);self.assertGreater(len(a.events),0)

    def test_blocked_awards_does_not_invent_rookie(self):
        from idol_manager.awards import decide,AwardError
        with self.assertRaises(AwardError):decide([],[],2,random.Random(1))
        self.assertEqual(self.c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],405)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM season_awards WHERE season=2').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],1170)

if __name__=='__main__':unittest.main()
